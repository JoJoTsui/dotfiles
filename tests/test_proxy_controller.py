"""The deployed controller helper carries its own route-health implementation."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "dot_local/share/dotfiles/proxy/scripts/executable_configure-mihomo.py"


class ProxyControllerTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("dotfiles_proxy_controller", SCRIPT)
        self.controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.controller)

    def test_health_uses_the_selected_proxy_despite_inherited_bypass(self):
        completed = subprocess.CompletedProcess([], 0, "203.0.113.8\n", "")
        with mock.patch.dict(os.environ, {"NO_PROXY": "*"}), mock.patch.object(
                self.controller.subprocess, "run", return_value=completed) as run:
            self.assertEqual(self.controller.route_health("http://127.0.0.1:7892"),
                             (True, "203.0.113.8"))
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--proxy") + 1], "http://127.0.0.1:7892")
        self.assertEqual(arguments[arguments.index("--noproxy") + 1], "")

    def test_failed_or_invalid_exit_responses_are_unhealthy(self):
        for response in (subprocess.CalledProcessError(7, "curl"),
                         subprocess.CompletedProcess([], 0, "captive portal", "")):
            with self.subTest(response=type(response).__name__):
                options = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
                with mock.patch.object(self.controller.subprocess, "run", **options):
                    self.assertEqual(self.controller.route_health("http://127.0.0.1:7892"), (False, ""))

    def test_controller_startup_has_no_undeployed_import_dependency(self):
        with mock.patch.dict(os.environ, {"STARTUP_ENV": "/nonexistent", "MIHOMO_PREFER_REGION": ""}, clear=True), \
                mock.patch.object(self.controller, "wait_for_controller") as wait, \
                mock.patch.object(self.controller, "http") as request, \
                mock.patch.object(self.controller.sys, "argv", [str(SCRIPT)]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.controller.main(), 0)
        wait.assert_called_once_with("http://127.0.0.1:9090")
        request.assert_called_once_with("PATCH", "http://127.0.0.1:9090", "/configs", {"mode": "rule", "ipv6": True})

    def run_selection(self, healthy):
        """Run main() against a fake controller; return the pin order and result."""
        proxies = {
            "GLOBAL": {"type": "Selector", "now": "JP1", "all": ["US1", "US2", "JP1", "♻️自动选择"]},
            "US1": {"type": "SS"},
            "US2": {"type": "VMess"},
            "JP1": {"type": "Trojan"},
            "♻️自动选择": {"type": "URLTest"},
        }
        pinned = []

        def fake_http(method, base, path, payload=None, timeout=10.0):
            return {"proxies": proxies} if method == "GET" else {}

        def fake_pin(base, selector, name):
            pinned.append(name)

        def fake_health(proxy_url):
            return (bool(pinned) and pinned[-1] in healthy, "203.0.113.9" if pinned and pinned[-1] in healthy else "")

        environment = {"STARTUP_ENV": "/nonexistent", "MIHOMO_PREFER_REGION": "us",
                       "MIHOMO_PREFER_SELECTOR": "GLOBAL", "PROXY_HTTP": "http://127.0.0.1:7892"}
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(self.controller, "wait_for_controller"), \
                mock.patch.object(self.controller, "http", side_effect=fake_http), \
                mock.patch.object(self.controller, "pin_node", side_effect=fake_pin), \
                mock.patch.object(self.controller, "route_health", side_effect=fake_health), \
                mock.patch.object(self.controller.time, "sleep"), \
                mock.patch.object(self.controller.sys, "argv", [str(SCRIPT)]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            result = self.controller.main()
        return result, pinned, output.getvalue()

    def test_us_preference_wins_while_a_us_node_is_healthy(self):
        result, pinned, _ = self.run_selection(healthy={"US1", "US2", "JP1"})
        self.assertEqual(result, 0)
        self.assertEqual(set(pinned), {"US1", "US2"})
        self.assertNotIn("JP1", pinned)

    def test_only_other_regions_are_used_when_no_us_node_serves(self):
        result, pinned, output = self.run_selection(healthy={"JP1"})
        self.assertEqual(result, 0)
        self.assertEqual(pinned[-1], "JP1")
        self.assertIn("falling back to other regions", output)
        # A group is never pinned: its own choice would be measured, not a node.
        self.assertNotIn("♻️自动选择", pinned)
