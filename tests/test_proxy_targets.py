"""Proxy asset selection uses release platform names on both host architectures."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class ProxyTargetTests(unittest.TestCase):
    def test_supported_profiles_resolve_and_reuse_the_pinned_native_asset(self):
        catalog = SOURCE / "deployment/proxy/mihomo.tsv"
        versions = {row[2]: row[1] for row in
                    (line.split("|") for line in catalog.read_text().splitlines())
                    if row[0] == "mihomo"}
        with tempfile.TemporaryDirectory(prefix="dotfiles-proxy-target-", dir="/tmp") as temporary:
            home = Path(temporary)
            binary = home / ".local/share/mihomo/bin/mihomo"
            binary.parent.mkdir(parents=True)
            for platform, release in (("linux", "linux"), ("wsl", "linux"), ("macos", "darwin")):
                for machine, arch in (("x86_64", "amd64"), ("arm64", "arm64")):
                    target = f"{release}-{arch}"
                    with self.subTest(platform=platform, machine=machine):
                        binary.write_text(f"#!/bin/sh\necho 'Mihomo v{versions[target]}'\n")
                        binary.chmod(0o755)
                        script = (
                            "set -euo pipefail\n"
                            f"DEPLOY_SOURCE='{SOURCE}'\nDEPLOY_PLATFORM='{platform}'\n"
                            f"export HOME='{home}' XDG_CACHE_HOME='{home / 'cache'}'\n"
                            "fail() { echo \"$*\" >&2; exit 1; }\n"
                            f"uname() {{ echo '{machine}'; }}\n"
                            "curl() { echo unexpected-download >&2; exit 97; }\n"
                            f"source '{SOURCE}/deployment/proxy.sh'\n"
                            "proxy_target\ninstall_proxy_binary\n")
                        result = subprocess.run(["/bin/bash", "-c", script],
                                                capture_output=True, text=True, timeout=20)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, target)
                        self.assertFalse((home / "cache").exists())
