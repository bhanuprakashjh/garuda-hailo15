"""Temporary loopback, GET-only package proxy for the isolated 15L ROS rootfs.

No general CONNECT proxy, credentials, board routing or persistent service.
Repository signatures are still verified by apt inside the rootfs.
"""
import http.server
import urllib.request
import urllib.parse

ALLOWED = {'ports.ubuntu.com', 'packages.ros.org', 'archive.ubuntu.com', 'security.ubuntu.com'}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.scheme != 'http' or url.hostname not in ALLOWED or url.port not in (None, 80) or url.username:
            self.send_error(403)
            return
        try:
            # Official ROS HTTPS repository alias has a valid certificate;
            # packages.ros.org itself is documented as HTTP and lacks one.
            host, path = url.netloc, url.path
            if url.hostname == 'packages.ros.org':
                if not path.startswith('/ros2/ubuntu/'):
                    self.send_error(403)
                    return
                host, path = 'repo.ros2.org', '/ubuntu/main/'+path[len('/ros2/ubuntu/'):]
            request = urllib.request.Request(urllib.parse.urlunsplit(('https', host, path, url.query, '')))
            with urllib.request.urlopen(request, timeout=45) as source:
                self.send_response(source.status)
                if source.headers.get('Content-Length'):
                    self.send_header('Content-Length', source.headers['Content-Length'])
                self.end_headers()
                while block := source.read(128 * 1024):
                    self.wfile.write(block)
        except Exception as error:
            self.send_error(502, str(error))


if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('127.0.0.1', 18080), Handler).serve_forever()
