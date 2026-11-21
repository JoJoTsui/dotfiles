"""A proxy refresh publishes a replacement only after staging and validation."""
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

# A profile whose port is not a number. Mihomo cannot load it, so it must
# never replace the working profile.
FETCHED_WITH_INVALID_PORT = """mixed-port: not-a-number
proxies:
  - {name: "US-new", type: ss, server: new.example.invalid, port: 443, cipher: aes-128-gcm, password: fixture}
proxy-groups:
  - {name: GLOBAL, type: select, proxies: ["US-new"]}
rules:
  - 'MATCH,DIRECT'
"""

# A profile whose credential is not a string. Mihomo refuses it, and the
# refusal quotes the credential, so the refresh must not relay that message.
FETCHED_WITH_UNQUOTED_CREDENTIAL = """mixed-port: 7890
proxies:
  - {name: "US-new", type: ss, server: new.example.invalid, port: 443, cipher: aes-128-gcm, password: 123456}
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

# Fixture curl for a failed fetch: it reports the URL it was given, the way
# a curl error can, so the refresh must not relay it.
FAILING_CURL_STUB = """#!/bin/sh
printf 'curl: (22) The requested URL returned error: 403: %s\\n' "$DOTFILES_TEST_SUBSCRIPTION_URL" >&2
exit 22
"""

# A stand-in for the managed Mihomo binary. Mihomo parses a configuration
# before it loads it, so a value of the wrong type is refused with a message
# that quotes the value. The validated path is recorded so a test can see
# which copy was checked.
MIHOMO_STUB = """#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

arguments = sys.argv[1:]
if "-f" not in arguments:
    print("usage: mihomo -d <dir> -t -f <profile>", file=sys.stderr)
    raise SystemExit(2)
profile = Path(arguments[arguments.index("-f") + 1])
text = profile.read_text(encoding="utf-8")
marker = os.environ.get("DOTFILES_TEST_VALIDATOR_MARKER")
if marker:
    Path(marker).write_text(str(profile), encoding="utf-8")
port = re.search(r"^mixed-port:[ \\t]*(\\S+)", text, re.MULTILINE)
value = port.group(1) if port else ""
if not value.isdigit():
    print(f"yaml: cannot unmarshal !!str `{value}` into int", file=sys.stderr)
    raise SystemExit(1)
credential = re.search(r"password:[ \\t]*([^\\s,}]+)", text, re.MULTILINE)
if credential and credential.group(1).isdigit():
    print(f"yaml: cannot unmarshal !!int `{credential.group(1)}` into string", file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(0)
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
        self.validator_marker = self.root / "validated.marker"
        self.stub = self.tools / "curl"
        self.stub.write_text(CURL_STUB, encoding="utf-8")
        self.stub.chmod(0o755)
        self.install_scripts()
        self.install_validator()
        self.secret = self.home / ".local/share/mihomo/subscription-url"
        self.secret.parent.mkdir(parents=True, exist_ok=True)
        self.secret.write_text("https://fixture.invalid/subscription\n", encoding="utf-8")
        self.secret.chmod(0o600)
        self.profiles = self.home / ".local/share/mihomo/profiles"
        self.profiles.mkdir(parents=True, exist_ok=True)
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

    def install_validator(self):
        """The managed Mihomo binary, which decides whether a profile is usable."""
        binary = self.home / ".local/share/mihomo/bin/mihomo"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text(MIHOMO_STUB, encoding="utf-8")
        binary.chmod(0o755)

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
            "DOTFILES_TEST_VALIDATOR_MARKER": str(self.validator_marker),
            "DOTFILES_TEST_SUBSCRIPTION_URL": "https://fixture.invalid/subscription",
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

    def test_a_profile_mihomo_cannot_load_never_replaces_the_working_one(self):
        self.write_fixture(FETCHED_WITH_INVALID_PORT)
        result = self.run_refresh()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.marker.exists(), "the fetch must have run")
        self.assertEqual(self.active.read_text(encoding="utf-8"), ACTIVE_PROFILE)
        self.assertEqual(self.profile_entries(), ["config.yaml"])

    def test_the_staged_copy_is_validated_before_it_is_published(self):
        self.write_fixture(FETCHED_WITH_US)
        result = self.run_refresh()
        self.assertEqual(result.returncode, 0, result.stderr)
        validated = self.validator_marker.read_text(encoding="utf-8")
        self.assertNotEqual(validated, str(self.active),
                            "the validator must check the staged copy, not the published profile")
        self.assertIn(".staged.", validated)

    def test_a_missing_transform_stops_the_refresh(self):
        scripts = self.home / ".local/share/dotfiles/proxy/scripts"
        for name in ("restrict-proxy-groups.py", "apply-us-routing-policy.py"):
            with self.subTest(transform=name):
                self.write_fixture(FETCHED_WITH_US)
                transform = scripts / name
                keep = transform.read_bytes()
                transform.unlink()
                try:
                    result = self.run_refresh()
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertEqual(self.active.read_text(encoding="utf-8"), ACTIVE_PROFILE)
                    self.assertEqual(self.profile_entries(), ["config.yaml"])
                finally:
                    transform.write_bytes(keep)
                    transform.chmod(0o755)

    def test_a_transform_that_is_not_executable_stops_the_refresh(self):
        transform = self.home / ".local/share/dotfiles/proxy/scripts/restrict-proxy-groups.py"
        transform.chmod(0o644)
        self.write_fixture(FETCHED_WITH_US)
        result = self.run_refresh()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.active.read_text(encoding="utf-8"), ACTIVE_PROFILE)
        self.assertEqual(self.profile_entries(), ["config.yaml"])

    def test_a_destination_that_is_not_a_regular_file_is_refused(self):
        self.active.unlink()
        self.active.mkdir()
        self.write_fixture(FETCHED_WITH_US)
        result = self.run_refresh()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.active.is_dir())
        self.assertEqual(list(self.active.iterdir()), [],
                         "the staged copy must not be nested inside the destination")
        self.assertFalse(self.marker.exists(), "a refused destination must not be fetched for")

    def test_the_refresh_does_not_relay_a_rejected_credential(self):
        self.write_fixture(FETCHED_WITH_UNQUOTED_CREDENTIAL)
        result = self.run_refresh()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("123456", result.stderr + result.stdout)
        self.assertEqual(self.active.read_text(encoding="utf-8"), ACTIVE_PROFILE)

    def test_a_failed_fetch_does_not_relay_the_subscription_url(self):
        self.stub.write_text(FAILING_CURL_STUB, encoding="utf-8")
        self.stub.chmod(0o755)
        result = self.run_refresh()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("fixture.invalid/subscription", result.stderr + result.stdout)
        self.assertEqual(self.active.read_text(encoding="utf-8"), ACTIVE_PROFILE)
        self.assertEqual(self.profile_entries(), ["config.yaml"])


if __name__ == "__main__":
    unittest.main()
