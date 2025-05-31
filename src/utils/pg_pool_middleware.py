from __future__ import annotations

import time
from typing import TYPE_CHECKING
from aiohttp.web import Response

from aiohttp.web import middleware

if TYPE_CHECKING:
  from aiohttp.web import Request

# Disable the "call to /whatever/ took x microseconds"
DISABLED_LOG_PATHS = [
  "/api/job/workers/",
  "/api/job/complete/",
  "/api/job/current/"
]

@middleware
async def pg_pool_middleware(request: Request, handler):
  request.LOG = request.app.LOG
  start = time.monotonic_ns()
  try:
    resp = await handler(request)
  except Exception:
    request.LOG.exception(f"Request to {request.path} failed!")
    resp = Response(status=500,body="internal server error")
  if request.path not in DISABLED_LOG_PATHS:
    request.LOG.info(
      f"call to {request.path} took {(time.monotonic_ns()-start)/1000} microseconds"
    )
  if resp is None:
    resp = Response(status=204)
  return resp