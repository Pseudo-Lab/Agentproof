"""Optional localhost transport; no Python child process is launched by Node."""
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from benchmark import generate
from judge import get_assert


def start_bridge():
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.headers.get("Authorization") != "Bearer " + token:
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 8_000_000:
                    raise ValueError("Invalid request length")
                payload = json.loads(self.rfile.read(size))
                if self.path == "/generate":
                    ctx = payload["context"]
                    result = generate(payload["group"], payload["prompt"], ctx["vars"]["task_id"],
                                      ctx.get("repeatIndex", 0))
                elif self.path == "/grade":
                    result = get_assert(payload["output"], payload["context"])
                else:
                    self.send_error(404)
                    return
                data = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                # Details are already in the ledger. Never expose keys in HTTP responses.
                self.send_error(500, "Experiment call failed; inspect records")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    os.environ["PLAN_BRIDGE_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["PLAN_BRIDGE_TOKEN"] = token
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
