"""Proxy catalog and provisioning checks without network access."""
import hashlib
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        self.skills = self.root / "skills"
        shutil.copytree(SOURCE / "tests/fixtures/skill-library", self.skills)
        self.env = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                    "DOTFILES_CHEZMOI_BIN": self.chezmoi or "",
                    "DOTFILES_SKILLS_DIR": str(self.skills)}

    def deploy(self, *arguments):
        if not self.chezmoi:
            self.skipTest("actual apply requires chezmoi")
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--source", str(SOURCE), "--home", str(self.home),
                               "--platform", "linux", "--role", "workstation",
                               *arguments],
                              cwd=SOURCE, env=self.env, capture_output=True,
                              text=True, timeout=120)

    def test_catalog_pins_one_https_digest_per_architecture(self):
        rows = [line.split("|") for line in
                (SOURCE / "deployment/proxy/mihomo.tsv").read_text().splitlines()
                if line and not line.startswith("#")]
        self.assertEqual({row[2] for row in rows}, {"amd64", "arm64"})
        for name, version, arch, url, digest in rows:
            self.assertEqual(name, "mihomo")
            self.assertTrue(url.startswith("https://"))
            self.assertIn(f"v{version}", url)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_apply_installs_wrappers_scripts_secret_and_unit(self):
        result = self.deploy("--apply-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        scripts = self.home / ".local/share/dotfiles/proxy/scripts"
        for name in ("refresh-profile.sh", "run-mihomo.sh", "run-mihomo-supervised.sh",
                     "configure-mihomo.py", "apply-us-routing-policy.py",
                     "restrict-proxy-groups.py"):
            path = scripts / name
            self.assertTrue(path.is_file(), name)
            self.assertTrue(path.stat().st_mode & 0o111, name)
        startup = self.home / ".local/share/dotfiles/proxy/config/startup.env"
        self.assertIn("MIHOMO_MODE=rule", startup.read_text())
        secret = self.home / ".local/share/mihomo/subscription-url"
        self.assertEqual(secret.read_text().strip(), "REPLACE_ME")
        self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
        for name in ("with-proxy", "direct"):
            wrapper = self.home / f".local/bin/{name}"
            self.assertTrue(wrapper.is_file(), name)
            self.assertTrue(wrapper.stat().st_mode & 0o111, name)
        unit = self.home / ".config/systemd/user/mihomo.service"
        self.assertIn("run-mihomo-supervised.sh", unit.read_text())

    def test_plan_reports_proxy_only_when_requested(self):
        if not self.chezmoi:
            self.skipTest("plan requires chezmoi")
        plain = self.deploy("--plan")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertFalse(__import__("json").loads(plain.stdout)["proxy"])
        selected = self.deploy("--plan", "--proxy")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        plan = __import__("json").loads(selected.stdout)
        self.assertTrue(plan["proxy"])
        self.assertIn("install-proxy", plan["actions"])

    def test_binary_install_verifies_the_pin_and_replaces_stale_binary(self):
        if os.uname().machine not in ("x86_64", "amd64"):
            self.skipTest("fixture pins the amd64 asset")
        source = self.root / "source"
        catalog = source / "deployment/proxy/mihomo.tsv"
        catalog.parent.mkdir(parents=True)
        payload = gzip.compress(b"#!/bin/sh\necho 'Mihomo Meta v1.19.29'\n")
        asset = self.root / "mihomo.gz"
        asset.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        catalog.write_text(f"mihomo|1.19.29|amd64|file://{asset}|{digest}\n")
        script = self.root / "run.sh"
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{source}'\n"
            f"HOME='{self.root}/home'\n"
            f"export XDG_CACHE_HOME='{self.root}/cache'\n"
            f"mkdir -p \"$HOME\"\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            f"source '{SOURCE}/deployment/proxy.sh'\n"
            "install_proxy_binary\n"
            "test -x \"$HOME/.local/share/mihomo/bin/mihomo\"\n",
            encoding="utf-8")
        result = subprocess.run(["/bin/bash", str(script)], env=dict(os.environ),
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("v1.19.29", result.stdout)
        binary = self.root / "home/.local/share/mihomo/bin/mihomo"
        self.assertTrue(binary.stat().st_mode & 0o111)

        # A digest mismatch must fail on a fresh install.
        binary.unlink()
        catalog.write_text(f"mihomo|1.19.29|amd64|file://{asset}|{'0' * 64}\n")
        result = subprocess.run(["/bin/bash", str(script)], env=dict(os.environ),
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
