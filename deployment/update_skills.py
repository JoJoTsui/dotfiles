"""Check skill pins, review the skill budget, or refresh a reviewable lock.

Never deploys skills. The review measures a library and reports the
per-client inventory, the budget findings, and the ratchet result.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skill_drift  # noqa: E402  The drift reader lives beside this module.
import skill_review  # noqa: E402  The budget reader lives beside this module.

SOURCE = Path(__file__).resolve().parents[1]
# The shared tree is the portable home of the library and the default library
# the review measures.
DEFAULT_LIBRARY = ".agents/skills"


def rows(path: Path, width: int) -> list[list[str]]:
    result = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != width or fields[0] in seen:
            raise ValueError(f"malformed or duplicate row in {path.name}")
        seen.add(fields[0])
        result.append(fields)
    return result


def check(catalog: Path, lock: Path) -> dict[str, list[str]]:
    """Validate the catalog against the reviewed lock; return the declarations."""
    declarations = {row[0]: row for row in rows(catalog, 6)}
    pins = {row[0]: row for row in rows(lock, 5)}
    disabled = catalog.with_name("disabled-skills.tsv")
    if disabled.is_file() and declarations.keys() & {row[0] for row in rows(disabled, 2)}:
        raise ValueError("disabled skills must not be in the active catalog")
    if declarations.keys() != pins.keys():
        raise ValueError("skill catalog and lock names differ; refresh the lock")
    for name, declaration in declarations.items():
        pin = pins[name]
        if declaration[:3] != pin[:3]:
            raise ValueError(f"skill lock source mismatch: {name}")
        if declaration[5] != pin[4]:
            raise ValueError(f"skill lock selection mismatch: {name}")
        pattern = r"[a-f0-9]{40}" if pin[1] == "git" else r"[a-f0-9]{64}"
        if pin[1] not in ("git", "tarball") or not re.fullmatch(pattern, pin[3]):
            raise ValueError(f"invalid skill pin: {name}")
    return declarations


def report_review(library: Path, catalog: Path, exceptions: Path, clients: Path,
                  skill_roots: Path, generated: Path) -> list[str]:
    """Measure the library and report the inventory, the findings, and the ratchet.

    The review never writes the library, the exception list, or the catalog.
    It reports the rows that fail the budget gate, so a caller decides what
    the result means.
    """
    selections = {row[0]: row[5] for row in rows(catalog, 6)}
    result = skill_review.review(
        library,
        selections,
        skill_review.read_exceptions(exceptions),
        skill_review.read_clients(clients),
        skill_review.read_device_roots(skill_roots),
        skill_review.read_generated_skills(generated),
    )
    for line in result.lines:
        print(line)
    return result.failures


def layout_paths(catalog: Path, name: str, path: str) -> list[str]:
    layout = catalog.with_name("skill-layouts.tsv")
    mapped = []
    if layout.is_file():
        for line in layout.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            skill, source, target = line.split("|")
            if skill != name:
                continue
            for value in (source, target):
                if not value or PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts:
                    raise ValueError(f"unsafe skill layout: {name}")
            mapped.append(f"{path}/{source}")
    return mapped or [f"{path}/SKILL.md"]


def refresh(catalog: Path, lock: Path) -> None:
    lines = ["# Reviewed source snapshot: name|kind|source|git commit or archive SHA-256|selection"]
    with tempfile.TemporaryDirectory(prefix="dotfiles-skills-update-") as temporary:
        root = Path(temporary)
        repositories = {}
        for name, kind, source, ref, path, selection in rows(catalog, 6):
            if kind == "git":
                key = (source, ref)
                if key not in repositories:
                    repo = root / f"repo-{len(repositories)}"
                    subprocess.run(["git", "clone", "--quiet", "--no-checkout", "--depth", "1",
                                    "--branch", ref, source, str(repo)], check=True, timeout=180)
                    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
                    repositories[key] = (repo, revision)
                repo, revision = repositories[key]
                if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
                    raise ValueError(f"unsafe skill path: {name}")
                # A removed upstream skill must fail before replacing the lock.
                for resource in layout_paths(catalog, name, path):
                    subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{revision}:{resource}"],
                                   check=True, timeout=30)
            elif kind == "tarball":
                archive = root / "download.tgz"
                with urllib.request.urlopen(source, timeout=90) as response, archive.open("wb") as output:
                    import shutil
                    shutil.copyfileobj(response, output)
                with tarfile.open(archive) as handle:
                    members = handle.getmembers()
                    for member in members:
                        location = PurePosixPath(member.name)
                        if location.is_absolute() or ".." in location.parts or not (member.isfile() or member.isdir()):
                            raise ValueError(f"unsafe skill archive: {name}")
                    if not any(PurePosixPath(m.name).as_posix() == "SKILL.md" and m.isfile() for m in members):
                        raise ValueError(f"skill archive has no SKILL.md: {name}")
                revision = hashlib.sha256(archive.read_bytes()).hexdigest()
            else:
                raise ValueError(f"unknown skill kind: {kind}")
            lines.append("|".join((name, kind, source, revision, selection)))
        # Complete and validate the candidate before atomically replacing pins.
        candidate = root / "candidate.tsv"
        candidate.write_text("\n".join(lines) + "\n", encoding="utf-8")
        check(catalog, candidate)
        with tempfile.NamedTemporaryFile(dir=lock.parent, prefix=".skills-lock-", delete=False) as output:
            staged = Path(output.name)
            output.write(candidate.read_bytes())
        try:
            staged.replace(lock)
        finally:
            staged.unlink(missing_ok=True)


def report_cli_drift(lock_path: Path, catalog: Path, disabled: Path) -> None:
    """The CLI lockfile is device state: name the entries the catalog does not own.

    A check reports the drift without failing: the lockfile belongs to the
    device, and its contents are the device owner's to review.
    """
    try:
        entries = skill_drift.drift_entries(lock_path, catalog, disabled)
    except skill_drift.LockError as error:
        print(f"dotfiles: {error}", file=sys.stderr)
        return
    print(skill_drift.report_text(lock_path, entries))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "refresh", "review"))
    parser.add_argument("--catalog", type=Path, default=SOURCE / "deployment/skills.tsv")
    parser.add_argument("--lock", type=Path, default=SOURCE / "deployment/skills.lock.tsv")
    parser.add_argument("--disabled", type=Path, default=SOURCE / "deployment/disabled-skills.tsv")
    parser.add_argument("--cli-lock", type=Path, default=None,
                        help="the skills CLI lockfile the drift report reads")
    parser.add_argument("--no-drift", action="store_true",
                        help="skip the skills CLI lockfile drift report")
    parser.add_argument("--library", type=Path, default=None,
                        help="the skill library the budget is measured in; "
                             "the deployed shared tree by default")
    parser.add_argument("--exceptions", type=Path,
                        default=SOURCE / "deployment/skill-budget-exceptions.tsv",
                        help="the reviewed budget exceptions")
    parser.add_argument("--clients", type=Path,
                        default=SOURCE / "deployment/agent-payload/skill-clients.tsv",
                        help="the per-client skill matrix")
    parser.add_argument("--skill-roots", type=Path,
                        default=SOURCE / "deployment/agent-payload/skill-roots.tsv",
                        help="the client roots the deployment never writes")
    parser.add_argument("--generated-skills", type=Path, default=None,
                        help="the device state that names the generated skills")
    parser.add_argument("--report", action="store_true",
                        help="report the budget findings without failing on them")
    args = parser.parse_args()
    if args.command == "refresh":
        refresh(args.catalog, args.lock)
        check(args.catalog, args.lock)
        print(f"skill pins: checked {len(rows(args.lock, 5))} entries")
        if not args.no_drift:
            report_cli_drift(args.cli_lock or skill_drift.cli_lock_path(Path.home()),
                            args.catalog, args.disabled)
        return
    if args.command == "check":
        check(args.catalog, args.lock)
        print(f"skill pins: checked {len(rows(args.lock, 5))} entries")
    library = args.library or (Path.home() / DEFAULT_LIBRARY)
    generated = args.generated_skills or (Path.home() / ".local/state/dotfiles/generated-skills.tsv")
    failures = report_review(library, args.catalog, args.exceptions, args.clients,
                             args.skill_roots, generated)
    if args.command == "check" and not args.no_drift:
        lock_path = args.cli_lock or skill_drift.cli_lock_path(Path.home())
        report_cli_drift(lock_path, args.catalog, args.disabled)
    if failures and not args.report:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
