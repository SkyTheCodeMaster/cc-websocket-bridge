# Ratelimiter
from __future__ import annotations

import functools
import hashlib
import re
import time
from ipaddress import ip_address, ip_network
from typing import TYPE_CHECKING

from aiohttp.web import Response

from utils.authenticate import authenticate
from utils.logger import get_origin_ip

if TYPE_CHECKING:
  from ipaddress import IPv4Address
  from typing import Awaitable, Callable

  from utils.extra_request import Request

# Ideal usecase:
# limiter = Limiter(use_auth = True, use_auth_cache = True, exempt_ips=[])
# @routes.post("/")
# @limiter.limit("1/second", use_auth=True, auth_limit="2/second")
# async def post_slash(request: Request) -> Response:
#   ...


class Limiter:
  current_limits: dict[str, dict[str, list[int]]]
  EXPR: re.Pattern
  use_auth: bool
  use_auth_cache: bool
  exempt_ips: list[IPv4Address | IPv4Address]

  def __init__(
    self,
    *,
    use_auth: bool = True,
    use_auth_cache: bool = True,
    exempt_ips: list[str],
  ) -> None:
    self.use_auth = use_auth
    self.use_auth_cache = use_auth_cache
    self.exempt_ips = []
    for ip in exempt_ips:
      try:
        ipaddr = ip_address(ip)
      except ValueError:
        ipaddr = ip_network(ip)
      self.exempt_ips.append(ipaddr)

    SEPARATORS = re.compile(r"[,;|]{1}")  # noqa: N806
    SINGLE_EXPR = re.compile(  # noqa: N806
      r"""
        \s*([0-9]+)
        \s*(/|\s*per\s*)
        \s*([0-9]+)
        *\s*(h|hour|m|min|minute|s|sec|second|d|day|mo|month|y|year)s?\s*""",
      re.IGNORECASE | re.VERBOSE,
    )
    self.EXPR = re.compile(
      r"^{SINGLE}(:?{SEPARATORS}{SINGLE})*$".format(
        SINGLE=SINGLE_EXPR.pattern, SEPARATORS=SEPARATORS.pattern
      ),
      re.IGNORECASE | re.VERBOSE,
    )
    # {
    #   "route_name": {
    #     "hashed_user_identifier": [
    #       timestamp_when_free
    #     ]
    #   }
    # }
    self.current_limits: dict[str, dict[str, list[int]]] = {}

  def is_exempt(self, ipaddr: str) -> bool:
    ip = ip_address(ipaddr)
    for exempt in self.exempt_ips:
      try:
        if ip == exempt:
          return True
        if ip in exempt:
          return True
      except Exception:
        pass
    return False

  def limit(
    self,
    normal_limit: str,
    *,
    auth_limit: str = None,
    route_name: str = None,
    force_auth: bool = False,
  ) -> Callable[[Request, None], Awaitable[Response]]:
    # Check the limits for validity
    self.parse_limit(normal_limit)
    if auth_limit:
      self.parse_limit(auth_limit)
      
    def _decorator(
      f: Callable[[Request, None], Awaitable[Response]],
    ) -> Callable[[Request, None], Awaitable[Response]]:
      @functools.wraps(f)
      async def _inner(
        request: Request,
        *,
        normal_limit: str = normal_limit,
        auth_limit: str = auth_limit,
        force_auth: bool = force_auth,
        route_name: str = route_name,
      ) -> Response:
        if route_name is None:
          route_name = f.__name__
        if auth_limit is None:
          auth_limit = normal_limit

        resp = await self._limiter(
          normal_limit,
          auth_limit=auth_limit,
          route_name=route_name,
          force_auth=force_auth,
          request=request,
        )

        if resp is not None:
          return resp

        return await f(request)

      return _inner

    return _decorator

  def parse_limit(self, limit: str) -> tuple[int, int]:
    # Take in a limit string, output [limit, seconds]
    match = self.EXPR.match(limit)
    if match:
      total, _, mult, granularity = match.groups()[:4]
      lookup = {
        "h": 3600,
        "hour": 3600,
        "m": 60,
        "min": 60,
        "minute": 60,
        "s": 1,
        "sec": 1,
        "second": 1,
        "d": 86400,
        "day": 86400,
        "mo": 86400 * 30,
        "month": 86400 * 30,
        "year": 86400 * 365,
        "y": 86400 * 365,
      }

      if mult is None:
        mult = 1
      seconds = int(mult) * lookup[granularity]
      return (int(total), seconds)
    else:
      raise ValueError(f"ratelimit string {limit} is invalid!")

  async def _limiter(
    self,
    normal_limit: str,
    *,
    auth_limit: str = None,
    route_name: str,
    force_auth: bool = False,
    request: Request,
  ) -> Response | None:
    ip = get_origin_ip(request)
    if self.is_exempt(ip):
      return None
      
    if self.use_auth and auth_limit is None:
      raise Exception("must pass auth limit when use_auth is True!")

    if self.use_auth:
      try:
        # Authenticate and use username as ident
        user = await authenticate(
          request, cs=request.session, use_cache=self.use_auth_cache
        )
        if not hasattr(user, "username"):
          if force_auth:
            return Response(status=401)
          else:
            ident = None
        else:
          ident = hashlib.sha512(user.username.encode()).hexdigest()
          resolved_limit = auth_limit
      except Exception:
        ident = None
    if ident is None:
      ident = hashlib.sha512(ip.encode()).hexdigest()
      resolved_limit = normal_limit

    # Now check if the ratelimit is free
    total, seconds = self.parse_limit(resolved_limit)

    if route_name not in self.current_limits:
      self.current_limits[route_name] = {}
    if ident not in self.current_limits[route_name]:
      self.current_limits[route_name][ident] = []


    user_limits = self.current_limits[route_name][ident]

    # Check if any are expired
    current_time = int(time.time())
    user_limits = [expiry for expiry in user_limits if current_time < expiry]
    user_limits.sort()
    self.current_limits[route_name][ident] = user_limits

    if len(user_limits) >= total:
      # calculate next free
      current_time = int(time.time())
      time_until_free = user_limits[0] - current_time
      return Response(status=429, headers={"Retry-After": str(time_until_free)})
    else:
      # add current request to window, return None
      current_time = int(time.time())
      user_limits.append(current_time + seconds)
