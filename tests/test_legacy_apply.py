"""Checks for the legacy repo-owned file adapter; all writes stay in temp roots."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "deployment/legacy/apply.sh"


class LegacyApplyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-legacy-apply-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.live = self.root / "live"
        for directory in (self.home, self.live / ".local/bin", self.live / ".config/herdr", self.live / ".codex"):
            directory.mkdir(parents=True)
        (self.home / ".local").symlink_to(self.live / ".local")
        (self.home / ".config").symlink_to(self.live / ".config")
        (self.home / ".codex").symlink_to(self.live / ".codex")

    def run_apply(self, *arguments):
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), "--checkout", str(SOURCE),
             "--home", str(self.home), "--live-root", str(self.live), *arguments],
            cwd=SOURCE,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_check_reports_drift_and_dry_run_writes_nothing(self):
        check = self.run_apply("--check")
        self.assertNotEqual(check.returncode, 0)
        self.assertIn("MISSING .local/bin/dotfiles-host-up", check.stdout)
        dry = self.run_apply("--dry-run", "--groups", "agent")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("would create .local/bin/dotfiles-host-up", dry.stdout)
        self.assertFalse((self.live / ".local/bin/dotfiles-host-up").exists())

    def test_apply_is_idempotent_and_backs_up_an_existing_target(self):
        old = self.live / ".local/bin/nu-login"
        old.write_text("old wrapper\n", encoding="utf-8")
        result = self.run_apply("--apply", "--groups", "agent")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WRITE .local/bin/nu-login", result.stdout)
        backups = sorted((self.live / ".local/bin").glob("nu-login.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "old wrapper\n")
        self.assertIn("exec nu --login", old.read_text(encoding="utf-8"))
        self.assertTrue((self.live / ".local/bin/dotfiles-host-up").is_file())
        second = self.run_apply("--check", "--groups", "agent")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

    def test_mode_drift_is_reported_and_repaired(self):
        result = self.run_apply("--apply", "--groups", "agent")
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.live / ".local/bin/nu-login"
        target.chmod(0o644)
        check = self.run_apply("--check", "--groups", "agent")
        self.assertNotEqual(check.returncode, 0)
        self.assertIn("DRIFT .local/bin/nu-login (mode 644 -> 755)", check.stdout)
        repair = self.run_apply("--apply", "--groups", "agent")
        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)

    def test_config_group_does_not_install_agent_files(self):
        result = self.run_apply("--apply", "--groups", "config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.live / ".config/herdr/config.toml").is_file())
        self.assertFalse((self.live / ".local/bin/nu-login").exists())

    def test_target_selection_preserves_unselected_legacy_shell(self):
        shell = self.live / ".local/bin/nu-login"
        shell.write_text("legacy shell\n")
        selected = ".local/bin/dotfiles-host-up,.local/bin/dotfiles-agent-health,.config/herdr/config.toml"
        applied = self.run_apply("--apply", "--targets", selected)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(shell.read_text(), "legacy shell\n")
        checked = self.run_apply("--check", "--targets", selected)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_unknown_target_fails_before_any_write(self):
        result = self.run_apply("--apply", "--targets", ".local/bin/dotfiles-host-up,typo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown manifest target", result.stderr)
        self.assertFalse((self.live / ".local/bin/dotfiles-host-up").exists())

    def test_symlink_target_is_refused(self):
        target = self.live / ".local/bin/codex-herdr"
        target.symlink_to(self.root / "elsewhere")
        result = self.run_apply("--apply", "--groups", "agent")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FOREIGN .local/bin/codex-herdr", result.stderr)
        self.assertTrue(target.is_symlink())

    def test_help_and_syntax(self):
        result = self.run_apply("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: apply.sh", result.stdout)
        syntax = subprocess.run(["/bin/bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
