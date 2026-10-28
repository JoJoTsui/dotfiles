"""Fetched-skill library fixtures for bootstrap tests."""
import shutil
from pathlib import Path

STATIC_LIBRARY = Path(__file__).resolve().parent / "skill-library"


def write_skill_library(root):
    """Copy the static fixture library to a disposable root."""
    root = Path(root)
    shutil.copytree(STATIC_LIBRARY, root)
    return root
