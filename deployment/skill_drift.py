"""Report the drift between the bunx skills CLI lockfile and the skill catalog.

The ``bunx skills`` CLI keeps its own lockfile beside the shared skill tree.
The repository catalog owns that tree, so the CLI lockfile is device state:
this module reads it, names every entry the catalog does not own, and prints
the ``bunx skills remove`` command that tidies the device. It never writes the
lockfile or the directory that holds it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "deployment/skills.tsv"
DISABLED = ROOT / "deployment/disabled-skills.tsv"
CLI_LOCK_RELATIVE = ".agents/.skill-lock.json"
REMOVE_COMMAND = "bunx skills remove"
UNCATALOGUED = "uncatalogued"
DISABLED_ENTRY = "disabled"


class LockError(Exception):
    """The CLI lockfile cannot be read, so its drift cannot be assessed."""


def cli_lock_path(home: Path) -> Path:
    """The lockfile the CLI keeps beside the shared skill tree."""
    return home / CLI_LOCK_RELATIVE


def _names(path: Path) -> set[str]:
    """The first column of a two-column catalog file."""
    names: set[str] = set()
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) < 2 or not fields[0]:
            continue
        names.add(fields[0])
    return names


def catalog_names(path: Path = CATALOG) -> set[str]:
    """The skills the repository catalog owns."""
    return _names(path)


def disabled_names(path: Path = DISABLED) -> set[str]:
    """The skills the deployment keeps outside discovery."""
    return _names(path)


def lock_entries(path: Path) -> dict:
    """The skills the CLI recorded. The file is read, never written."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise LockError(f"cannot read the skills CLI lockfile {path}: {error}") from error
    if not isinstance(payload, dict):
        raise LockError(f"the skills CLI lockfile {path} is not an object")
    skills = payload.get("skills", {})
    if not isinstance(skills, dict):
        raise LockError(f"the skills CLI lockfile {path} has no skills object")
    return skills


def drift_entries(lock_path: Path, catalog: Path = CATALOG, disabled: Path = DISABLED) -> list[tuple[str, str]]:
    """The lockfile entries the catalog does not own, with the reason for each."""
    entries = lock_entries(lock_path)
    known = catalog_names(catalog)
    retired = disabled_names(disabled)
    return [
        (name, DISABLED_ENTRY if name in retired else UNCATALOGUED)
        for name in sorted(entries)
        if name not in known
    ]


def report_text(lock_path: Path, entries: list[tuple[str, str]]) -> str:
    """The drift report, one exact removal command per entry."""
    if not entries:
        return f"skill drift: none; {lock_path} matches the repository catalog"
    lines = [
        f"skill drift: {len(entries)} entries in {lock_path} are not owned by the repository catalog"
    ]
    for name, reason in entries:
        lines.append(f"skill drift: {reason} {name}")
        lines.append(f"{REMOVE_COMMAND} {name}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG,
                        help="the repository skill catalog")
    parser.add_argument("--disabled", type=Path, default=DISABLED,
                        help="the catalog of skills kept outside discovery")
    parser.add_argument("--lock", type=Path, default=None,
                        help="the CLI lockfile to read")
    parser.add_argument("--home", type=Path, default=None,
                        help="the device home whose .agents/.skill-lock.json is read")
    parser.add_argument("--report", action="store_true",
                        help="print the drift without failing, for an apply or a check")
    arguments = parser.parse_args(argv)
    lock_path = arguments.lock or cli_lock_path(arguments.home or Path.home())
    try:
        entries = drift_entries(lock_path, arguments.catalog, arguments.disabled)
    except LockError as error:
        print(f"dotfiles: {error}", file=sys.stderr)
        return 0 if arguments.report else 2
    print(report_text(lock_path, entries))
    return 0 if arguments.report or not entries else 1


if __name__ == "__main__":
    raise SystemExit(main())
