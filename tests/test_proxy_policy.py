"""Real subscription policies preserve valid US SOCKS5 nodes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "dot_local/share/dotfiles/proxy/scripts/executable_restrict-proxy-groups.py"


class ProxyPolicyTests(unittest.TestCase):
    def test_socks5_nodes_participate_in_region_filtering(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-proxy-policy-", dir="/tmp") as temporary:
            profile = Path(temporary) / "profile.yaml"
            profile.write_text(
                "proxies:\n  - {name: US-1, type: socks5, server: us.invalid, port: 1234}\n"
                "  - {name: HK-1, type: socks5, server: hk.invalid, port: 1234}\n"
                "proxy-groups:\n  - {name: AUTO, type: select, proxies: [US-1, HK-1, DIRECT]}\n"
                "rules:\n  - MATCH,AUTO\n")
            result = subprocess.run([sys.executable, str(SCRIPT), "us", str(profile)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("US-1", profile.read_text())
            self.assertNotIn("HK-1", profile.read_text())
