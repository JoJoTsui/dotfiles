"""Fetched-skill library fixtures for bootstrap tests."""
import shutil
from pathlib import Path

STATIC_LIBRARY = Path(__file__).resolve().parent / "skill-library"


def skill_fixture_inventory(source, library, selection=""):
    """Expected discoveries from the input fixture and source catalogs."""
    selected = set(selection.split(","))
    disabled = {
        line.split("|", 1)[0]
        for line in (source / "deployment/disabled-skills.tsv").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    allowed = set()
    for line in (source / "deployment/skills.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, *_origin, tag = line.split("|")
            if not tag or tag == "auto" or name in selected or tag in selected:
                allowed.add(name)
    available = {path.parent.name for path in library.glob("*/SKILL.md")}
    return (available & allowed) - disabled, disabled


def assert_skill_copies(case, home, fixture_root, resources):
    """Check regular, byte-identical resources in every managed discovery root."""
    for root in (".agents/skills", ".claude/skills", ".minimax/skills"):
        for resource in resources:
            copied = home / root / resource
            case.assertFalse(copied.is_symlink(), str(copied))
            case.assertEqual(copied.read_bytes(), (fixture_root / resource).read_bytes(), str(copied))


def write_skill_library(root):
    """Copy the static fixture library to a disposable root."""
    root = Path(root)
    shutil.copytree(STATIC_LIBRARY, root)
    graphify = root / "graphify"
    graphify.mkdir(exist_ok=True)
    (graphify / "SKILL.md").write_text("---\nname: graphify\ndescription: mock portable graph skill\n---\nSee references/query.md.\n")
    (graphify / "references").mkdir(exist_ok=True)
    (graphify / "references/query.md").write_text("Mock reference; actual upstream bytes are tested by the fetcher.\n")
    return root
