import http.server
import socketserver
import os
import http.client
import socket
import threading
import urllib.parse
from pathlib import Path

DIST_DIR = Path(__file__).parent / "dist"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8002")
PORT = int(os.environ.get("FRONTEND_PORT", "5173"))

_parsed_backend = urllib.parse.urlparse(BACKEND_URL)
BACKEND_HOST = _parsed_backend.hostname or "127.0.0.1"
BACKEND_PORT = _parsed_backend.port or 80


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/") or self.path.startswith("/ws/"):
            self._proxy_request("GET")
        else:
            if self.path == "/" or "." not in self.path.split("/")[-1]:
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy_request("POST")
        else:
            self.send_error(404)

    def do_PUT(self):
        if self.path.startswith("/api/"):
            self._proxy_request("PUT")
        else:
            self.send_error(404)

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            self._proxy_request("DELETE")
        else:
            self.send_error(404)

    def _proxy_request(self, method):
        is_sse = "stream" in self.path or "batch-quick" in self.path
        conn = None
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None

            if 'batch-quick' in self.path:
                backend_timeout = 600
            elif is_sse:
                backend_timeout = 120
            elif '/backtest' in self.path:
                backend_timeout = 300
            else:
                backend_timeout = 60
            conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=backend_timeout)

            fwd_headers = {}
            for key in ["Content-Type", "Authorization", "Accept", "Cookie"]:
                if key in self.headers:
                    fwd_headers[key] = self.headers[key]

            conn.request(method, self.path, body=body, headers=fwd_headers)

            resp = conn.getresponse()

            self.send_response(resp.status)

            is_streaming = False
            for key, val in resp.getheaders():
                key_lower = key.lower()
                if key_lower in ("connection", "transfer-encoding", "content-length"):
                    continue
                if key_lower == "content-type" and "text/event-stream" in val:
                    is_streaming = True
                self.send_header(key, val)

            if is_streaming:
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
            else:
                resp_data = resp.read()
                self.send_header("Content-Length", str(len(resp_data)))
                self.send_header("Connection", "close")
            self.end_headers()

            if is_streaming:
                sse_buffer = b''
                while True:
                    try:
                        chunk = resp.read(4096)
                        if not chunk:
                            if sse_buffer:
                                self.wfile.write(sse_buffer)
                                self.wfile.flush()
                            break
                        chunk = chunk.replace(b'\r\n', b'\n')
                        sse_buffer += chunk
                        while b'\n\n' in sse_buffer:
                            event_end = sse_buffer.index(b'\n\n') + 2
                            event_data = sse_buffer[:event_end]
                            sse_buffer = sse_buffer[event_end:]
                            self.wfile.write(event_data)
                            self.wfile.flush()
                    except Exception:
                        break
            else:
                if resp_data:
                    self.wfile.write(resp_data)
                    self.wfile.flush()

        except Exception as e:
            try:
                if not self.headers_sent:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(f'{{"detail":"Proxy error: {str(e)}"}}'.encode())
            except Exception:
                pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


if __name__ == "__main__":
    with ThreadedHTTPServer(("0.0.0.0", PORT), ProxyHandler) as httpd:
        print(f"Frontend server running on http://0.0.0.0:{PORT}")
        print(f"Serving: {DIST_DIR}")
        print(f"Proxy /api/* -> {BACKEND_URL}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            httpd.shutdown()
