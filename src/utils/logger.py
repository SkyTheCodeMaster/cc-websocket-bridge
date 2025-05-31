from __future__ import annotations

import functools
import logging
import tomllib
from ipaddress import ip_address
from typing import TYPE_CHECKING

from aiohttp import hdrs, web
from aiohttp.web_log import AccessLogger, KeyMethod

from utils.pg_pool_middleware import DISABLED_LOG_PATHS

if TYPE_CHECKING:
  from ipaddress import IPv4Address, IPv6Address
  from typing import List, Tuple, Union

  from aiohttp.web import BaseRequest, StreamResponse
  from multidict import MultiMapping

  from utils.extra_request import Request

  IPAddress = Union[IPv4Address, IPv6Address]

with open("config.toml") as f:
  config = tomllib.loads(f.read())
  TRUSTED_PROXIES = config["srv"]["trusted_proxies"]


def get_forwarded_for(headers: MultiMapping[str]) -> List[IPAddress]:
  forwarded_for: List[str] = headers.getall(hdrs.X_FORWARDED_FOR, [])
  if not forwarded_for:
    return []
  if len(forwarded_for) > 1:
    raise Exception(f"Too many headers for {hdrs.X_FORWARDED_FOR}")
  forwarded_for = forwarded_for[0].split(",")
  valid_ips = []
  for a in forwarded_for:
    addr = a.strip()
    try:
      if addr in TRUSTED_PROXIES:
        continue
      valid_ips.append(ip_address(addr))
    except ValueError:
      raise web.HTTPBadRequest(reason=f"Invalid {hdrs.X_FORWARDED_FOR} header")
  return valid_ips


def get_origin_ip(request: Request) -> str:
  forwarded_for = get_forwarded_for(request.headers)
  if not forwarded_for:
    return request.remote
  first = forwarded_for[0]
  return str(first)


class CustomWebLogger(AccessLogger):
  def compile_format(self, log_format: str) -> Tuple[str, List[KeyMethod]]:
    """
    Translate log_format into form usable by modulo formatting

    All known atoms will be replaced with %s
    Also methods for formatting of those atoms will be added to
    _methods in appropriate order
    For example we have log_format = "%a %t"
    This format will be translated to "%s %s"
    Also contents of _methods will be
    [self._format_a, self._format_t]
    These method will be called and results will be passed
    to translated string format.
    Each _format_* method receive 'args' which is list of arguments
    given to self.log
    Exceptions are _format_e, _format_i and _format_o methods which
    also receive key name (by functools.partial)
    """
    # list of (key, method) tuples, we don't use an OrderedDict as users
    # can repeat the same key more than once
    methods = list()
    for atom in self.FORMAT_RE.findall(log_format):
      if atom[1] == "":
        format_key1 = self.LOG_FORMAT_MAP[atom[0]]
        m = getattr(self, "_format_%s" % atom[0])
        key_method = KeyMethod(format_key1, m)
      else:
        format_key2 = (self.LOG_FORMAT_MAP[atom[2]], atom[1])
        m = getattr(self, "_format_%s" % atom[2])
        key_method = KeyMethod(format_key2, functools.partial(m, atom[1]))
      methods.append(key_method)
    log_format = self.FORMAT_RE.sub(r"%s", log_format)
    log_format = self.CLEANUP_RE.sub(r"%\1", log_format)
    return log_format, methods

  @staticmethod
  def _format_a(
    request: BaseRequest, response: StreamResponse, time: float
  ) -> str:
    if request is None:
      return "-"
    headers = request.headers
    forwarded_for = get_forwarded_for(headers)
    if forwarded_for:
      ip = str(forwarded_for[-1])
    else:
      ip = request.remote
    return ip if ip is not None else "-"

  def log(
    self, request: BaseRequest, response: StreamResponse, time: float
  ) -> None:
    if not self.logger.isEnabledFor(logging.INFO):
      # Avoid formatting the log line if it will not be emitted.
      return
    print(request.path)
    if request.path in DISABLED_LOG_PATHS:
      return
    try:
      fmt_info = self._format_line(request, response, time)

      values = list()
      extra = dict()
      for key, value in fmt_info:
        values.append(value)

        if key.__class__ is str:
          extra[key] = value
        else:
          k1, k2 = key  # type: ignore[misc]
          dct = extra.get(k1, {})  # type: ignore[var-annotated,has-type]
          dct[k2] = value  # type: ignore[index,has-type]
          extra[k1] = dct  # type: ignore[has-type,assignment]

      self.logger.info(self._log_format % tuple(values), extra=extra)
    except Exception:
      self.logger.exception("Error in logging")
