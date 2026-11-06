"""First-use proxy preparation runs before Chezmoi or managed Python exists."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class ProxyBootstrapHelperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-helpers-", dir="/tmp")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.tools = self.home / "tools"
        self.tools.mkdir()
        self.env = {"HOME": str(self.home), "PATH": str(self.tools) + ":/usr/bin:/bin",
                    "XDG_CACHE_HOME": str(self.home / ".cache"), "TMPDIR": str(self.home)}

    def run_proxy(self, body):
        script = ("set -euo pipefail\n"
                  f"DEPLOY_SOURCE={shlex.quote(str(SOURCE))}\n"
                  f"DEPLOY_HOME={shlex.quote(str(self.home))}\n"
                  "fail() { echo \"$*\" >&2; exit 1; }\n"
                  f"source {shlex.quote(str(SOURCE / 'deployment/payload.sh'))}\n"
                  f"source {shlex.quote(str(SOURCE / 'deployment/proxy.sh'))}\n" + body)
        return subprocess.run(["/bin/bash", "-c", script], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_fresh_helpers_are_regular_executable_copies_and_clean_up_without_proxy(self):
        result = self.run_proxy(
            'scripts=$(deploy_proxy_scripts)\n'
            'test -x "$scripts/refresh-profile.sh"\n'
            'test -x "$scripts/configure-mihomo.py"\n'
            'test -f "$scripts/../config/startup.env"\n'
            'printf "%s\\n" "$scripts"\n'
            'stop_deployment_proxy\n'
            'test ! -e "$scripts"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.home / ".cache/dotfiles/proxy-scripts"), result.stdout)
        self.assertFalse((self.home / ".local/share/dotfiles/proxy").exists())

    def test_fresh_helpers_build_a_real_us_profile_before_source_application(self):
        root = self.home / ".local/share/mihomo"
        root.mkdir(parents=True)
        self.env["MIHOMO_SUBSCRIPTION_URL"] = "https://fixture.invalid/profile"
        profile = self.home / "subscription.yaml"
        profile.write_text(
            "mixed-port: 7890\nproxies:\n"
            "  - {name: US-1, type: socks5, server: us.invalid, port: 1234}\n"
            "  - {name: HK-1, type: socks5, server: hk.invalid, port: 1234}\n"
            "proxy-groups:\n  - {name: AUTO, type: select, proxies: [US-1, HK-1, DIRECT]}\n"
            "rules:\n  - MATCH,AUTO\n")
        curl = self.tools / "curl"
        curl.write_text("#!/bin/sh\nwhile [ \"$1\" != --output ]; do shift; done\n"
                        f"cp {shlex.quote(str(profile))} \"$2\"\n")
        curl.chmod(0o755)
        result = self.run_proxy(
            'deploy_proxy_subscription >/dev/null\n'
            'DEPLOY_PROXY_PORT=7895\nDEPLOY_PROXY_CONTROLLER_PORT=9091\n'
            'deploy_proxy_profile\nstop_deployment_proxy\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = root / "profiles/deployment-config.yaml"
        text = generated.read_text()
        self.assertIn("external-controller: 127.0.0.1:9091", text)
        self.assertIn("mixed-port: 7895", text)
        self.assertIn("MATCH,GLOBAL", text)
        group = next(line for line in text.splitlines() if "name: AUTO" in line)
        self.assertIn("US-1", group)
        self.assertNotIn("HK-1", group)
        self.assertFalse((root / "profiles/config.yaml").exists())
        self.assertEqual((root / "subscription-url").read_bytes(), b"https://fixture.invalid/profile\n")

    def test_detected_user_client_is_not_reused_by_deployment(self):
        root = self.home / ".local/share/mihomo"
        (root / "bin").mkdir(parents=True)
        binary = root / "bin/mihomo"
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
        result = self.run_proxy(
            'DEPLOY_PROXY_PORTS="7890 7891"\n'
            'deploy_proxy_client_running() { return 0; }\n'
            'deploy_proxy_port_free() { [ "$1" != 7890 ] && [ ! -e "$HOME/listening" ]; }\n'
            'deploy_proxy_answers() { return 0; }\n'
            'deploy_proxy_subscription() { printf fixture; }\n'
            'install_proxy_binary() { :; }\n'
            'deploy_proxy_scripts() { printf fixture; }\n'
            'deploy_proxy_profile() { touch "$HOME/profile-built"; printf fixture.yaml; }\n'
            'deploy_proxy_select_us_node() { touch "$HOME/us-node-selected"; }\n'
            'sleep() { touch "$HOME/listening"; }\n'
            'deploy_proxy_ensure\n'
            'printf "selected=%s\\n" "$DEPLOY_PROXY_URL"\n'
            'stop_deployment_proxy\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("selected=http://127.0.0.1:7891", result.stdout)
        self.assertTrue((self.home / "profile-built").exists())
        self.assertTrue((self.home / "us-node-selected").exists())

    def test_node_selection_probes_the_owned_http_port(self):
        python = self.tools / "python3"
        python.write_text('#!/bin/sh\nprintf "%s\\n%s\\n" "$PROXY_HTTP" "$MIHOMO_CONTROLLER" > "$HOME/selection-env"\n')
        python.chmod(0o755)
        self.env["PROXY_HTTP"] = "http://127.0.0.1:19999"
        result = self.run_proxy(
            'DEPLOY_PROXY_PORT=7891\nDEPLOY_PROXY_CONTROLLER_PORT=9092\n'
            'deploy_proxy_select_us_node fixture\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / "selection-env").read_text().splitlines(),
                         ["http://127.0.0.1:7891", "http://127.0.0.1:9092"])
