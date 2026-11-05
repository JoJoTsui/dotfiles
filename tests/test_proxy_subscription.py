"""Subscription refresh accepts both managed and older unterminated URL files."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "dot_local/share/dotfiles/proxy/scripts/executable_refresh-profile.sh"


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
                            "output.write_text('mixed-port: 7890\\nproxies: []\\nproxy-groups: []\\nrules: []\\n')\n")
            curl.chmod(0o755)
            profiles = root / "runtime/profiles"
            profiles.mkdir(parents=True)
            secret = root / "subscription-url"
            url = "https://fixture.invalid/profile?token=synthetic&format=clash"
            env = {"HOME": str(root), "PATH": str(tools) + ":/usr/bin:/bin", "TMPDIR": str(root),
                   "INSTALL_ROOT": str(root / "runtime"), "SUBSCRIPTION_URL_FILE": str(secret)}
            for suffix in ("", "\n"):
                with self.subTest(terminated=bool(suffix)):
                    secret.write_text(url + suffix)
                    result = subprocess.run(["/bin/bash", str(SCRIPT)], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(log.read_text())[-1], url)
                    self.assertEqual((profiles / "config.yaml").stat().st_mode & 0o777, 0o600)
            log.unlink()
            secret.write_text("")
            result = subprocess.run(["/bin/bash", str(SCRIPT)], env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("empty", result.stderr)
            self.assertFalse(log.exists())
