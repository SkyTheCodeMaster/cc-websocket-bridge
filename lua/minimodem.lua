local a={}local b="wss://ccws.skystuff.cc/connect/"local c={}function a.open(d,e)local f=b..fs.combine(d,e or"")local g,h=http.websocket(f)if not g then if h:match("403")then return false,"forbidden"end;return false,h else c[d]={ws=g,passwd=e}return true end end;function a.transmit(d,i)if not c[d]then return false end;local j=pcall(c[d].ws.send,i)if not j then pcall(c[d].ws.close)local f=b..fs.combine(d,c[d].passwd or"")local g,h=http.websocket(f)if not g then if h:match("403")then return false,"reconnect: forbidden"end;return false,"reconnect failed"else c[d].ws=g;g.send(i)return true end end;return true end;function a.receive(d)if not c[d]then return false end;local j,k=pcall(c[d].ws.receive)if not j then pcall(c[d].ws.close)local f=b..fs.combine(d,c[d].passwd or"")local g,h=http.websocket(f)if not g then if h:match("403")then return false,"reconnect: forbidden"end;return false,"reconnect failed"else c[d].ws=g;local k=g.receive()return k end else return k end end;function a.daemon()while true do local l,f,m=os.pullEvent("websocket_message")local d=f:match("/connect/%w+"):sub(10)os.queueEvent("bridge_message",d,m)end end;function a.close(d)if c[d]then c[d].ws.close()c[d]=nil end end;return a
