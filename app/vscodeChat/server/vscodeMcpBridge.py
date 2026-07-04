"""VSCode MCP bridge: pure byte relay stdin/stdout ↔ Extension TCP.
Zero JSON parsing, zero state — identical to Extension's Agent relay.
"""
import sys, socket, os, select

port = int(os.environ.get('QODER_MCP_PORT', 0))
if not port:
    sys.exit(1)

sock = socket.create_connection(('127.0.0.1', port))
sock.setblocking(False)

while True:
    r, _, _ = select.select([sys.stdin.buffer, sock], [], [])
    if sys.stdin.buffer in r:
        data = sys.stdin.buffer.read1()
        if not data: break
        sock.sendall(data)
    if sock in r:
        data = sock.recv(8192)
        if not data: break
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
