"""Check skill pins or explicitly refresh a reviewable lock; never deploy skills."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]


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


def check(catalog: Path, lock: Path) -> None:
    declarations = {row[0]: row for row in rows(catalog, 5)}
    pins = {row[0]: row for row in rows(lock, 4)}
    if declarations.keys() != pins.keys():
        raise ValueError("skill catalog and lock names differ; refresh the lock")
    for name, declaration in declarations.items():
        pin = pins[name]
        if declaration[:3] != pin[:3]:
            raise ValueError(f"skill lock source mismatch: {name}")
        pattern = r"[a-f0-9]{40}" if pin[1] == "git" else r"[a-f0-9]{64}"
        if pin[1] not in ("git", "tarball") or not re.fullmatch(pattern, pin[3]):
            raise ValueError(f"invalid skill pin: {name}")


def refresh(catalog: Path, lock: Path) -> None:
    lines = ["# Reviewed source snapshot: name|kind|source|git commit or archive SHA-256"]
    with tempfile.TemporaryDirectory(prefix="dotfiles-skills-update-") as temporary:
        root = Path(temporary)
        repositories = {}
        for name, kind, source, ref, path in rows(catalog, 5):
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
                subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{revision}:{path}/SKILL.md"],
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
            lines.append("|".join((name, kind, source, revision)))
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "refresh"))
    parser.add_argument("--catalog", type=Path, default=SOURCE / "deployment/skills.tsv")
    parser.add_argument("--lock", type=Path, default=SOURCE / "deployment/skills.lock.tsv")
    args = parser.parse_args()
    if args.command == "refresh":
        refresh(args.catalog, args.lock)
    check(args.catalog, args.lock)
    print(f"skill pins: checked {len(rows(args.lock, 4))} entries")


if __name__ == "__main__":
    main()
