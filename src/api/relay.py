from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web
from api.multinode import create_node_message

if TYPE_CHECKING:
  from typing import Union
  from utils.extra_request import Request
  from aiohttp.web import Response

LOG = logging.getLogger(__name__)
channels: dict[str, Channel] = {}

class Channel:
  name: str
  passwd: str
  clients: list[web.WebSocketResponse]

  def __init__(self, name: str, passwd: str) -> None:
    self.name = name
    self.passwd = passwd
    self.clients = []

  async def send_message(
    self, msg: Union[str, bytes], sender: web.WebSocketResponse
  ) -> None:
    for ws in self.clients:
      if ws != sender:
        if type(msg) is str:
          await ws.send_str(msg)
        else:
          await ws.send_bytes(msg)

  async def handle_websocket(self, request: Request) -> Response:
    ws = web.WebSocketResponse(heartbeat=10.0)
    await ws.prepare(request)

    self.clients.append(ws)
    request.LOG.info(f"[CHAN {self.name}] new client. {len(self.clients)} connected.")

    async for msg in ws:
      LOG.info(f"[CHAN {self.name}] received message")
      if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
        await self.send_message(msg.data, ws)
        try:
          LOG.info(f"[CHAN {self.name}] trying to send node message")
          await create_node_message(msg.data, self.name)
        except Exception:
          LOG.exception("Couldnt send node message")
      else:
        request.LOG.info(
          f"{self.name}: ws connection closed with exception {ws.exception()}"
        )
    try:
      self.clients.remove(ws)
    except Exception:
      pass
    request.LOG.info(
      f"[CHAN {self.name}]: client disconnected. {len(self.clients)} connected."
    )
    # Check if we're empty
    if not self.clients:
      channels.pop(self.name)
      request.LOG.info(f"[CHAN {self.name}]: empty, removing.\nChannels:")
      for channel in channels.values():
        request.LOG.info(f" - {channel}")

    return ws

  def __str__(self) -> str:
    return f"<Channel {self.name} Clients {len(self.clients)}>"


routes = web.RouteTableDef()


@routes.get("/connect/{tail:.*}")
async def websocket_handler(request: Request) -> Response:
  conndetails: str = request.path.removeprefix(
    "/connect/"
  )  # Channel/password is same thing here.
  try:
    channel, password = conndetails.split("/")
  except ValueError:
    channel = conndetails
    password = ""
  if channel in channels:  # We are connecting to an existing channel.
    c = channels[channel]
    if password == c.passwd:
      return await c.handle_websocket(request)
    else:
      return web.Response(status=403)
  else:
    # We are creating a new channel.
    c = Channel(channel, password)
    channels[channel] = c
    return await c.handle_websocket(request)


async def setup(app: web.Application) -> None:
  for route in routes:
    app.LOG.info(f"  ↳ {route}")
  app.add_routes(routes)
  app.channels = channels
