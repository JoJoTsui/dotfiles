"""The Herdr Codex launch gate must not require the legacy proxy stack.

`codex-herdr` gates every launch on `dotfiles-agent-health --quiet --codex`.
The launch route itself uses `with-proxy --if-available`, which runs the
command direct when no proxy endpoint is reachable, so the launch does not
need the legacy Mihomo controller or its U.S. egress. The narrow `--codex`
check therefore skips exactly that readiness and keeps everything else:
the Herdr server, the Codex binary, and the strict default and
`--before-restore` checks that host bring-up runs.

Everything here runs against stubs; no test opens a network connection.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
HEALTH = SOURCE / "dot_local/bin/executable_dotfiles-agent-health"
LAUNCHER = SOURCE / "dot_local/bin/executable_codex-herdr"
WITH_PROXY = SOURCE / "dot_local/bin/executable_with-proxy"


class CodexLaunchHealthTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-launch-health-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()

        # A Codex that reports its argv and the proxy variables it inherited.
        codex = self.bin / "codex"
        codex.write_text(
            '#!/bin/sh\n'
            'printf "codex %s\\n" "$*"\n'
            'printf "proxy %s\\n" "${HTTP_PROXY:-none}"\n', encoding="utf-8")
        codex.chmod(0o755)
        # Herdr answers the snapshot call the health check makes.
        herdr = self.bin / "herdr"
        herdr.write_text('#!/bin/sh\nexit 0\n', encoding="utf-8")
        herdr.chmod(0o755)
        # No proxy controller listens, so the readiness probes answer nothing.
        curl = self.bin / "curl"
        curl.write_text('#!/bin/sh\nprintf "000"\n', encoding="utf-8")
        curl.chmod(0o755)
        # No proxy endpoint is reachable, so with-proxy runs the command direct.
        nc = self.bin / "nc"
        nc.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        nc.chmod(0o755)
        # The real launcher, so the fallback route is the shipped one.
        proxy = self.bin / "with-proxy"
        shutil.copyfile(WITH_PROXY, proxy)
        proxy.chmod(0o755)

        self.env = os.environ.copy()
        self.env.update(
            HOME=str(self.home),
            PATH=f"{self.bin}:/usr/bin:/bin",
            DOTFILES_PLATFORM="linux",
            DOTFILES_AGENT_HEALTH=str(HEALTH),
            DOTFILES_WITH_PROXY=str(WITH_PROXY),
        )
        self.env.pop("HTTP_PROXY", None)
        self.env.pop("HTTPS_PROXY", None)

    def run_health(self, *arguments):
        return subprocess.run(
            ["/bin/bash", str(HEALTH), "--quiet", *arguments],
            env=self.env, cwd=self.home, capture_output=True, text=True, timeout=60)

    def test_codex_launch_check_skips_the_legacy_proxy_readiness(self):
        result = self.run_health("--codex")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_codex_launch_check_still_requires_herdr_and_codex(self):
        (self.bin / "herdr").unlink()
        result = self.run_health("--codex")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("herdr", result.stderr)
        (self.bin / "herdr").write_text('#!/bin/sh\nexit 0\n', encoding="utf-8")
        (self.bin / "herdr").chmod(0o755)
        (self.bin / "codex").unlink()
        result = self.run_health("--codex")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("codex", result.stderr)

    def test_default_and_before_restore_checks_keep_the_proxy_readiness(self):
        for arguments in ((), ("--before-restore",)):
            with self.subTest(arguments=arguments):
                result = self.run_health(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("mihomo", result.stderr)

    def test_before_restore_keeps_the_readiness_next_to_the_codex_set(self):
        # Both flags were supported together before the narrow set existed, so
        # the combined check stays the strict host bring-up check.
        result = self.run_health("--codex", "--before-restore")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mihomo", result.stderr)

    def test_launcher_only_check_requires_the_with_proxy_executable(self):
        # codex-herdr refuses to launch without the executable, so the health
        # check answers the same question; the endpoint stays optional.
        (self.bin / "with-proxy").unlink()
        result = self.run_health("--codex")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("with-proxy", result.stderr)

    def test_wrapper_launches_directly_without_a_proxy_endpoint(self):
        self.env["HTTP_PROXY"] = "http://127.0.0.1:1"
        result = subprocess.run(
            ["/bin/bash", str(LAUNCHER), "--version"],
            env=self.env, cwd=self.home, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("codex --no-daemon --version", result.stdout)
        # The fallback drops the inherited proxy instead of pointing Codex at a
        # port nothing serves.
        self.assertIn("proxy none", result.stdout)


if __name__ == "__main__":
    unittest.main()
