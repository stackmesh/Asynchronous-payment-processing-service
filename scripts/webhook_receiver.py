#!/usr/bin/env python3
"""Tiny webhook sink for the docker demo. Writes one JSON line per POST."""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "webhook-events.jsonl"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 9000

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            with open(path, "a", encoding="utf-8") as sink:
                sink.write(raw.decode("utf-8") + "\n")
                sink.flush()
            print(raw.decode("utf-8"), flush=True)
            self.send_response(204)
            self.end_headers()

        def log_message(self, fmt: str, *args) -> None:
            print(fmt % args, flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"webhook receiver on :{port} -> {path}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
