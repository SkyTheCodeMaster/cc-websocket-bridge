# cc-websocket-bridge
A simple server that bounces messages between clients on channels.
Similar to modems except that this is encrypted (and password protected) without any Lua side cost.

# setup
* `git clone https://github.com/skythecodemaster/cc-websocket-bridge`
* `cd cc-websocket-bridge`
* `./setup.sh`

Run `./run.sh` inside a tmux session, screen session, etc.

# usage
Using the server raw is the only method for now. Lua libraries that mimick `modem` and `rednet` will be added soon.

```lua
local ws = http.websocket("wss://example.com/connect/<channel_name>", {
  "Authorization": "Super secret, but optional, password!"
})

ws.send("Message!")

-- On another machine:
print(ws.receive())
-- Message!
```
Use `/connect/<channel_name>` without an `Authorization` header for a public channel if desired

This has multi-node compatibility, check the config for details.