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
