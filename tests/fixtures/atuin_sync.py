"""Local Atuin 18.23 protocol fixture; synthetic accounts and encrypted records only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlparse


class AtuinSyncFixture:
    def __init__(self):
        self.account = None
        self.records = {}
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *arguments):
                pass  # Never write synthetic credentials into test logs.

            def reply(self, value, status=200):
                payload = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Atuin-Version", "18.23.0")
                self.end_headers()
                self.wfile.write(payload)

            def authenticated(self):
                if self.headers.get("Authorization") != "Token synthetic-session-token":
                    self.reply({"reason": "invalid synthetic session"}, 401)
                    return False
                return True

            def do_GET(self):
                url = urlparse(self.path)
                if url.path.startswith("/user/"):
                    return self.reply({}, 200 if fixture.account else 404)
                if url.path == "/api/v0/capabilities":
                    return self.reply({"capabilities": {}, "token": "synthetic-capabilities"})
                if not self.authenticated():
                    return
                if url.path == "/api/v0/record":
                    hosts = {}
                    for record in fixture.records.values():
                        tags = hosts.setdefault(record["host"]["id"], {})
                        tags[record["tag"]] = max(tags.get(record["tag"], 0), record["idx"])
                    return self.reply({"hosts": hosts})
                if url.path == "/api/v0/record/next":
                    query = parse_qs(url.query)
                    host, tag = query["host"][0], query["tag"][0]
                    start, count = int(query.get("start", [0])[0]), int(query["count"][0])
                    records = sorted((record for record in fixture.records.values()
                                      if record["host"]["id"] == host and record["tag"] == tag
                                      and record["idx"] >= start), key=lambda record: record["idx"])
                    return self.reply(records[:count])
                if url.path == "/api/v0/me":
                    return self.reply({"username": fixture.account["username"]})
                self.reply({"reason": "unimplemented synthetic endpoint"}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/register":
                    fixture.account = body
                    return self.reply({"session": "synthetic-session-token"})
                if self.path == "/login":
                    if fixture.account and all(body[name] == fixture.account[name] for name in ("username", "password")):
                        return self.reply({"session": "synthetic-session-token"})
                    return self.reply({"reason": "invalid synthetic account"}, 401)
                if not self.authenticated():
                    return
                if self.path == "/api/v0/record":
                    for record in body:
                        fixture.records[record["id"]] = record
                    return self.reply({})
                self.reply({"reason": "unimplemented synthetic endpoint"}, 404)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.address = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *arguments):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
