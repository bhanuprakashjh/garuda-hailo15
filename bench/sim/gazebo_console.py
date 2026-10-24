"""Local-only HTTP console. Requests enqueue; they never touch MAVLink directly."""
import json
import pathlib
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs


def serve(runtime, port):
    origin = f"http://127.0.0.1:{port}"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data, kind="application/json"):
            if not isinstance(data, bytes):
                data = json.dumps(data, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get('Host') == f"127.0.0.1:{port}"

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "use the loopback console URL"})
            request = urlsplit(self.path)
            if request.path == '/':
                return self.reply(200, pathlib.Path(__file__).with_name('follow_console.html').read_bytes(), 'text/html; charset=utf-8')
            if request.path == '/follow_console.js':
                return self.reply(200, pathlib.Path(__file__).with_name('follow_console.js').read_bytes(), 'text/javascript; charset=utf-8')
            if request.path == '/api/state':
                return self.reply(200, runtime.state())
            if request.path in ('/frame.jpg', '/overview.jpg'):
                try:
                    seq = int(parse_qs(request.query).get('sequence', ['-1'])[0])
                    data = runtime.image(request.path, seq)
                except (TypeError, ValueError):
                    data = None
                return self.reply(200, data, 'image/jpeg') if data else self.reply(410, {"error": "frame expired"})
            return self.reply(404, {"error": "not found"})

        def do_POST(self):
            if not self.allowed() or self.headers.get('Origin') != origin:
                return self.reply(403, {"error": "same-origin local operator required"})
            if self.path != '/api/action':
                return self.reply(404, {"error": "not found"})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError('bounded JSON request required')
                body = json.loads(self.rfile.read(size))
                message = runtime.action(body)
                return self.reply(202, {"message": message})
            except (ValueError, KeyError, TypeError, queue.Full) as error:
                return self.reply(400, {"error": str(error) or 'operator queue full'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server
