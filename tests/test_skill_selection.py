"""Skill selection, the managed-skill inventory, and the prune step."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
STATIC_LIBRARY = SOURCE / "tests/fixtures/skill-library"

CAVEMAN_GROUP = (
    "cavecrew", "caveman-commit", "caveman-discover", "caveman-evidence-review",
    "caveman-explore", "caveman-help", "caveman-learn", "caveman-manage",
    "caveman-optimize", "caveman-review", "caveman-setup", "caveman-stats",
    "megacave", "ultracave",
)
# The generic engineering skills of the same upstream are general workflows,
# not caveman voice, so they stay in the reviewed default set.
GENERIC_ENGINEERING = (
    "investigate-first", "lean-build", "migration", "safe-refactor",
    "surgical-patch", "verify-and-stop",
)
DESIGN_GROUP = ("baoyu-diagram", "baoyu-slide-deck", "guizang-ppt-skill", "impeccable")
LARK_DOCS = ("lark-base", "lark-doc", "lark-drive", "lark-markdown", "lark-openapi-explorer",
             "lark-shared", "lark-sheets", "lark-whiteboard", "lark-wiki")
MANAGED_ROOTS = (".agents/skills", ".claude/skills", ".minimax/skills")


def catalog_selections():
    """The selection every catalog row declares."""
    rows = {}
    for line in (SOURCE / "deployment/skills.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        rows[fields[0]] = fields[5]
    return rows


def lock_selections():
    """The selection every reviewed lock row records."""
    rows = {}
    for line in (SOURCE / "deployment/skills.lock.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        rows[fields[0]] = fields[4]
    return rows


class CatalogTaggingTests(unittest.TestCase):
    """The catalog's selection column is the reviewed core and its tags."""

    def test_the_caveman_group_is_tagged_and_the_mode_stays_automatic(self):
        selections = catalog_selections()
        for name in CAVEMAN_GROUP:
            with self.subTest(name=name):
                self.assertEqual(selections[name], "caveman")
        self.assertEqual(selections["caveman"], "auto")
        self.assertEqual(selections["caveman-compress"], "auto")

    def test_the_generic_engineering_skills_stay_automatic(self):
        selections = catalog_selections()
        for name in GENERIC_ENGINEERING:
            with self.subTest(name=name):
                self.assertEqual(selections[name], "auto")

    def test_the_design_skills_and_lark_doc_cluster_are_automatic(self):
        selections = catalog_selections()
        for name in DESIGN_GROUP:
            with self.subTest(name=name):
                self.assertEqual(selections[name], "auto")
        for name in LARK_DOCS:
            with self.subTest(name=name):
                self.assertEqual(selections[name], "auto")
        lark = [name for name, selection in selections.items() if selection == "lark"]
        self.assertTrue(lark)
        for name in lark:
            self.assertTrue(name.startswith("lark-"), name)
            self.assertNotIn(name, LARK_DOCS)

    def test_find_skills_is_disabled_and_not_in_the_catalog(self):
        self.assertNotIn("find-skills", catalog_selections())
        disabled = {
            line.split("|")[0]
            for line in (SOURCE / "deployment/disabled-skills.tsv").read_text().splitlines()
            if line and not line.startswith("#")
        }
        self.assertIn("find-skills", disabled)

    def test_the_lock_records_the_same_selection_as_the_catalog(self):
        self.assertEqual(lock_selections(), catalog_selections())
        result = subprocess.run(
            [sys.executable, str(SOURCE / "deployment/update_skills.py"), "check", "--no-drift"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)


class SkillSelectionTests(unittest.TestCase):
    """The deployment applies the selection, records the inventory, and prunes."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skill-selection-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual payload apply requires chezmoi")
        self.library = self.root / "skill-library"
        shutil.copytree(STATIC_LIBRARY, self.library)
        # A tagged skill of each group, so the selection is observable without
        # fetching anything.
        for name in ("caveman-review", "impeccable"):
            skill = self.library / name
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: fixture skill\n---\nbody\n")
        # A skill the catalog does not own is device content, not a profile
        # member.
        unknown = self.library / "uncatalogued-skill"
        unknown.mkdir()
        (unknown / "SKILL.md").write_text(
            "---\nname: uncatalogued-skill\ndescription: fixture skill\n---\nbody\n")

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
            return None
        rows = set()
        for line in state.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            rows.add(tuple(line.split("|")))
        return rows

    def managed_names(self, root=".agents/skills"):
        directory = self.home / root
        if not directory.is_dir():
            return set()
        return {path.name for path in directory.iterdir()}

    def test_the_default_set_excludes_every_tagged_group(self):
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("caveman-review", self.managed_names())
        for name in ("tdd", "show-me", "humanizer", "humanizer-zh", "implement-spec",
                     "impeccable"):
            self.assertIn(name, self.managed_names())

    def test_a_tag_deploys_only_its_own_group(self):
        result = self.deploy(skills="caveman")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("caveman-review", self.managed_names())
        # The design skills are automatic, so the tag does not gate them.
        self.assertIn("impeccable", self.managed_names())

    def test_a_skill_name_deploys_a_tagged_skill(self):
        result = self.deploy(skills="caveman-review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("caveman-review", self.managed_names())
        self.assertIn("impeccable", self.managed_names())

    def test_a_skill_the_catalog_does_not_own_never_enters_a_managed_root(self):
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        for root in MANAGED_ROOTS:
            self.assertNotIn("uncatalogued-skill", self.managed_names(root))

    def test_the_inventory_records_the_managed_roots_the_deployment_wrote(self):
        result = self.deploy(skills="caveman")
        self.assertEqual(result.returncode, 0, result.stderr)
        inventory = self.inventory()
        self.assertIsNotNone(inventory)
        self.assertIn(("caveman-review", ".agents/skills"), inventory)
        self.assertIn(("caveman-review", ".claude/skills"), inventory)
        self.assertIn(("caveman-review", ".minimax/skills"), inventory)
        self.assertIn(("tdd", ".agents/skills"), inventory)
        # A root the deployment does not own is never recorded.
        for _, root in inventory:
            self.assertIn(root, MANAGED_ROOTS)

    def test_a_deselected_managed_skill_is_pruned_from_every_root(self):
        first = self.deploy(skills="caveman")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("caveman-review", self.managed_names())
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        for root in MANAGED_ROOTS:
            self.assertNotIn("caveman-review", self.managed_names(root))
        self.assertNotIn(("caveman-review", ".agents/skills"), self.inventory())
        self.assertIn("pruned managed skill caveman-review", second.stderr)

    def test_a_device_skill_is_preserved_and_reported(self):
        skill = self.home / ".agents/skills/device-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: device-skill\ndescription: d\n---\nbody\n")
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertIn("device-skill", result.stderr)
        self.assertNotIn(("device-skill", ".agents/skills"), self.inventory())

    def test_a_generated_skill_is_preserved(self):
        first = self.deploy(skills="caveman")
        self.assertEqual(first.returncode, 0, first.stderr)
        state = self.home / ".local/state/dotfiles/generated-skills.tsv"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text("# name|root|generator\ncaveman-review|.agents/skills|herdr --skill\n")
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("caveman-review", self.managed_names())
        self.assertIn("preserved generated skill caveman-review", second.stderr)

    def test_a_symlinked_managed_skill_is_preserved_and_not_followed(self):
        first = self.deploy(skills="caveman")
        self.assertEqual(first.returncode, 0, first.stderr)
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "untouched"
        sentinel.write_text("device bytes\n")
        managed = self.home / ".agents/skills/caveman-review"
        shutil.rmtree(managed)
        managed.symlink_to(outside, target_is_directory=True)
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(managed.is_symlink())
        self.assertEqual(sentinel.read_text(), "device bytes\n")
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ["untouched"])
        self.assertIn("refused to follow a symlink", second.stderr)

    def test_reapplying_with_an_unchanged_selection_changes_nothing(self):
        first = self.deploy(skills="caveman")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {path.relative_to(self.home): path.read_bytes()
                  for path in self.home.rglob("*") if path.is_file() and not path.is_symlink()}
        second = self.deploy(skills="caveman")
        self.assertEqual(second.returncode, 0, second.stderr)
        after = {path.relative_to(self.home): path.read_bytes()
                 for path in self.home.rglob("*") if path.is_file() and not path.is_symlink()}
        # The chezmoi state database records the apply itself.
        before.pop(Path(".config/chezmoi/chezmoistate.boltdb"), None)
        after.pop(Path(".config/chezmoi/chezmoistate.boltdb"), None)
        self.assertEqual(before, after)
        self.assertNotIn("pruned managed skill", second.stderr)


if __name__ == "__main__":
    unittest.main()
