import http.server
import os
import urllib.request
import urllib.error
import sys
from pathlib import Path

DIST_DIR = Path(__file__).parent / "dist"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8002")
PORT = int(os.environ.get("FRONTEND_PORT", "5173"))


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
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
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None

            headers = {}
            for key in ["Content-Type", "Authorization", "Accept"]:
                if key in self.headers:
                    headers[key] = self.headers[key]

            target_url = f"{BACKEND_URL}{self.path}"
            req = urllib.request.Request(
                target_url, data=body, headers=headers, method=method
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(resp.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"detail":"Backend error: {str(e)}"}}'.encode())

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    with http.server.HTTPServer(("0.0.0.0", PORT), ProxyHandler) as httpd:
        print(f"Frontend server running on http://0.0.0.0:{PORT}")
        print(f"Serving: {DIST_DIR}")
        print(f"Proxy /api/* -> {BACKEND_URL}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            httpd.shutdown()
