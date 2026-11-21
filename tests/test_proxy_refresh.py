"""A proxy refresh publishes a replacement only after it is staged and validated."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPTS = SOURCE / "dot_local/share/dotfiles/proxy/scripts"

# The profile the device is serving with before the refresh.
ACTIVE_PROFILE = """mixed-port: 7890
external-controller: 127.0.0.1:9090
proxies:
  - {name: "US-old", type: ss, server: old.example.invalid, port: 443, cipher: aes-128-gcm, password: fixture}
proxy-groups:
  - {name: GLOBAL, type: select, proxies: ["US-old"]}
rule-providers:
  proxy:
    type: http
    behavior: domain
    url: "https://fixture.invalid/proxy.txt"
    path: ./ruleset/proxy.yaml
    interval: 86400
rules:
  - 'DOMAIN,localhost,DIRECT'
  - 'MATCH,GLOBAL'
"""

# A fetched profile with no US leaf. It carries every Clash key, so only the
# region conversion can reject it.
FETCHED_WITHOUT_US = """mixed-port: 7890
proxies:
  - {name: "HK-1", type: ss, server: hk.example.invalid, port: 443, cipher: aes-128-gcm, password: fixture}
proxy-groups:
  - {name: GLOBAL, type: select, proxies: ["HK-1"]}
rules:
  - 'MATCH,DIRECT'
"""

# The same profile with a US leaf, so every conversion step succeeds.
FETCHED_WITH_US = """mixed-port: 7890
proxies:
  - {name: "US-new", type: ss, server: new.example.invalid, port: 443, cipher: aes-128-gcm, password: fixture}
proxy-groups:
  - {name: GLOBAL, type: select, proxies: ["US-new"]}
rules:
  - 'MATCH,DIRECT'
"""

CURL_STUB = """#!/bin/sh
# Fixture curl: publish the configured profile to the requested output path.
output=
while [ $# -gt 0 ]; do
    case $1 in
        --output) output=$2; shift 2 ;;
        --user-agent) shift 2 ;;
        *) shift ;;
    esac
done
[ -n "$output" ] || exit 2
cp "$DOTFILES_TEST_PROFILE_FIXTURE" "$output"
: > "$DOTFILES_TEST_FETCH_MARKER"
"""


class ProxyRefreshTests(unittest.TestCase):
    """The deployment refresh keeps the last working profile until a valid one exists."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-refresh-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.fixture = self.root / "fetched.yaml"
        self.marker = self.root / "fetched.marker"
        self.stub = self.tools / "curl"
        self.stub.write_text(CURL_STUB, encoding="utf-8")
        self.stub.chmod(0o755)
        self.install_scripts()
        self.secret = self.home / ".local/share/mihomo/subscription-url"
        self.secret.parent.mkdir(parents=True)
        self.secret.write_text("https://fixture.invalid/subscription\n", encoding="utf-8")
        self.secret.chmod(0o600)
        self.profiles = self.home / ".local/share/mihomo/profiles"
        self.profiles.mkdir(parents=True)
        self.active = self.profiles / "config.yaml"
        self.active.write_text(ACTIVE_PROFILE, encoding="utf-8")
        self.active.chmod(0o600)

    def install_scripts(self):
        """The managed scripts, named the way the deployment stages them."""
        scripts = self.home / ".local/share/dotfiles/proxy/scripts"
        scripts.mkdir(parents=True)
        for source in sorted(SCRIPTS.glob("executable_*")):
            target = scripts / source.name[len("executable_"):]
            target.write_bytes(source.read_bytes())
            target.chmod(0o755)

    def write_fixture(self, text):
        self.fixture.write_text(text, encoding="utf-8")
        if self.marker.exists():
            self.marker.unlink()

    def run_refresh(self):
        """Refresh through the deployment command the proxy step uses."""
        script = self.root / "refresh.sh"
        script.write_text(
            "set -euo pipefail\n"
            "fail() { printf '%s\\n' \"$*\" >&2; exit 1; }\n"
            f"DEPLOY_SOURCE={shlex.quote(str(SOURCE))}\n"
            f"export HOME={shlex.quote(str(self.home))}\n"
            f"source {shlex.quote(str(SOURCE / 'deployment/proxy.sh'))}\n"
            "refresh_proxy_profile\n",
            encoding="utf-8")
        environment = {
            "HOME": str(self.home),
            "PATH": f"{self.tools}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "DOTFILES_TEST_PROFILE_FIXTURE": str(self.fixture),
            "DOTFILES_TEST_FETCH_MARKER": str(self.marker),
        }
        return subprocess.run(["/bin/bash", str(script)], env=environment,
                              capture_output=True, text=True, timeout=60)

    def profile_entries(self):
        return sorted(entry.name for entry in self.profiles.iterdir())

    def test_a_failed_conversion_preserves_the_active_profile(self):
        self.write_fixture(FETCHED_WITHOUT_US)
        result = self.run_refresh()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.marker.exists(), "the fetch must have run")
        self.assertEqual(self.active.read_text(encoding="utf-8"), ACTIVE_PROFILE)
        self.assertEqual(self.active.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.profile_entries(), ["config.yaml"])

    def test_a_valid_retry_publishes_the_replacement(self):
        self.write_fixture(FETCHED_WITHOUT_US)
        failed = self.run_refresh()
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        self.assertEqual(self.active.read_text(encoding="utf-8"), ACTIVE_PROFILE)

        self.write_fixture(FETCHED_WITH_US)
        result = self.run_refresh()
        self.assertEqual(result.returncode, 0, result.stderr)
        published = self.active.read_text(encoding="utf-8")
        self.assertIn("US-new", published)
        self.assertNotIn("US-old", published)
        self.assertIn("rule-providers:", published)
        self.assertIn("MATCH,GLOBAL", published)
        self.assertEqual(self.active.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.profile_entries(), ["config.yaml"])


if __name__ == "__main__":
    unittest.main()
