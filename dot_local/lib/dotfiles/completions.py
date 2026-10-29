"""Prepare native and pinned community Nu completions for managed CLIs.

This runs after tool installation. Shell startup loads only its regular local
files; it never downloads, checks out, or discovers a community script library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

WINDOWS = os.name == "nt"
NATIVE_GENERATORS = {
    "uv": ("generate-shell-completion", "nushell"),
    "just": ("--completions", "nushell"),
}


class CompletionError(ValueError):
    pass


def safe_destination(path: Path, home: Path) -> Path:
    if ".." in path.parts:
        raise CompletionError("completion state paths cannot contain parent traversal")
    path = path.absolute()
    try:
        relative = path.relative_to(home)
    except ValueError as error:
        raise CompletionError("completion state must remain in the designated home") from error
    current = home
    for part in (None, *relative.parts):
        if part is not None:
            current /= part
        if current.is_symlink():
            raise CompletionError(f"completion state is a symlink: {current}")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_catalog(path: Path) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("version") != 1 or not re.fullmatch(r"[a-f0-9]{40}", catalog.get("revision", "")):
        raise CompletionError("invalid Nu completion catalog version or revision")
    if not re.fullmatch(r"[a-f0-9]{64}", catalog.get("sha256", "")):
        raise CompletionError("invalid Nu completion archive checksum")
    expected_url = "https://codeload.github.com/nushell/nu_scripts/tar.gz/" + catalog["revision"]
    if catalog.get("url") != expected_url:
        raise CompletionError("Nu completion URL must identify the pinned upstream revision")
    commands = set()
    for module in catalog["modules"]:
        command, source = module["command"], PurePosixPath(module["path"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", command) or command in commands:
            raise CompletionError("duplicate or invalid Nu completion command")
        if command in NATIVE_GENERATORS:
            raise CompletionError("native completion command must not appear in the community catalog")
        if (source.is_absolute() or ".." in source.parts or source.suffix != ".nu"
                or "\\" in module["path"] or ":" in module["path"]):
            raise CompletionError("Nu completion sources must be relative .nu files")
        if not re.fullmatch(r"[a-f0-9]{64}", module.get("sha256", "")):
            raise CompletionError("invalid Nu completion module checksum")
        commands.add(command)
    return catalog


def managed_command(command: str, pixi: Path) -> Path | None:
    suffixes = ("", ".exe", ".cmd", ".bat") if WINDOWS else ("",)
    for suffix in suffixes:
        candidate = pixi / "bin" / (command + suffix)
        if candidate.is_file() and (WINDOWS or os.access(candidate, os.X_OK)):
            return candidate.absolute()
    return None


def selected_modules(catalog: dict, config_root: Path, pixi: Path, home: Path) -> list[dict]:
    declared = set()
    for name in ("pixi-global.toml", "pixi-bundles.toml"):
        manifest = safe_destination(config_root / "dotfiles" / name, home)
        with manifest.open("rb") as handle:
            desired = tomllib.load(handle)
        if desired.get("version") != 1:
            raise CompletionError("unsupported desired Pixi manifest version")
        for environment in desired.get("envs", {}).values():
            declared.update(environment.get("exposed", {}))
    # Never infer eligibility from the caller's PATH or unrelated preserved
    # environments. Windows wrappers use the same declared exposure names.
    candidates = catalog["modules"] + [
        {"command": command, "path": f"native/{command}-completions.nu"}
        for command in NATIVE_GENERATORS]
    return [module for module in candidates
            if module["command"] in declared and managed_command(module["command"], pixi)]


def generate_native(command: str, pixi: Path) -> bytes:
    executable = managed_command(command, pixi)
    if executable is None:
        raise CompletionError("managed native completion command disappeared: " + command)
    result = subprocess.run([str(executable), *NATIVE_GENERATORS[command]],
                            check=False, capture_output=True, text=True, encoding="utf-8", timeout=30)
    if result.returncode or not result.stdout.strip():
        raise CompletionError("native completion generator failed: " + command + ": " + result.stderr.strip())
    return result.stdout.encode("utf-8")


def module_source(catalog: dict, cache: Path, home: Path) -> Path:
    source = os.environ.get("DOTFILES_NU_SCRIPTS_ARCHIVE")
    if source:
        archive = Path(source)
        if archive.is_symlink() or sha256(archive) != catalog["sha256"]:
            raise CompletionError("Nu completion archive checksum mismatch")
        return archive
    cache = safe_destination(cache, home)
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def read_modules(source: Path, catalog: dict, selected: list[dict]) -> dict[str, bytes]:
    if source.is_dir():
        contents = {}
        for module in selected:
            cached = source / (module["sha256"] + ".nu")
            if cached.is_symlink():
                raise CompletionError("Nu completion cache is a symlink")
            if not cached.exists():
                descriptor, name = tempfile.mkstemp(prefix=".nu-scripts-", dir=source)
                temporary = Path(name)
                try:
                    url = ("https://raw.githubusercontent.com/nushell/nu_scripts/" + catalog["revision"]
                           + "/" + urllib.parse.quote(module["path"], safe="/"))
                    with os.fdopen(descriptor, "wb") as output, urllib.request.urlopen(url, timeout=90) as response:
                        shutil.copyfileobj(response, output)
                    if sha256(temporary) != module["sha256"]:
                        raise CompletionError("Nu completion module checksum mismatch: " + module["command"])
                    os.replace(temporary, cached)
                finally:
                    temporary.unlink(missing_ok=True)
            content = cached.read_bytes()
            if hashlib.sha256(content).hexdigest() != module["sha256"]:
                raise CompletionError("Nu completion module checksum mismatch: " + module["command"])
            contents[module["path"]] = content
        return contents
    root = "nu_scripts-" + catalog["revision"]
    wanted = {root + "/" + module["path"]: module["path"] for module in selected}
    contents = {}
    seen = set()
    with tarfile.open(source, "r:gz") as handle:
        for member in handle:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile())
                    or "\\" in member.name or ":" in member.name or not path.parts
                    or path.parts[0] != root or member.name in seen):
                raise CompletionError("unsafe Nu completion archive member")
            seen.add(member.name)
            if member.name in wanted:
                if not member.isfile():
                    raise CompletionError("Nu completion module is not a regular file")
                contents[wanted[member.name]] = handle.extractfile(member).read()
    if set(contents) != set(wanted.values()):
        raise CompletionError("pinned archive is missing an allowlisted Nu completion")
    for module in selected:
        if hashlib.sha256(contents[module["path"]]).hexdigest() != module["sha256"]:
            raise CompletionError("Nu completion module checksum mismatch: " + module["command"])
    return contents


def loader_text(directory: Path, selected: list[dict]) -> str:
    return "# Managed pinned Nu completions; prepared after tool installation.\n" + "".join(
        ("source " if module["command"] in NATIVE_GENERATORS else "use ")
        + json.dumps(str(directory / module["path"]), ensure_ascii=False)
        + ("\n" if module["command"] in NATIVE_GENERATORS else " *\n")
        for module in selected)


def validate(nu: Path, loader: Path) -> None:
    result = subprocess.run([str(nu), "--no-config-file", "-c",
                             "source " + json.dumps(str(loader), ensure_ascii=False) + "; null"],
                            check=False, capture_output=True, text=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise CompletionError("generated Nu completions failed validation: " + result.stderr.strip())


def prepare(config: Path, nu: Path, autoload: Path | None = None) -> int:
    home = Path(os.environ["HOME"]).absolute()
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    data_root = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
    pixi = Path(os.environ.get("PIXI_HOME", home / ".pixi"))
    safe_destination(config, home)
    catalog = read_catalog(config)
    selected = selected_modules(catalog, config_root, pixi, home)
    autoload = safe_destination(autoload or data_root / "nushell/vendor/autoload", home)
    target = safe_destination(autoload / "nu-scripts.nu", home)
    modules_root = safe_destination(data_root / "nushell/completions/nu-scripts", home)
    autoload.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".nu-scripts-", suffix=".nu", dir=autoload)
    staged_loader = Path(name)
    os.close(descriptor)
    try:
        final_directory = modules_root
        if selected:
            community = [module for module in selected if module["command"] not in NATIVE_GENERATORS]
            contents = {module["path"]: generate_native(module["command"], pixi)
                        for module in selected if module["command"] in NATIVE_GENERATORS}
            if community:
                cache = safe_destination(cache_root / "dotfiles/nu-scripts", home)
                contents.update(read_modules(module_source(catalog, cache, home), catalog, community))
            digest = hashlib.sha256()
            for path, content in sorted(contents.items()):
                digest.update(path.encode() + b"\0" + content)
            final_directory = safe_destination(modules_root / (catalog["revision"] + "-" + digest.hexdigest()[:16]), home)
            modules_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".nu-scripts-", dir=modules_root) as temporary:
                staging = Path(temporary)
                for path, content in contents.items():
                    destination = staging / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    destination.chmod(0o644)
                staged_loader.write_text(loader_text(staging, selected), encoding="utf-8")
                validate(nu, staged_loader)
                if final_directory.exists():
                    for path, content in contents.items():
                        destination = safe_destination(final_directory / path, home)
                        if not destination.is_file() or destination.read_bytes() != content:
                            raise CompletionError("managed Nu completion module differs from its pinned content")
                else:
                    os.replace(staging, final_directory)
                    # TemporaryDirectory cleanup tolerates the moved staging tree.
            staged_loader.write_text(loader_text(final_directory, selected), encoding="utf-8")
        else:
            staged_loader.write_text(loader_text(final_directory, []), encoding="utf-8")
        validate(nu, staged_loader)
        os.replace(staged_loader, target)
    finally:
        staged_loader.unlink(missing_ok=True)
    return len(selected)


def main() -> int:
    home = Path(os.environ["HOME"])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "dotfiles/nu-completions.json")
    parser.add_argument("--nu", type=Path, required=True)
    parser.add_argument("--autoload-dir", type=Path)
    arguments = parser.parse_args()
    try:
        count = prepare(arguments.config, arguments.nu, arguments.autoload_dir)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"dotfiles Nu completions: {error}", file=sys.stderr)
        return 1
    print(f"dotfiles Nu completions: prepared {count} matching installed commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
