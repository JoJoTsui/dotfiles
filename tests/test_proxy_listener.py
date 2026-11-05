"""Unrelated TCP services must not become deployment proxies."""
import http.server
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Unix deployment proxy")
class ProxyListenerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-listener-", dir="/tmp")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def ensure_proxy(self, port, body=""):
        script = ("set -euo pipefail\n"
                  f"DEPLOY_SOURCE='{SOURCE}'\nexport HOME='{self.home}'\n"
                  "fail() { echo \"$*\" >&2; exit 1; }\n"
                  f"source '{SOURCE}/deployment/proxy.sh'\n"
                  f"DEPLOY_PROXY_PORTS='{port}'\n"
                  "deploy_proxy_subscription() { return 1; }\n"
                  "deploy_proxy_client_running() { return 1; }\n" + body +
                  "\ndeploy_proxy_ensure\nprintf 'selected=%s\\n' \"$DEPLOY_PROXY_URL\"\n")
        return subprocess.run(["/bin/bash", "-c", script],
                              env={"HOME": str(self.home), "PATH": "/usr/bin:/bin", "NO_PROXY": "*"},
                              capture_output=True, text=True, timeout=15)

    def test_ordinary_http_server_is_rejected_as_a_proxy(self):
        requests = []

        class OrdinaryServer(http.server.BaseHTTPRequestHandler):
            def do_CONNECT(self):
                requests.append(self.path)
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *arguments):
                pass

        with http.server.HTTPServer(("127.0.0.1", 0), OrdinaryServer) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = self.ensure_proxy(server.server_port)
            finally:
                server.shutdown()
                thread.join(timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("selected=\n", result.stdout)
        self.assertEqual(requests, ["www.gstatic.com:443"])

    def test_successful_proxy_probe_is_reused_and_bypass_is_disabled(self):
        log = self.home / "curl-arguments"
        result = self.ensure_proxy(19090,
            "deploy_proxy_port_free() { return 1; }\n"
            f"curl() {{ printf '%s\\n' \"$@\" > '{log}'; printf 204; }}\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("selected=http://127.0.0.1:19090", result.stdout)
        arguments = log.read_text().splitlines()
        self.assertEqual(arguments[arguments.index("--proxy") + 1], "http://127.0.0.1:19090")
        self.assertEqual(arguments[arguments.index("--noproxy") + 1], "")

    def test_unexpected_success_status_is_not_adopted(self):
        result = self.ensure_proxy(19090,
            "deploy_proxy_port_free() { return 1; }\ncurl() { printf 200; }\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("selected=\n", result.stdout)
