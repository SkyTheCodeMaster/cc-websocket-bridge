from __future__ import annotations

import asyncio
import collections
import logging
import random
import tomllib
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web
from aiohttp.web import Response

if TYPE_CHECKING:
  from typing import Union
  from utils.extra_request import Request

with open("config.toml") as f:
  config = tomllib.loads(f.read())

LOG = logging.getLogger(__name__)


class NodeMessage:
  data: str
  channel: str
  nonce: str
  binary: bool

  def __init__(
    self, *, channel: str, data: Union[str, bytes], nonce: str, binary: bool
  ) -> None:
    self.channel = channel
    self.data = data
    self.nonce = nonce
    self.binary = binary


routes = web.RouteTableDef()
received_messages = collections.deque([], 100)

# url = Node
outgoing_nodes: dict[str, Node] = {}
# list of ws responses
incoming_nodes: list[web.WebSocketResponse] = []


async def handle_message(
  msg: aiohttp.WSMessage,
  sender: Union[web.WebSocketResponse, aiohttp.ClientWebSocketResponse],
  app: web.Application,
) -> None:
  try:
    if msg.type == web.WSMsgType.TEXT:
      data = msg.json()
      nodemsg = NodeMessage(
        channel=data["channel"],
        data=data["data"],
        nonce=data["nonce"],
        binary=data["binary"],
      )
      if data["nonce"] in received_messages:
        return
      received_messages.append(data["nonce"])
      await send_message_to_other_nodes(nodemsg, sender, app)
      if sender is None:
        return # None means we were the sender, don't bother routing it back to ourselves
      if nodemsg.binary:
        await send_relay_message(nodemsg.data.encode(), nodemsg.channel, app)
      else:
        await send_relay_message(nodemsg.data, nodemsg.channel, app)
      # TODO: handle receiving messages from the relay side of this node.
  except Exception:
    LOG.exception("Failed to process message from another node")


async def send_message_to_other_nodes(
  msg: NodeMessage,
  sender: Union[web.WebSocketResponse, aiohttp.ClientWebSocketResponse],
  app: web.Application
) -> None:
  # First send to outgoing nodes
  payload = {
    "binary": msg.binary,
    "data": msg.data,
    "channel": msg.channel,
    "nonce": msg.nonce,
  }
  for node in app.outgoing_nodes.values():
    if node == sender:
      continue
    try:
      await node.send_message(msg)
    except Exception:
      LOG.exception(f"Failed to send message to outgoing node {node.url}")
  # Send to incoming nodes
  for ws in app.incoming_nodes:
    if ws == sender:
      continue
    try:
      await ws.send_json(payload)
    except Exception:
      LOG.exception(f"Failed to send message to incoming node {ws}")


class Node:
  url: str
  ws: aiohttp.ClientWebSocketResponse
  app: web.Application

  def __init__(self, url: str, app: web.Application) -> None:
    self.url = url
    self.app = app

  async def send_message(self, msg: NodeMessage) -> None:
    payload = {
      "binary": msg.binary,
      "data": msg.data,
      "channel": msg.channel,
      "nonce": msg.nonce,
    }
    await self.ws.send_json(payload)

  async def create_websocket(self) -> None:
    LOG.info(f"[Node] Attempting to connect to {self.url}...")
    headers = {"Authorization": config["srv"]["node_password"]}
    async with self.app.cs.ws_connect(self.url, headers=headers, heartbeat=10.0, timeout=15.0) as ws:
      LOG.info(f"[Node] Connected to {self.url}")
      self.app.outgoing_nodes[self.url] = self
      self.ws = ws
      async for msg in ws:
        LOG.debug("received:", str(msg.data))
        if msg.type == aiohttp.WSMsgType.TEXT:
          await handle_message(msg, ws, self.app)
        elif msg.type == aiohttp.WSMsgType.ERROR:
          LOG.error(f"Error from {self.url}... attempting reconnect")
          outgoing_nodes[self.url] = None
          break
    LOG.error(f"[Node] Disconnected from {self.url}, waiting 10 seconds...")
    await asyncio.sleep(10)
    return await self.create_websocket()


routes = web.RouteTableDef()


@routes.get("/node/")
async def get_node(request: Request) -> Response:
  authorization = request.headers.get("Authorization", None)
  if authorization is None:
    return Response(status=403)
  if authorization != config["srv"]["node_password"]:
    return Response(status=403)

  ws = web.WebSocketResponse(heartbeat=10.0, timeout=15.0)
  await ws.prepare(request)

  request.app.incoming_nodes.append(ws)
  LOG.info("[NODE] New incoming node")
  print(request.app.incoming_nodes)
  async for msg in ws:
    LOG.info(f"received: {msg.data}")
    if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
      await handle_message(msg, ws, request.app)
    else:
      request.LOG.info("[NODE] Incoming node disconnected.")
  LOG.warning("[Node] Incoming node disconnected")
  try:
    request.app.incoming_nodes.remove(ws)
  except Exception:
    pass


async def setup_outgoing_connections(app: web.Application) -> None:
  for url in config["srv"]["nodes"]:
    node = Node(url, app)
    loop = asyncio.get_event_loop()
    loop.create_task(node.create_websocket())


async def create_node_message(msg: Union[str, bytes], channel: str, app: web.Application) -> None:
  "Create a NodeMessage and send it to the network"
  nonce = random.getrandbits(64)
  d = {"nonce": nonce, "channel": channel}

  if type(msg) is str:
    d["data"] = msg
    d["binary"] = False
  else:
    d["data"] = msg.decode()
    d["binary"] = True

  nodemsg = NodeMessage(
    channel=d["channel"],
    data=d["data"],
    nonce=d["nonced"],
    binary=d["binary"],
  )

  await send_message_to_other_nodes(nodemsg, None, app)


async def send_relay_message(
  msg: Union[str, bytes], channel: str, app: web.Application
) -> None:
  "Send a message to the relay side of the node"
  if channel in app.channels:
    if type(msg) not in [str, bytes]:
      msg = str(msg)
    await app.channels[channel].send_message(msg, None)


async def setup(app: web.Application) -> None:
  for route in routes:
    app.LOG.info(f"  ↳ {route}")
  app.add_routes(routes)
  app.outgoing_nodes = {}
  app.incoming_nodes = []
  await setup_outgoing_connections(app)
