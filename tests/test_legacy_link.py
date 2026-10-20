"""Checks for the opt-in legacy home relinker; all writes stay in temp homes."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "deployment" / "legacy" / "link-home.sh"
MANIFEST = SOURCE / "deployment" / "legacy" / "home-links.tsv"


def manifest_rows():
    rows = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        group, path = line.split("|")
        rows.append((group, path))
    return rows


class LegacyLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-legacy-link-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "legacy"
        self.home = self.root / "home"
        self.source.mkdir()
        self.home.mkdir()
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.root / "unrelated-home")
        self.env["NO_COLOR"] = "1"

    def run_link(self, *arguments, groups=None):
        command = ["bash", str(SCRIPT), "--source", str(self.source), "--home", str(self.home)]
        if groups is not None:
            command += ["--groups", groups]
        command += list(arguments)
        return subprocess.run(
            command,
            cwd=SOURCE,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def make_sources(self, rows=None):
        for _group, path in rows or manifest_rows():
            (self.source / path).mkdir(parents=True)

    def make_source_file(self, path, content):
        target = self.source / path
        if target.is_dir():
            target.rmdir()
        target.write_text(content, encoding="utf-8")

    def backups(self):
        return sorted(set(self.home.glob("*.bak.*")) | set(self.home.glob(".*.bak.*")))

    def test_manifest_is_well_formed_and_covers_agent_roots(self):
        rows = manifest_rows()
        groups = {group for group, _path in rows}
        paths = [path for _group, path in rows]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(groups)
        for group in groups:
            self.assertRegex(group, r"^[a-z0-9-]+$")
        for path in paths:
            self.assertNotIn("/", path)
            self.assertNotIn(path, (".", ".."))
        for required in (
            ".qoder", ".minimax", ".minimax-code", ".minimax-code-install-logs",
            ".codex", ".opencode", ".kimi-code", ".pi", ".codegraph",
        ):
            self.assertIn(required, paths)

    def test_full_link_is_idempotent_and_creates_no_backups(self):
        self.make_sources()
        first = self.run_link()
        self.assertEqual(first.returncode, 0, first.stderr)
        for _group, path in manifest_rows():
            target = self.home / path
            self.assertTrue(target.is_symlink(), target)
            self.assertEqual(os.readlink(target), str(self.source / path))
        self.assertEqual(self.backups(), [])

        second = self.run_link()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("already correct", second.stdout)
        self.assertEqual(self.backups(), [])

    def test_existing_file_and_directory_are_backed_up(self):
        self.make_sources([("config", ".bashrc"), ("runtime", ".config")])
        self.make_source_file(".bashrc", "new shell\n")
        (self.home / ".bashrc").write_text("old shell\n", encoding="utf-8")
        (self.home / ".config").mkdir()
        (self.home / ".config" / "marker").write_text("keep\n", encoding="utf-8")

        result = self.run_link(groups="config,runtime")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / ".bashrc").is_symlink())
        self.assertTrue((self.home / ".config").is_symlink())

        bash_backups = sorted(self.home.glob(".bashrc.bak.*"))
        config_backups = sorted(self.home.glob(".config.bak.*"))
        self.assertEqual(len(bash_backups), 1)
        self.assertEqual(len(config_backups), 1)
        self.assertRegex(bash_backups[0].name, r"^\.bashrc\.bak\.\d{8}-\d{6}(-\d+)?$")
        self.assertEqual(bash_backups[0].read_text(encoding="utf-8"), "old shell\n")
        self.assertEqual((config_backups[0] / "marker").read_text(encoding="utf-8"), "keep\n")

    def test_wrong_symlink_is_moved_to_backup_before_relinking(self):
        self.make_sources([("config", ".bashrc")])
        self.make_source_file(".bashrc", "new\n")
        other = self.root / "other-bashrc"
        other.write_text("other\n", encoding="utf-8")
        (self.home / ".bashrc").symlink_to(other)

        result = self.run_link(groups="config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.home / ".bashrc"), str(self.source / ".bashrc"))
        backups = sorted(self.home.glob(".bashrc.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].is_symlink())
        self.assertEqual(os.readlink(backups[0]), str(other))

    def test_dry_run_reports_changes_without_writing(self):
        self.make_sources([("config", ".bashrc")])
        self.make_source_file(".bashrc", "new\n")
        (self.home / ".bashrc").write_text("old\n", encoding="utf-8")

        result = self.run_link("--dry-run", groups="config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would back up .bashrc", result.stdout)
        self.assertIn("dry run complete", result.stdout)
        self.assertFalse((self.home / ".bashrc").is_symlink())
        self.assertEqual((self.home / ".bashrc").read_text(encoding="utf-8"), "old\n")
        self.assertEqual(self.backups(), [])

    def test_check_returns_drift_until_links_are_correct(self):
        self.make_sources([("config", ".bashrc")])
        self.make_source_file(".bashrc", "new\n")

        missing = self.run_link("--check", groups="config")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("MISSING  .bashrc", missing.stdout)

        linked = self.run_link(groups="config")
        self.assertEqual(linked.returncode, 0, linked.stderr)
        correct = self.run_link("--check", groups="config")
        self.assertEqual(correct.returncode, 0, correct.stderr)
        self.assertIn("OK       .bashrc", correct.stdout)

        other = self.root / "elsewhere"
        other.mkdir()
        (self.home / ".bashrc").unlink()
        (self.home / ".bashrc").symlink_to(other)
        drift = self.run_link("--check", groups="config")
        self.assertEqual(drift.returncode, 1)
        self.assertIn("DRIFT    .bashrc", drift.stdout)

    def test_group_selection_limits_the_link_set(self):
        rows = manifest_rows()
        self.make_sources(rows)
        result = self.run_link(groups="agents")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / ".qoder").is_symlink())
        self.assertFalse((self.home / ".bashrc").exists())
        self.assertFalse((self.home / ".config").exists())

        unknown = self.run_link(groups="not-a-group")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown group", unknown.stderr)

    def test_source_and_home_must_differ(self):
        self.make_sources([("config", ".bashrc")])
        result = self.run_link("--source", str(self.home))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source and home are the same", result.stderr)
        self.assertFalse((self.home / ".bashrc").exists())

    def test_target_may_not_contain_its_source(self):
        nested = self.home / ".config" / "legacy"
        nested.mkdir(parents=True)
        (nested / ".config").mkdir()
        self.source = nested
        result = self.run_link(groups="runtime")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("would contain source", result.stderr)
        self.assertFalse((self.home / ".config").is_symlink())
        self.assertEqual(self.backups(), [])

    def test_system_request_fails_before_home_changes_when_source_is_missing(self):
        self.make_sources([("config", ".bashrc")])
        result = self.run_link("--system", groups="config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--system requested", result.stderr)
        self.assertFalse((self.home / ".bashrc").exists())
        self.assertEqual(self.backups(), [])

    def test_missing_source_tree_and_strict_mode_fail_before_writing(self):
        empty = self.run_link(groups="config")
        self.assertNotEqual(empty.returncode, 0)
        self.assertIn("none of the selected sources exist", empty.stderr)

        self.make_sources([("config", ".bashrc")])
        strict = self.run_link("--strict", groups="config")
        self.assertNotEqual(strict.returncode, 0)
        self.assertIn("selected source path(s) missing", strict.stderr)
        self.assertFalse((self.home / ".bashrc").exists())

    def test_symlink_invocation_still_finds_the_manifest(self):
        self.make_sources([("config", ".bashrc")])
        alias = self.root / "link-home"
        alias.symlink_to(os.path.relpath(SCRIPT, self.root))
        result = subprocess.run(
            [
                "bash", str(alias),
                "--source", str(self.source),
                "--home", str(self.home),
                "--groups", "config",
            ],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / ".bashrc").is_symlink())
        self.assertEqual(
            os.readlink(self.home / ".bashrc"),
            str(self.source / ".bashrc"),
        )

    def test_help_and_list_do_not_require_a_target_home(self):
        help_result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            cwd=SOURCE,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--source DIR", help_result.stdout)

        listing = self.run_link("--list", groups="agents")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn("agents     .qoder", listing.stdout)
        self.assertNotIn("config     .bashrc", listing.stdout)


if __name__ == "__main__":
    unittest.main()
