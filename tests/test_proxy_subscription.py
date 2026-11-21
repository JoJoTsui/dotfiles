"""Subscription refresh accepts both managed and older unterminated URL files."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "dot_local/share/dotfiles/proxy/scripts/executable_refresh-profile.sh"

# A profile Mihomo can load: it carries a US leaf, so the region restriction
# and the routing policy both accept it.
FIXTURE_PROFILE = (
    "mixed-port: 7890\n"
    "proxies:\n"
    "  - {name: US-1, type: socks5, server: us.invalid, port: 1234}\n"
    "proxy-groups:\n"
    "  - {name: AUTO, type: select, proxies: [US-1]}\n"
    "rules:\n"
    "  - MATCH,AUTO\n"
)

# A stand-in for the managed Mihomo binary, which decides whether a
# configuration is usable.
VALIDATOR_STUB = """import re
import sys
from pathlib import Path

arguments = sys.argv[1:]
if "-f" not in arguments:
    raise SystemExit(2)
text = Path(arguments[arguments.index("-f") + 1]).read_text(encoding="utf-8")
port = re.search(r"^mixed-port:[ \\t]*(\\S+)", text, re.MULTILINE)
raise SystemExit(0 if port and port.group(1).isdigit() else 1)
"""


class ProxySubscriptionTests(unittest.TestCase):
    def test_refresh_accepts_url_with_or_without_trailing_newline(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-proxy-url-", dir="/tmp") as temporary:
            root = Path(temporary)
            tools = root / "bin"
            tools.mkdir()
            log = root / "curl.json"
            curl = tools / "curl"
            curl.write_text("#!" + sys.executable + "\n"
                            "import json, pathlib, sys\n"
                            f"pathlib.Path({str(log)!r}).write_text(json.dumps(sys.argv[1:]))\n"
                            "output = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n"
                            f"output.write_text({FIXTURE_PROFILE!r})\n")
            curl.chmod(0o755)
            validator = tools / "mihomo"
            validator.write_text("#!" + sys.executable + "\n" + VALIDATOR_STUB)
            validator.chmod(0o755)
            profiles = root / "runtime/profiles"
            profiles.mkdir(parents=True)
            secret = root / "subscription-url"
            url = "https://fixture.invalid/profile?token=synthetic&format=clash"
            env = {"HOME": str(root), "PATH": str(tools) + ":/usr/bin:/bin", "TMPDIR": str(root),
                   "INSTALL_ROOT": str(root / "runtime"), "SUBSCRIPTION_URL_FILE": str(secret),
                   "MIHOMO_VALIDATOR": str(validator)}
            for suffix in ("", "\n"):
                with self.subTest(terminated=bool(suffix)):
                    secret.write_text(url + suffix)
                    result = subprocess.run(["/bin/bash", str(SCRIPT)], env=env,
                                            capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(log.read_text())[-1], url)
                    self.assertEqual((profiles / "config.yaml").stat().st_mode & 0o777, 0o600)
            # The transforms beside the script run in this layout too: the
            # published profile carries the routing policy, not the rules the
            # subscription shipped with.
            published = (profiles / "config.yaml").read_text(encoding="utf-8")
            self.assertIn("rule-providers:", published)
            self.assertIn("MATCH,GLOBAL", published)
            log.unlink()
            secret.write_text("")
            result = subprocess.run(["/bin/bash", str(SCRIPT)], env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("empty", result.stderr)
            self.assertFalse(log.exists())
