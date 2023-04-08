-- This mimicks the `modem` peripheral but using the server instead.
local lib = {}

local BASE_URL = "wss://ccws.skystuff.cc/connect/"

local channels = {}

--- Open a channel, optionally with a password
-- @tparam string channel Channel name
-- @tparam[opt] string password Password. If not passed it assumes the channel is public.
-- @treturn boolean Whether or not the channel opened successfully
function lib.open(channel,password)
  local url = BASE_URL .. fs.combine(channel,password or "")
  local ws,err = http.websocket(url)
  if not ws then
    if err:match("403") then return false,"forbidden" end
    return false,err
  else
    channels[channel] = {ws=ws,passwd=password}
    return true
  end
end

--- Send a message on a channel.
-- @tparam string channel Channel name
-- @tparam string message Message to send.
-- @treturn boolean Whether the message was sent successfully.
function lib.transmit(channel,message)
  if not channels[channel] then
    return false
  end
  local ok = pcall(channels[channel].ws.send,message)
  if not ok then -- The websocket was closed, attempt reconnect.
    pcall(channels[channel].ws.close)
    local url = BASE_URL .. fs.combine(channel,channels[channel].passwd or "")
    local ws,err = http.websocket(url)
    if not ws then
      if err:match("403") then return false,"reconnect: forbidden" end
      return false,"reconnect failed"
    else
      channels[channel].ws = ws
      ws.send(message)
      return true
    end
  end
  return true
end

--- Wait to receive a message on the channel..
-- @treturn string The received message if not daemon.
function lib.receive(channel)
  if not channels[channel] then
    return false
  end
  local ok,msg = pcall(channels[channel].ws.receive)
  if not ok then -- The websocket was closed, attempt reconnect
    pcall(channels[channel].ws.close)
    local url = BASE_URL .. fs.combine(channel,channels[channel].passwd or "")
    local ws,err = http.websocket(url)
    if not ws then
      if err:match("403") then return false,"reconnect: forbidden" end
      return false,"reconnect failed"
    else
      channels[channel].ws = ws
      local msg = ws.receive()
      return msg
    end
  else
    return msg
  end
end

--- Loop forever and queue `bridge_message` events
-- `"bridge_message", channel, message`
function lib.daemon()
  while true do
    local e,url,contents = os.pullEvent("websocket_message")
    local channel = url:match("/connect/%w+"):sub(10)
    os.queueEvent("bridge_message",channel,contents)
  end
end

--- Close the channel. This removes it from the daemon and receive/send.
function lib.close(channel)
  if channels[channel] then
    channels[channel].ws.close()
    channels[channel] = nil
  end
end

return lib
