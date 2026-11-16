"""The copy roots hold the profile, and a device entry is never overwritten."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
STATIC_LIBRARY = SOURCE / "tests/fixtures/skill-library"

MANAGED_ROOTS = (".agents/skills", ".claude/skills", ".minimax/skills")


class SkillCopyRootTests(unittest.TestCase):
    """A selected skill reaches a copy root without losing a device entry."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skill-copy-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual payload apply requires chezmoi")
        self.library = self.root / "skill-library"
        shutil.copytree(STATIC_LIBRARY, self.library)
        # A tagged skill, so a selection is observable without fetching.
        skill = self.library / "caveman-review"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: caveman-review\ndescription: fixture skill\n---\nbody\n")

    def deploy(self, skills=None):
        environment = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                       "DOTFILES_CHEZMOI_BIN": self.chezmoi,
                       "DOTFILES_SKILLS_DIR": str(self.library)}
        if skills is not None:
            environment["DOTFILES_SKILLS"] = skills
        return subprocess.run(
            ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
             "--home", str(self.home), "--platform", "linux", "--role", "workstation",
             "--apply-only"],
            cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)

    def inventory(self):
        """The managed skill inventory the deployment recorded."""
        state = self.home / ".local/state/dotfiles/managed-skills.tsv"
        if not state.is_file():
            return set()
        rows = set()
        for line in state.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            rows.add(tuple(line.split("|")))
        return rows

    def managed_names(self, root=".claude/skills"):
        directory = self.home / root
        if not directory.is_dir():
            return set()
        return {path.name for path in directory.iterdir()}

    def device_directory(self, root, name):
        """A device directory that holds the name of a selected skill."""
        destination = self.home / root / name
        destination.mkdir(parents=True)
        (destination / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: device skill\n---\ndevice bytes\n")
        return destination

    def test_a_device_symlink_collision_is_preserved_and_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "untouched"
        sentinel.write_text("device bytes\n")
        destination = self.home / ".claude/skills/tdd"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(outside, target_is_directory=True)
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(destination.is_symlink())
        # The copy never crossed the link.
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ["untouched"])
        self.assertEqual(sentinel.read_text(), "device bytes\n")
        self.assertIn("preserved skill tdd in .claude/skills", result.stderr)
        self.assertIn("a device symlink has that name", result.stderr)
        # The deployment does not own the entry, so it never records it.
        self.assertNotIn(("tdd", ".claude/skills"), self.inventory())

    def test_a_device_file_collision_is_preserved(self):
        destination = self.home / ".minimax/skills/tdd"
        destination.parent.mkdir(parents=True)
        destination.write_text("device bytes\n")
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_text(), "device bytes\n")
        self.assertIn("preserved skill tdd in .minimax/skills", result.stderr)
        self.assertIn("a device file has that name", result.stderr)
        self.assertNotIn(("tdd", ".minimax/skills"), self.inventory())

    def test_an_unrecorded_identical_directory_is_adopted_without_a_rewrite(self):
        destination = self.home / ".claude/skills/tdd"
        shutil.copytree(self.library / "tdd", destination)
        stamp = 1000000000
        for path in [destination, *destination.rglob("*")]:
            os.utime(path, (stamp, stamp))
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        # The deployment adopts the directory and never rewrites its bytes.
        self.assertEqual(destination.stat().st_mtime, stamp)
        self.assertEqual((destination / "SKILL.md").stat().st_mtime, stamp)
        self.assertIn(("tdd", ".claude/skills"), self.inventory())
        self.assertNotIn("preserved skill tdd in .claude/skills", result.stderr)

    def test_an_unrecorded_different_directory_is_preserved_and_reported(self):
        destination = self.device_directory(".minimax/skills", "tdd")
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((destination / "SKILL.md").read_text(),
                         "---\nname: tdd\ndescription: device skill\n---\ndevice bytes\n")
        self.assertIn("preserved skill tdd in .minimax/skills", result.stderr)
        self.assertIn("a device directory has that name and its bytes differ", result.stderr)
        self.assertNotIn(("tdd", ".minimax/skills"), self.inventory())

    def test_a_recorded_directory_is_replaced(self):
        first = self.deploy()
        self.assertEqual(first.returncode, 0, first.stderr)
        destination = self.home / ".claude/skills/tdd"
        self.assertEqual((destination / "SKILL.md").read_bytes(),
                         (self.library / "tdd/SKILL.md").read_bytes())
        # The device changes the directory the deployment owns.
        (destination / "SKILL.md").write_text("device bytes\n")
        (destination / "stale.md").write_text("stale bytes\n")
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((destination / "SKILL.md").read_bytes(),
                         (self.library / "tdd/SKILL.md").read_bytes())
        self.assertFalse((destination / "stale.md").exists())

    def test_a_managed_skill_that_leaves_the_profile_is_pruned(self):
        first = self.deploy(skills="caveman")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("caveman-review", self.managed_names())
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        for root in MANAGED_ROOTS:
            self.assertNotIn("caveman-review", self.managed_names(root))
        self.assertIn("pruned managed skill caveman-review", second.stderr)
        self.assertNotIn(("caveman-review", ".claude/skills"), self.inventory())

    def test_the_initial_stale_copy_is_reported_and_not_deleted(self):
        destination = self.device_directory(".minimax/skills", "tdd")
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        # The stale copy predates the inventory, so the deployment reports it
        # and leaves it to the device owner.
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertIn("preserved skill tdd in .minimax/skills", result.stderr)
        self.assertNotIn(("tdd", ".minimax/skills"), self.inventory())

    def test_reapplying_with_an_unchanged_profile_leaves_the_copy_roots_unchanged(self):
        first = self.deploy()
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {path: path.read_bytes() for root in MANAGED_ROOTS
                  for path in (self.home / root).rglob("*") if path.is_file()}
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        after = {path: path.read_bytes() for root in MANAGED_ROOTS
                 for path in (self.home / root).rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertNotIn("pruned managed skill", second.stderr)


if __name__ == "__main__":
    unittest.main()
