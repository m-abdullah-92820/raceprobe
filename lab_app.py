#!/usr/bin/env python3
"""Lab app for RaceProbe: a coupon that may be redeemed only once.

Binds to 127.0.0.1 only. Never expose this to a network.

  python3 lab_app.py            # VULNERABLE: check and update are not atomic
  python3 lab_app.py --safe     # FIXED: a lock makes check+update atomic
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

state = {"redeemed": False, "redeem_count": 0}
lock = threading.Lock()
SAFE = False


def redeem():
    """Redeem the coupon. Returns (http_status, message)."""
    if SAFE:
        with lock:                       # check + update happen as one step
            return _redeem_logic()
    return _redeem_logic()               # no lock: the race window is open


def _redeem_logic():
    if state["redeemed"]:                # CHECK
        return 409, "already redeemed"
    time.sleep(0.05)                     # simulated work (DB call, etc.)
    state["redeemed"] = True             # UPDATE
    state["redeem_count"] += 1
    return 200, "coupon redeemed"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        if self.path == "/redeem":
            code, msg = redeem()
            self._send(code, {"message": msg})
        elif self.path == "/reset":
            state.update(redeemed=False, redeem_count=0)
            self._send(200, {"message": "reset"})
        else:
            self._send(404, {"message": "not found"})

    def do_GET(self):
        if self.path == "/status":
            self._send(200, {**state, "safe_mode": SAFE})
        else:
            self._send(404, {"message": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--safe", action="store_true", help="use locking")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    SAFE = args.safe
    print(f"Lab app on http://127.0.0.1:{args.port} | "
          f"{'SAFE (locked)' if SAFE else 'VULNERABLE (no lock)'}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
