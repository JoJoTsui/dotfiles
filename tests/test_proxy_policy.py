"""Real subscription policies preserve valid US SOCKS5 nodes and YAML."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "dot_local/share/dotfiles/proxy/scripts/executable_restrict-proxy-groups.py"
ROUTING_SCRIPT = SOURCE / "dot_local/share/dotfiles/proxy/scripts/executable_apply-us-routing-policy.py"


class ProxyPolicyTests(unittest.TestCase):
    def parse_yaml(self, profile):
        result = subprocess.run(
            [shutil.which("ruby"), "-rjson", "-ryaml", "-e",
             "puts JSON.generate(YAML.load_file(ARGV.fetch(0)))", str(profile)],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

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

    @unittest.skipUnless(shutil.which("ruby"), "YAML regression requires installed Ruby/Psych")
    def test_routing_policy_preserves_yaml_variants_and_neighboring_data(self):
        variants = (
            ("rules:\n  - MATCH,AUTO\n", "rule-providers:\n  old: {type: http}\n"),
            ("rules:\n- MATCH,AUTO\n", "rule-providers: # old providers\n  old: {type: http}\n"),
            ("rules: # provider rules\n- MATCH,AUTO\n", "rule-providers: {}\n"),
            ("rules: [] # provider rules\n", "rule-providers: {} # old providers\n"),
        )
        with tempfile.TemporaryDirectory(prefix="dotfiles-proxy-routing-", dir="/tmp") as temporary:
            profile = Path(temporary) / "profile.yaml"
            for rules, providers in variants:
                with self.subTest(rules=rules, providers=providers):
                    profile.write_text(
                        "mixed-port: 7890\nproxies:\n"
                        "  - {name: US-1, type: socks5, server: us.invalid, port: 1234}\n"
                        "proxy-groups:\n  - {name: AUTO, type: select, proxies: [US-1]}\n"
                        + providers + rules + "# Neighboring configuration\ndns:\n  enable: true\n  nameserver: [1.1.1.1]\n")
                    before = self.parse_yaml(profile)
                    result = subprocess.run([sys.executable, str(ROUTING_SCRIPT), str(profile)],
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    after = self.parse_yaml(profile)
                    self.assertEqual(after["rules"][-1], "MATCH,GLOBAL")
                    self.assertIn("DOMAIN,localhost,DIRECT", after["rules"])
                    self.assertNotIn("MATCH,AUTO", after["rules"])
                    self.assertEqual(len(after["rules"]), 27)
                    self.assertEqual(len(after["rule-providers"]), 13)
                    self.assertNotIn("old", after["rule-providers"])
                    for key in ("mixed-port", "proxies", "proxy-groups", "dns"):
                        self.assertEqual(after[key], before[key])
                    rewritten = profile.read_bytes()
                    repeated = subprocess.run([sys.executable, str(ROUTING_SCRIPT), str(profile)],
                                              capture_output=True, text=True, timeout=10)
                    self.assertEqual(repeated.returncode, 0, repeated.stderr)
                    self.assertEqual(profile.read_bytes(), rewritten)

    @unittest.skipUnless(shutil.which("ruby"), "YAML regression requires installed Ruby/Psych")
    def test_unsupported_yaml_forms_leave_the_profile_unchanged(self):
        variants = (
            "rules: [\n'MATCH,AUTO'\n]\n",
            "rule-providers: {\nold: {type: http}\n}\nrules: []\n",
            "rules: &shared ['MATCH,AUTO']\ncustom-rules: *shared\n",
            "rules:\n- MATCH,AUTO\ncustom:tag: keep\n",
            "rules: ['MATCH,AUTO']\n",
            "rule-providers: {old: {type: http}}\nrules: []\n",
            "rule-providers: { # }\nold: {type: http}\n}\nrules: []\n",
            "rule-providers: { # }\n  old: {type: http}\n}\nrules: []\n",
        )
        with tempfile.TemporaryDirectory(prefix="dotfiles-proxy-routing-", dir="/tmp") as temporary:
            profile = Path(temporary) / "profile.yaml"
            for text in variants:
                with self.subTest(profile=text):
                    profile.write_text("mixed-port: 7890\n" + text)
                    self.parse_yaml(profile)
                    before = profile.read_bytes()
                    result = subprocess.run([sys.executable, str(ROUTING_SCRIPT), str(profile)],
                                            capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("unsupported", result.stderr)
                    self.assertEqual(profile.read_bytes(), before)
