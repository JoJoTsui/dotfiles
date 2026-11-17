"""The skill review gate: the budget, the ratchet, and the per-client inventory.

The gate reads a library, measures every skill in it, and reports the
per-client inventory, the budget findings, and the ratchet result. A new row
above the budget fails by name; a row whose measurements no longer match its
reviewed exception fails as well.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from deployment import skill_review  # noqa: E402  The reviewer lives beside the check.

UPDATE = SOURCE / "deployment/update_skills.py"
CATALOG = SOURCE / "deployment/skills.tsv"
EXCEPTIONS = SOURCE / "deployment/skill-budget-exceptions.tsv"
CLIENTS = SOURCE / "deployment/agent-payload/skill-clients.tsv"
SKILL_ROOTS = SOURCE / "deployment/agent-payload/skill-roots.tsv"

LONG_DESCRIPTION = "x" * 300


class ReviewFixture(unittest.TestCase):
    """A disposable catalog, lock, library, and exception list."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skill-review-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.catalog = self.root / "skills.tsv"
        self.lock = self.root / "skills.lock.tsv"
        self.exceptions = self.root / "exceptions.tsv"

    def write_skill(self, name, description="A short description.", body="Body\n",
                    root_lines=None, reference=False):
        """A skill directory in the fixture library."""
        directory = self.library / name
        directory.mkdir(parents=True, exist_ok=True)
        text = f"---\nname: {name}\ndescription: {description}\n---\n"
        if root_lines is not None:
            text += "\n".join(f"line {index}" for index in range(root_lines)) + "\n"
        else:
            text += body
        (directory / "SKILL.md").write_text(text, encoding="utf-8")
        if reference:
            references = directory / "references"
            references.mkdir(exist_ok=True)
            (references / "detail.md").write_text("reference bytes\n", encoding="utf-8")
        return directory

    def write_catalog(self, *names, selection="auto"):
        """A catalog and a lock that declare the same names.

        A name is a plain string with the default selection, or a
        ``(name, selection)`` pair.
        """
        rows = []
        for name in names:
            row_name, row_selection = name if isinstance(name, tuple) else (name, selection)
            rows.append(f"{row_name}|git|https://example.invalid/skills|main|"
                        f"skills/{row_name}|{row_selection}")
        self.catalog.write_text("# name|kind|source|ref|path|selection\n"
                                + "\n".join(rows) + "\n", encoding="utf-8")
        pins = []
        for row in rows:
            fields = row.split("|")
            pins.append(f"{fields[0]}|git|https://example.invalid/skills|{'a' * 40}|{fields[5]}")
        self.lock.write_text("# name|kind|source|resolved|selection\n"
                             + "\n".join(pins) + "\n", encoding="utf-8")

    def write_exceptions(self, *rows):
        """The reviewed exception list."""
        self.exceptions.write_text("# name|description|root|reference|reason\n"
                                   + "".join(f"{row}\n" for row in rows), encoding="utf-8")

    def check(self, *arguments):
        """The check command against the fixture."""
        return subprocess.run(
            [sys.executable, str(UPDATE), "check",
             "--catalog", str(self.catalog), "--lock", str(self.lock),
             "--exceptions", str(self.exceptions), "--no-drift", *arguments],
            capture_output=True, text=True, timeout=120)


