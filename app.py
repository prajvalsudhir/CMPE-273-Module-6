import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

POD = os.environ.get("HOSTNAME", "unknown")

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/ready":
            if os.path.exists("/tmp/unready"):
                print(f"[inventory] GET /ready -> 500 (unready) pod={POD}", flush=True)
                self._send(500, {"ready": False, "pod": POD})
            else:
                self._send(200, {"ready": True, "pod": POD})
            return
        if self.path == "/healthz":
            self._send(200, {"ok": True, "pod": POD})
            return
        print(f"[inventory] GET / served by pod={POD}", flush=True)
        self._send(200, {"pod": POD, "item": "widget", "stock": 42})

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
