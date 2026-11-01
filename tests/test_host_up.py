"""Checks for the host bring-up command with stub daemons; no host changes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "dot_local/bin/executable_dotfiles-host-up"


class HostUpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-host-up-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.home = self.root / "home"
        self.live = self.root / "live"
        self.repo = self.root / "repo"
        for directory in (self.bin, self.home, self.live, self.repo):
            directory.mkdir()
        self.write_stub("curl", """#!/bin/sh
for argument in "$@"; do
    case "$argument" in
        *9090*) echo 200; exit 0 ;;
        *8787*) echo 404; exit 0 ;;
    esac
done
echo 000
""")
        self.write_stub("with-proxy", "#!/bin/sh\nexec \"$@\"\n")
        for name in ("caveman", "codex", "herdr", "health", "link-home", "mihomo"):
            self.write_stub(name, "#!/bin/sh\nexit 0\n")

    def write_stub(self, name, text):
        path = self.bin / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)

    def run_host_up(self, *arguments):
        environment = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "DOTFILES_SOURCE": str(self.repo),
            "DOTFILES_LIVE_ROOT": str(self.live),
            "DOTFILES_WITH_PROXY": str(self.bin / "with-proxy"),
            "DOTFILES_CAVEMAN_BIN": str(self.bin / "caveman"),
            "DOTFILES_CODEX_BIN": str(self.bin / "codex"),
            "DOTFILES_HERDR_BIN": str(self.bin / "herdr"),
            "DOTFILES_CURL": str(self.bin / "curl"),
            "DOTFILES_AGENT_HEALTH": str(self.bin / "health"),
            "DOTFILES_LINK_HOME": str(self.bin / "link-home"),
            "DOTFILES_MIHOMO_SUPERVISOR": str(self.bin / "mihomo"),
        }
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), *arguments],
            env=environment,
            cwd=SOURCE,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_status_is_read_only_and_healthy_with_stubs(self):
        result = self.run_host_up("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok   links", result.stdout)
        self.assertIn("ok   mihomo", result.stdout)
        self.assertIn("host stack ready", result.stdout)

    def test_up_with_already_running_daemons_is_idempotent(self):
        result = self.run_host_up("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("host stack ready", result.stdout)
        self.assertFalse((self.home / ".caveman/run").exists())

    def test_restore_does_not_restart_a_running_herdr(self):
        result = self.run_host_up("up", "--restore")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("restore happens on the next server start", result.stderr)

    def test_help_and_syntax(self):
        result = self.run_host_up("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: dotfiles-host-up", result.stdout)
        syntax = subprocess.run(["/bin/bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
