"""Check skill pins, review the skill budget, or refresh a reviewable lock.

Never deploys skills. The review measures a library and reports the
per-client inventory, the budget findings, and the ratchet result.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
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
    validate_skill_assets(catalog)
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


def safe_relative(value: str, label: str) -> PurePosixPath:
    location = PurePosixPath(value)
    if not value or location.is_absolute() or ".." in location.parts:
        raise ValueError(f"unsafe {label}: {value}")
    return location


def layout_rows(catalog: Path, name: str) -> list[tuple[str, str, str]]:
    layout = catalog.with_name("skill-layouts.tsv")
    result = []
    if not layout.is_file():
        return result
    for line in layout.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) not in (3, 4):
            raise ValueError(f"malformed skill layout: {line}")
        skill, source, target = fields[:3]
        if skill != name:
            continue
        origin = fields[3] if len(fields) == 4 and fields[3] else "upstream"
        if origin not in ("upstream", "repo"):
            raise ValueError(f"unknown skill layout origin: {name} ({origin})")
        safe_relative(source, "skill layout source")
        safe_relative(target, "skill layout target")
        result.append((source, target, origin))
    return result


def overlay_source(catalog: Path, name: str, source: str) -> Path:
    root = catalog.parent / "skill-overlays" / name
    current = root
    while True:
        if current.is_symlink():
            raise ValueError(f"skill overlay is a symlink: {current}")
        if current == catalog.parent:
            break
        current = current.parent
    resolved_root = root.resolve()
    candidate = root / source
    if not candidate.resolve().is_relative_to(resolved_root):
        raise ValueError(f"unsafe skill overlay: {name}/{source}")
    current = candidate
    while True:
        if current.is_symlink():
            raise ValueError(f"skill overlay is a symlink: {current}")
        if current == root:
            break
        current = current.parent
    if not candidate.exists():
        raise ValueError(f"skill overlay is missing: {name}/{source}")

    def validate_tree(entry: Path) -> None:
        if entry.is_symlink():
            raise ValueError(f"skill overlay is a symlink: {entry}")
        if entry.is_dir():
            for child in entry.iterdir():
                validate_tree(child)
        elif not entry.is_file():
            raise ValueError(f"unsupported skill overlay resource: {entry}")

    validate_tree(candidate)
    return candidate


def smoke_rows(catalog: Path) -> dict[str, tuple[str, str]]:
    smoke = catalog.with_name("skill-smoke.tsv")
    result = {}
    if not smoke.is_file():
        return result
    for line in smoke.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != 3 or fields[0] in result:
            raise ValueError(f"malformed or duplicate skill smoke row: {line}")
        name, script, argument = fields
        safe_relative(script, "skill smoke script")
        if not argument or any(character.isspace() for character in argument):
            raise ValueError(f"unsafe skill smoke argument: {name}")
        result[name] = (script, argument)
    return result


def validate_skill_assets(catalog: Path) -> None:
    declarations = {row[0] for row in rows(catalog, 6)}
    seen = set()
    if catalog.with_name("skill-layouts.tsv").is_file():
        for line in catalog.with_name("skill-layouts.tsv").read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            name = line.split("|", 1)[0]
            if name in seen:
                continue
            seen.add(name)
            if name not in declarations:
                raise ValueError(f"skill layout names a row the catalog does not own: {name}")
            mapped = layout_rows(catalog, name)
            if not any(target == "SKILL.md" for _, target, _ in mapped):
                raise ValueError(f"skill layout has no SKILL.md: {name}")
            for source, _, origin in mapped:
                if origin == "repo":
                    overlay_source(catalog, name, source)
    for name in smoke_rows(catalog):
        if name not in declarations:
            raise ValueError(f"skill smoke names a row the catalog does not own: {name}")


def git_object_path(path: str, source: str) -> str:
    prefix = "" if path in ("", ".") else path.rstrip("/") + "/"
    return prefix + source


def layout_paths(catalog: Path, name: str, path: str) -> list[str]:
    mapped = layout_rows(catalog, name)
    if mapped:
        return [git_object_path(path, source) for source, _, origin in mapped if origin == "upstream"]
    return [git_object_path(path, "SKILL.md")]


def extract_git_tree(archive: bytes, object_path: str, destination: Path) -> None:
    prefix = len(PurePosixPath(object_path).parts)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as handle:
        for member in handle.getmembers():
            location = PurePosixPath(member.name)
            if location.is_absolute() or ".." in location.parts:
                raise ValueError(f"unsafe skill archive member: {member.name}")
            if len(location.parts) <= prefix:
                continue
            relative = PurePosixPath(*location.parts[prefix:])
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = handle.extractfile(member)
                if source is None:
                    raise ValueError(f"cannot read skill archive member: {member.name}")
                target.write_bytes(source.read())
                target.chmod(member.mode & 0o777)
            else:
                raise ValueError(f"unsupported skill archive member: {member.name}")


def stage_git_skill(catalog: Path, name: str, repo: Path, revision: str,
                    path: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    mappings = layout_rows(catalog, name)
    if not mappings:
        archive = subprocess.check_output(
            ["git", "-C", str(repo), "archive", "--format=tar.gz", revision, path],
            timeout=60,
        )
        extract_git_tree(archive, "" if path in ("", ".") else path, destination)
    else:
        for source, target, origin in mappings:
            output = destination / target
            if origin == "repo":
                incoming = overlay_source(catalog, name, source)
                if incoming.is_dir():
                    shutil.copytree(incoming, output, dirs_exist_ok=True)
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(incoming, output)
                continue
            object_path = git_object_path(path, source)
            kind = subprocess.check_output(
                ["git", "-C", str(repo), "cat-file", "-t", f"{revision}:{object_path}"],
                text=True, timeout=30,
            ).strip()
            if kind == "blob":
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(subprocess.check_output(
                    ["git", "-C", str(repo), "show", f"{revision}:{object_path}"],
                    timeout=60,
                ))
            elif kind == "tree":
                archive = subprocess.check_output(
                    ["git", "-C", str(repo), "archive", "--format=tar.gz", revision, object_path],
                    timeout=60,
                )
                output.mkdir(parents=True, exist_ok=True)
                extract_git_tree(archive, object_path, output)
            else:
                raise ValueError(f"unsupported skill object: {name}/{source}")
    if not (destination / "SKILL.md").is_file():
        raise ValueError(f"staged skill has no SKILL.md: {name}")


def run_skill_smoke(catalog: Path, name: str, destination: Path) -> None:
    row = smoke_rows(catalog).get(name)
    if row is None:
        return
    node = shutil.which("node")
    if node is None:
        raise ValueError(f"skill smoke check needs Node: {name}")
    script, argument = row
    result = subprocess.run(
        [node, str(destination / script), argument],
        env={**os.environ, "ARCHIFY_UPDATE_CHECK_DISABLED": "1"},
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()[-4000:]
        raise ValueError(f"skill smoke check failed: {name}: {detail}")


def refresh(catalog: Path, lock: Path) -> None:
    lines = ["# Reviewed source snapshot: name|kind|source|git commit or archive SHA-256|selection"]
    with tempfile.TemporaryDirectory(prefix="dotfiles-skills-update-") as temporary:
        root = Path(temporary)
        repositories = {}
        smokes = smoke_rows(catalog)
        for name, kind, source, ref, path, selection in rows(catalog, 6):
            if kind == "git":
                key = (source, ref)
                if key not in repositories:
                    repo = root / f"repo-{len(repositories)}"
                    command = ["git", "clone", "--quiet", "--no-checkout", "--depth", "1",
                               "--branch", ref]
                    if source.startswith(("http://", "https://")):
                        command.append("--filter=blob:none")
                    subprocess.run([*command, source, str(repo)], check=True, timeout=180)
                    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
                    repositories[key] = (repo, revision)
                repo, revision = repositories[key]
                if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
                    raise ValueError(f"unsafe skill path: {name}")
                # A removed upstream skill must fail before replacing the lock.
                for resource in layout_paths(catalog, name, path):
                    subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{revision}:{resource}"],
                                   check=True, timeout=30)
                if name in smokes:
                    staged = root / f"smoke-{name}"
                    stage_git_skill(catalog, name, repo, revision, path, staged)
                    run_skill_smoke(catalog, name, staged)
            elif kind == "tarball":
                archive = root / "download.tgz"
                with urllib.request.urlopen(source, timeout=90) as response, archive.open("wb") as output:
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
                if name in smokes:
                    staged = root / f"smoke-{name}"
                    staged.mkdir(parents=True, exist_ok=True)
                    extract_git_tree(archive.read_bytes(), "", staged)
                    run_skill_smoke(catalog, name, staged)
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
