#!/usr/bin/env python3
"""A fake Magpie gateway for the isolated real-CLI checks.

It answers the endpoints the pinned CLI asks for, with synthetic data only,
and logs every request so the evidence shows which address the CLI used.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = os.environ["FAKE_GATEWAY_LOG"]
MODELS = ["openai/gpt-6.1-sol", "openai/gpt-6.1-terra"]


def log(line):
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        log("GET " + self.path)
        if self.path.startswith("/v1/models"):
            self.reply(200, {"object": "list",
                             "data": [{"id": model} for model in MODELS]})
            return
        self.reply(200, {"object": "list", "data": []})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        log("POST " + self.path)
        self.reply(200, {"id": "chatcmpl-fake", "object": "chat.completion",
                         "choices": [{"index": 0, "message": {"role": "assistant",
                                                             "content": "pong"},
                                      "finish_reason": "stop"}]})

    def log_message(self, *arguments):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log("listening 127.0.0.1:%d" % port)
    server.serve_forever()
