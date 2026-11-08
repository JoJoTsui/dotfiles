"""Fetched-skill library fixtures for bootstrap tests."""
import shutil
from pathlib import Path

STATIC_LIBRARY = Path(__file__).resolve().parent / "skill-library"


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