class BudgetTests(ReviewFixture):
    """A description and a root document have a budget."""

    def test_a_library_within_the_budget_passes(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skill pins: checked 1 entries", result.stdout)
        self.assertIn("skill ratchet: no failures", result.stdout)

    def test_a_new_row_over_the_description_budget_fails_by_name(self):
        self.write_skill("demo", description=LONG_DESCRIPTION)
        self.write_catalog("demo")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("skill ratchet: demo:", result.stdout)
        self.assertIn("description 300 characters", result.stdout)
        self.assertIn("no reviewed exception", result.stdout)

    def test_a_new_row_over_the_root_budget_fails_by_name(self):
        self.write_skill("demo", root_lines=250)
        self.write_catalog("demo")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("skill ratchet: demo:", result.stdout)
        self.assertIn("root 254 lines", result.stdout)

    def test_a_root_over_the_limit_passes_when_the_skill_ships_a_reference(self):
        self.write_skill("demo", root_lines=250, reference=True)
        self.write_catalog("demo")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skill ratchet: no failures", result.stdout)

    def test_a_grandfathered_row_passes(self):
        self.write_skill("demo", description=LONG_DESCRIPTION)
        self.write_catalog("demo")
        self.write_exceptions(f"demo|300|5|no|the upstream description is longer than the budget")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skill ratchet: no failures", result.stdout)
        self.assertIn("demo: description 300 characters", result.stdout)

    def test_a_changed_grandfathered_row_fails(self):
        self.write_skill("demo", description=LONG_DESCRIPTION)
        self.write_catalog("demo")
        # The exception records the measurements of an earlier revision.
        self.write_exceptions(f"demo|280|5|no|the upstream description is longer than the budget")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("skill ratchet: demo:", result.stdout)
        self.assertIn("the reviewed exception records description 280 characters", result.stdout)

    def test_an_exception_for_a_row_within_the_budget_fails(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        self.write_exceptions(f"demo|300|5|no|the upstream description used to be longer")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("the reviewed exception records description 300 characters", result.stdout)

    def test_an_exception_without_a_reason_is_rejected(self):
        self.write_skill("demo", description=LONG_DESCRIPTION)
        self.write_catalog("demo")
        self.write_exceptions("demo|300|1|no|")
        result = self.check("--library", str(self.library))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs a name and a reason", result.stderr)

    def test_an_exception_for_a_row_the_catalog_does_not_own_fails(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        self.write_exceptions("gone|300|5|no|the row left the catalog")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("the reviewed exception names a row the catalog does not own", result.stdout)


    def test_a_generated_skill_is_outside_the_catalog_budget(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        self.write_skill("herdr", description=LONG_DESCRIPTION, root_lines=220)
        generated = self.root / "generated-skills.tsv"
        generated.write_text("# name|root|generator\nherdr|.agents/skills|herdr --skill\n",
                             encoding="utf-8")
        result = self.check("--library", str(self.library), "--generated-skills", str(generated))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("generated skill, outside the catalog budget", result.stdout)


class DescriptionParsingTests(ReviewFixture):
    """A block description is read as its joined prose."""

    def folded(self):
        directory = self.library / "folded"
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            "---\nname: folded\ndescription: >\n"
            f"  {'a' * 100}\n"
            f"  {'b' * 100}\n"
            f"  {'c' * 100}\n"
            "---\nbody\n", encoding="utf-8")
        return directory

    def literal(self):
        directory = self.library / "literal"
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            "---\nname: literal\ndescription: |\n"
            f"  {'a' * 100}\n"
            f"  {'b' * 100}\n"
            f"  {'c' * 100}\n"
            "---\nbody\n", encoding="utf-8")
        return directory

    def test_a_folded_description_counts_as_its_joined_prose(self):
        description = skill_review.read_description(self.folded() / "SKILL.md")
        self.assertEqual(len(description), 302)
        self.assertNotIn("\n", description)

    def test_a_literal_description_counts_as_its_joined_prose(self):
        description = skill_review.read_description(self.literal() / "SKILL.md")
        self.assertEqual(len(description), 302)
        self.assertIn("\n", description)

    def test_a_block_description_above_the_budget_fails(self):
        self.folded()
        self.write_catalog("folded")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("description 302 characters", result.stdout)


class InventoryTests(ReviewFixture):
    """The check reports what each client loads."""

    def test_the_inventory_names_every_client_and_its_shape(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skill inventory: 1 profile skills (1 automatic)", result.stdout)
        self.assertIn("claude: a filtered copy in .claude/skills (profile, 1 skills)", result.stdout)
        self.assertIn("minimax: a filtered copy in .minimax/skills (profile, 1 skills)", result.stdout)
        self.assertIn("codex: the shared tree .agents/skills, no managed root of its own (global, 1 skills)", result.stdout)
        self.assertIn("kimi: the shared tree .agents/skills, no managed root of its own (global, 1 skills)", result.stdout)
        self.assertIn("qoder: the shared tree .agents/skills, no managed root of its own (global, 1 skills)", result.stdout)
        self.assertIn("opencode: the shared tree .agents/skills, no managed root of its own (profile, 1 skills)", result.stdout)
        self.assertIn("pi: the shared tree .agents/skills, no managed root of its own (profile, 1 skills)", result.stdout)

    def test_the_inventory_separates_the_automatic_skills_from_the_tagged_ones(self):
        self.write_skill("demo")
        self.write_skill("extra")
        self.write_catalog("demo", ("extra", "design"))
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("2 profile skills (1 automatic, 1 tagged)", result.stdout)

    def test_the_inventory_names_the_device_roots_the_deployment_never_writes(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        result = self.check("--library", str(self.library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("device roots the deployment never writes:", result.stdout)
        self.assertIn(".pi/agent/skills (pi)", result.stdout)
        self.assertIn(".config/opencode/skills (opencode)", result.stdout)

    def test_a_generated_skill_is_named_and_is_not_part_of_the_profile(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        state = self.root / "generated-skills.tsv"
        state.write_text("# name|root|generator\nherdr|.agents/skills|herdr --skill\n",
                         encoding="utf-8")
        self.write_skill("herdr")
        result = self.check("--library", str(self.library), "--generated-skills", str(state))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 profile skills (1 automatic), 1 generated skill", result.stdout)
        self.assertIn("generated skill: herdr", result.stdout)


class MissingLibraryTests(ReviewFixture):
    """A library that cannot be read is reported, not assumed."""

    def test_a_missing_library_reports_that_the_budget_was_not_measured(self):
        self.write_skill("demo")
        self.write_catalog("demo")
        result = self.check("--library", str(self.root / "absent"))
        self.assertIn("NOT MEASURED", result.stdout)
        self.assertIn("skill ratchet: NOT MEASURED", result.stdout)
        self.assertNotIn("no failures", result.stdout)


class RepositoryExceptionTests(unittest.TestCase):
    """The repository's reviewed exceptions are complete."""

    def test_every_exception_records_a_reason_and_measured_numbers(self):
        exceptions = skill_review.read_exceptions(EXCEPTIONS)
        self.assertTrue(exceptions)
        for name, exception in exceptions.items():
            with self.subTest(skill=name):
                self.assertTrue(exception.reason.strip())
                self.assertGreaterEqual(exception.description_length, 0)
                self.assertGreaterEqual(exception.root_lines, 0)

    def test_every_exception_names_a_row_the_catalog_owns(self):
        catalog = {line.split("|")[0]
                   for line in CATALOG.read_text(encoding="utf-8").splitlines()
                   if line and not line.startswith("#")}
        for name in skill_review.read_exceptions(EXCEPTIONS):
            with self.subTest(skill=name):
                self.assertIn(name, catalog)

    def test_every_exception_is_over_the_budget(self):
        for name, exception in skill_review.read_exceptions(EXCEPTIONS).items():
            with self.subTest(skill=name):
                measurement = skill_review.Measurement(
                    name, exception.description_length, exception.root_lines,
                    exception.has_reference)
                self.assertTrue(measurement.over_budget)


if __name__ == "__main__":
    unittest.main()
