"""Skill catalog adoption and the CLI lockfile drift report."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
CATALOG = SOURCE / "deployment/skills.tsv"
LOCK = SOURCE / "deployment/skills.lock.tsv"
DISABLED = SOURCE / "deployment/disabled-skills.tsv"
DRIFT = SOURCE / "deployment/skill_drift.py"
UPDATE = SOURCE / "deployment/update_skills.py"

# The six skills the CLI lockfile knew and the catalog did not. Each row is
# the upstream source, the skill path inside it, and the selection.
ADOPTED = {
    "baoyu-diagram": ("https://github.com/jimliu/baoyu-skills", "skills/baoyu-diagram", "design"),
    "baoyu-slide-deck": ("https://github.com/jimliu/baoyu-skills", "skills/baoyu-slide-deck", "design"),
    "guizang-ppt-skill": ("https://github.com/op7418/guizang-ppt-skill", ".", "design"),
    "impeccable": ("https://github.com/pbakaus/impeccable", ".agents/skills/impeccable", "design"),
    "find-skills": ("https://github.com/vercel-labs/skills", "skills/find-skills", "auto"),
    "resolving-merge-conflicts": ("https://github.com/mattpocock/skills",
                                  "skills/engineering/resolving-merge-conflicts", "auto"),
}


def rows(path, width):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != width:
            continue
        result[fields[0]] = fields
    return result


class AdoptedCatalogTests(unittest.TestCase):
    """The six skills the CLI knew are catalogued rows with pinned bytes."""

    def test_each_adopted_skill_is_a_catalogued_row_with_its_selection(self):
        catalog = rows(CATALOG, 6)
        for name, (source, path, selection) in ADOPTED.items():
            with self.subTest(skill=name):
                self.assertIn(name, catalog)
                row = catalog[name]
                self.assertEqual(row[1], "git")
                self.assertEqual(row[2], source)
                self.assertEqual(row[4], path)
                self.assertEqual(row[5], selection)

    def test_each_adopted_skill_is_pinned_to_a_reviewed_commit(self):
        catalog = rows(CATALOG, 6)
        pins = rows(LOCK, 5)
        for name, (source, _, selection) in ADOPTED.items():
            with self.subTest(skill=name):
                self.assertIn(name, pins)
                pin = pins[name]
                self.assertEqual(pin[1], "git")
                self.assertEqual(pin[2], source)
                self.assertEqual(pin[4], selection)
                self.assertRegex(pin[3], r"^[a-f0-9]{40}$")

    def test_the_adoption_does_not_move_an_existing_pin(self):
        pins = rows(LOCK, 5)
        # A row the catalog already owned keeps the commit it had.
        self.assertEqual(pins["tdd"][3], "59db609eb1e18aaf59b63284d0e52255aff0c63c")
        self.assertEqual(pins["worktrunk"][3], pins["wt-switch-create"][3])

    def test_the_adopted_skills_deploy_through_the_catalog_path(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skill-adoption-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        (source / "deployment").mkdir(parents=True)
        shutil.copy(SOURCE / "deployment/skill-layouts.tsv", source / "deployment/skill-layouts.tsv")
        shutil.copy(DISABLED, source / "deployment/disabled-skills.tsv")
        shutil.copy(DRIFT, source / "deployment/skill_drift.py")
        repos = self.make_repos(root)
        catalog_rows = []
        pin_rows = []
        for name, (_, path, selection) in ADOPTED.items():
            repo, commit = repos[name]
            catalog_rows.append(f"{name}|git|{repo}|main|{path}|{selection}")
            pin_rows.append(f"{name}|git|{repo}|{commit}|{selection}")
        (source / "deployment/skills.tsv").write_text(
            "# name|kind|source|ref|path|selection\n" + "\n".join(catalog_rows) + "\n")
        (source / "deployment/skills.lock.tsv").write_text(
            "# name|kind|source|resolved|selection\n" + "\n".join(pin_rows) + "\n")
        home = root / "device"
        home.mkdir()
        # The design group is opt-in, so the host asks for it by tag.
        result = self.run_script(source, home, 'prepare_skill_library\nprintf "%s" "$PAYLOAD_SKILLS_DIR"',
                                 env={"DOTFILES_SKILLS": "design"})
        self.assertEqual(result.returncode, 0, result.stderr)
        library = Path(result.stdout.strip().splitlines()[-1])
        for name in ADOPTED:
            with self.subTest(skill=name):
                self.assertTrue((library / name / "SKILL.md").is_file())
        # A root skill keeps its mapped resources and leaves the repository's
        # own files out of the discovery root.
        guizang = library / "guizang-ppt-skill"
        self.assertTrue((guizang / "references/notes.md").is_file())
        self.assertTrue((guizang / "assets/template.html").is_file())
        self.assertTrue((guizang / "scripts/check.mjs").is_file())
        self.assertFalse((guizang / "README.md").exists())

    def make_repos(self, root):
        """One upstream repository per adopted skill, shaped like the real one."""
        layout = {
            "baoyu-diagram": {"skills/baoyu-diagram": "baoyu-diagram"},
            "baoyu-slide-deck": {"skills/baoyu-slide-deck": "baoyu-slide-deck"},
            "find-skills": {"skills/find-skills": "find-skills"},
            "resolving-merge-conflicts": {"skills/engineering/resolving-merge-conflicts":
                                          "resolving-merge-conflicts"},
            "impeccable": {".agents/skills/impeccable": "impeccable"},
            "guizang-ppt-skill": {".": "guizang-ppt-skill"},
        }
        repos = {}
        for name, skills in layout.items():
            repo = root / f"upstream-{name}"
            for path, skill in skills.items():
                directory = repo / path if path != "." else repo
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "SKILL.md").write_text(
                    f"---\nname: {skill}\ndescription: demo\n---\nbody\n")
            if name == "guizang-ppt-skill":
                # A root skill carries its own resources and the repository's
                # own files beside them.
                (repo / "LICENSE").write_text("upstream license\n")
                (repo / "README.md").write_text("repository readme\n")
                for directory, resource, body in (("references", "notes.md", "notes\n"),
                                                 ("assets", "template.html", "<html></html>\n"),
                                                 ("scripts", "check.mjs", "// helper\n")):
                    (repo / directory).mkdir()
                    (repo / directory / resource).write_text(body)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                            "commit", "-qm", "init"], check=True)
            commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            repos[name] = (repo, commit)
        return repos

    def run_script(self, source, home, body, env=None):
        script = home.parent / "run.sh"
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{source}'\n"
            f"DEPLOY_HOME='{home}'\n"
            f"export HOME='{home}'\n"
            f"export XDG_CACHE_HOME='{home}/xdg-cache' XDG_STATE_HOME='{home}/xdg-state' TMPDIR='{home}/tmp'\n"
            "mkdir -p \"$TMPDIR\"\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            f"source '{SOURCE}/deployment/skills.sh'\n"
            f"source '{SOURCE}/deployment/payload.sh'\n"
            + body,
            encoding="utf-8")
        environment = dict(os.environ, **(env or {}))
        return subprocess.run(["/bin/bash", str(script)], env=environment,
                              capture_output=True, text=True, timeout=180)


class DriftReportTests(unittest.TestCase):
    """The CLI lockfile is device state the deployment reports, never writes."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skill-drift-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        (self.home / ".agents").mkdir(parents=True)

    def write_lock(self, *names):
        payload = {
            "version": 3,
            "skills": {name: {"source": "someone/skills", "skillPath": f"{name}/SKILL.md"}
                       for name in names},
            "dismissed": {},
            "lastSelectedAgents": ["codex"],
        }
        path = self.home / ".agents/.skill-lock.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def report(self, *arguments):
        return subprocess.run([sys.executable, str(DRIFT), "--home", str(self.home), *arguments],
                              capture_output=True, text=True, timeout=60)

    def test_an_uncatalogued_entry_is_named_with_its_removal_command(self):
        self.write_lock("some-device-skill", "tdd")
        result = self.report()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("skill drift: uncatalogued some-device-skill", result.stdout)
        self.assertIn("bunx skills remove some-device-skill", result.stdout.splitlines())
        # A catalogued entry is not drift.
        self.assertNotIn("bunx skills remove tdd", result.stdout)

    def test_a_disabled_entry_is_named_with_its_removal_command(self):
        disabled = rows(DISABLED, 2)
        name = sorted(disabled)[0]
        self.write_lock(name)
        result = self.report()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(f"skill drift: disabled {name}", result.stdout)
        self.assertIn(f"bunx skills remove {name}", result.stdout.splitlines())

    def test_a_lockfile_the_catalog_owns_reports_no_drift(self):
        self.write_lock("tdd", "worktrunk")
        result = self.report()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("skill drift: none", result.stdout)
        self.assertNotIn("bunx skills remove", result.stdout)

    def test_the_report_mode_never_fails_on_drift(self):
        self.write_lock("some-device-skill")
        result = self.report("--report")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("bunx skills remove some-device-skill", result.stdout)

    def test_a_missing_lockfile_reports_no_drift(self):
        result = self.report()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("skill drift: none", result.stdout)

    def test_an_unreadable_lockfile_is_reported_without_a_traceback(self):
        path = self.home / ".agents/.skill-lock.json"
        path.write_text("{not json", encoding="utf-8")
        result = self.report()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("cannot read the skills CLI lockfile", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_the_check_reports_the_drift_without_failing(self):
        self.write_lock("some-device-skill")
        result = subprocess.run(
            [sys.executable, str(UPDATE), "check", "--cli-lock", str(self.home / ".agents/.skill-lock.json")],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill pins: checked", result.stdout)
        self.assertIn("bunx skills remove some-device-skill", result.stdout)

    def test_the_check_does_not_write_the_cli_lockfile(self):
        path = self.write_lock("some-device-skill")
        before = path.read_bytes()
        before_mtime = path.stat().st_mtime_ns
        listing = sorted(p.name for p in path.parent.iterdir())
        subprocess.run(
            [sys.executable, str(UPDATE), "check", "--cli-lock", str(path)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, before_mtime)
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), listing)


class NoWriteGuaranteeTests(unittest.TestCase):
    """An apply reads the CLI lockfile and leaves it exactly as it found it."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skill-nowrite-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        (self.home / ".agents").mkdir(parents=True)
        self.payload = {
            "version": 3,
            "skills": {"some-device-skill": {"source": "someone/skills"}},
            "dismissed": {},
            "lastSelectedAgents": [],
        }
        self.lock = self.home / ".agents/.skill-lock.json"
        self.lock.write_text(json.dumps(self.payload, indent=2) + "\n", encoding="utf-8")

    def deploy(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi; set DOTFILES_TEST_CHEZMOI to an isolated binary")
        environment = dict(os.environ)
        environment.update({
            "HOME": str(self.root / "original"),
            "DOTFILES_CHEZMOI_BIN": chezmoi,
            "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library"),
        })
        for name in tuple(environment):
            if name.startswith(("DOTFILES_SKILLS", "XDG_", "PIXI_", "BUN_")) and name != "DOTFILES_SKILLS_DIR":
                environment.pop(name)
        return subprocess.run(
            ["bash", str(SOURCE / "bootstrap.sh"), "--home", str(self.home), "--apply-only",
             "--platform", "linux", "--role", "workstation"],
            env=environment, cwd=SOURCE, capture_output=True, text=True, timeout=300)

    def test_an_apply_leaves_the_cli_lockfile_unchanged(self):
        before = self.lock.read_bytes()
        before_mtime = self.lock.stat().st_mtime_ns
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lock.read_bytes(), before)
        self.assertEqual(self.lock.stat().st_mtime_ns, before_mtime)
        # The deployment owns the shared skill tree and the shared
        # instructions. The CLI keeps its own hidden state in the same
        # directory, and the deployment writes none of it.
        self.assertEqual(sorted(p.name for p in (self.home / ".agents").iterdir() if p.name.startswith(".")),
                         [".skill-lock.json"])

    def test_an_apply_never_creates_a_cli_lockfile(self):
        self.lock.unlink()
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.lock.exists())
        self.assertEqual(sorted(p.name for p in (self.home / ".agents").iterdir() if p.name.startswith(".")), [])


if __name__ == "__main__":
    unittest.main()
