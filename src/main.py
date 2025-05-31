from __future__ import annotations

import asyncio
import logging
import math
import os
import tomllib

import aiohttp
import coloredlogs
import uvloop
from aiohttp import web

from utils.get_routes import get_module
from utils.logger import CustomWebLogger
from utils.pg_pool_middleware import pg_pool_middleware

LOGFMT = "[%(filename)s][%(asctime)s][%(levelname)s] %(message)s"
LOGDATEFMT = "%Y/%m/%d-%H:%M:%S"

handlers = [
  logging.StreamHandler()
]

with open("config.toml") as f:
  config = tomllib.loads(f.read())

if config['log']['file']:
  handlers.append(logging.FileHandler(config['log']['file']))

logging.basicConfig(
  handlers = handlers,
  format=LOGFMT,
  datefmt=LOGDATEFMT,
  level=logging.WARNING,
)

coloredlogs.install(
  fmt=LOGFMT,
  datefmt=LOGDATEFMT
)

LOG = logging.getLogger(__name__)

app = web.Application(
  #logger = CustomWebLogger(LOG),
  middlewares=[
    pg_pool_middleware
  ],
  client_max_size=8192**2
)

async def startup():
  try:
    session = aiohttp.ClientSession()
    app.cs = session

    app.LOG = LOG
    disabled_cogs: list[str] = []

    for cog in [
        f.replace(".py","") 
        for f in os.listdir("api") 
        if os.path.isfile(os.path.join("api",f)) and f.endswith(".py")
      ]:
      if cog not in disabled_cogs:
        LOG.info(f"Loading {cog}...")
        try:
          lib = get_module(f"api.{cog}")
          await lib.setup(app)
        except Exception:
          LOG.exception(f"Failed to load cog {cog}!")

    LOG.info("Loading frontend...")
    try:
      lib = get_module("frontend.routes")
      await lib.setup(app)
    except Exception:
      LOG.exception("Failed to load frontend!")

    # If we're running as the daemon, we dont need to serve.
    runner = web.AppRunner(app, logger=CustomWebLogger(LOG))
    await runner.setup()
    site = web.TCPSite(
      runner,
      config['srv']['host'],
      config['srv']['port'],
    )
    await site.start()
    print(f"Started server on http://{config['srv']['host']}:{config['srv']['port']}...\nPress ^C to close...")
    await asyncio.sleep(math.inf)
  except KeyboardInterrupt:
    pass
  except asyncio.exceptions.TimeoutError:
    LOG.error("PostgreSQL connection timeout. Check the connection arguments!")
  finally:
    try: await site.stop()   # noqa: E701
    except: pass  # noqa: E722, E701
    try: await session.close()   # noqa: E701
    except: pass  # noqa: E722, E701

try:
  uvloop.run(startup(), debug=True)
except KeyboardInterrupt:
  print("Server shut down.")