"""Publish native and pinned community Nu completions for managed CLIs.

This runs after tool installation. Shell startup loads only its regular local
files; it never downloads, checks out, or discovers a community script library.

This module owns the whole completion publication lifecycle. A loader is the
file a Nushell startup imports; the canonical one lives in the vendor autoload
directory of the XDG data home, and a platform may add a native discovery copy.
The module builds and validates a generation, switches every managed loader to
it, and retires a generation only after no managed loader imports it. A
publication that reaches only some loaders therefore leaves every loader with
a complete generation. A loader stores each import as a JSON string, so the
retirement check decodes that reference instead of matching raw text.

Ownership decides which loader a publication may write. A canonical loader is
owned by declaration: the XDG loader the deployment writes, and the native
copy the platform's catalog names. A legacy loader is a path an earlier
publication may have written; the publication takes it over only when the file
on disk carries the managed marker. A device file of the same name is
preserved, and an existing native directory is no reason to create a loader
in it. The generation a preserved loader names stays published.

A generation is retired only when its bytes prove this deployment published
it. The publication writes only ``.nu`` module files and creates a directory
only for the parents of those files, so a generation that carries a
device-created empty directory or a file of another kind is not provably ours
and stays with that entry inside it.
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
import time
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import NamedTuple

WINDOWS = os.name == "nt"
# A published module directory: the pinned revision and a digest of its bytes.
PUBLISHED_DIRECTORY = re.compile(r"[0-9a-f]{40}-[0-9a-f]{16}")
# A published loader starts with this marker, so a file that carries it was
# written by an earlier publication.
LOADER_MARKER = "# Managed pinned Nu completions; prepared after tool installation."
NATIVE_GENERATORS = {
    "uv": ("generate-shell-completion", "nushell"),
    "just": ("--completions", "nushell"),
}


class CompletionError(ValueError):
    pass


def safe_destination(path: Path, home: Path) -> Path:
    """Reject a destination that leaves the home or crosses a symlink.

    The home can be reached through a symlinked path, and the same directory
    then carries two spellings. A destination is inside the home when it is
    spelled under the home or under its canonical spelling. The canonical
    spelling is compared lexically, so an alias outside the home that
    resolves into it is refused instead of being written through, and the
    chain check then walks the components the destination is written
    through, so a symlink inside the home is refused as well.
    """
    if ".." in path.parts:
        raise CompletionError("completion state paths cannot contain parent traversal")
    path = path.absolute()
    try:
        relative = path.relative_to(home)
    except ValueError:
        try:
            relative = path.relative_to(home.resolve())
        except ValueError as error:
            raise CompletionError("completion state must remain in the designated home") from error
        home = home.resolve()
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
    roots = [Path(os.environ.get("DOTFILES_COMMON_BIN", str(pixi / "bin"))), pixi / "bin"]
    for root in dict.fromkeys(roots):
        for suffix in suffixes:
            candidate = root / (command + suffix)
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
                os.close(descriptor)
                try:
                    url = ("https://raw.githubusercontent.com/nushell/nu_scripts/" + catalog["revision"]
                           + "/" + urllib.parse.quote(module["path"], safe="/"))
                    # A transient TLS failure must not abort the deployment;
                    # the checksum below still guards the bytes.
                    attempt = 0
                    while True:
                        attempt += 1
                        try:
                            # Reopen and truncate after either a failed open or
                            # an interrupted copy closed the previous attempt.
                            with temporary.open("wb") as output, urllib.request.urlopen(url, timeout=90) as response:
                                shutil.copyfileobj(response, output)
                            break
                        except OSError as error:
                            if attempt >= 3:
                                raise
                            time.sleep(3)
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
    return LOADER_MARKER + "\n" + "".join(
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
    # A deprecation warning still parses, and a device may legitimately run a Nu
    # newer than the pinned revision. Report it here so the drift surfaces at
    # preparation instead of as noise on every interactive startup.
    if "deprecated" in result.stderr:
        print("dotfiles Nu completions: warning: a pinned completion uses syntax the installed Nu "
              "deprecated; review the pinned nu_scripts revision", file=sys.stderr)


def managed_loader(path: Path) -> bool:
    """Whether the loader file on disk belongs to this deployment.

    A published loader starts with the managed marker, so a file that carries
    it was written by an earlier publication and the publication may take it
    over. A device file of the same name does not carry the marker and is
    never taken over.
    """
    try:
        if path.is_symlink() or not path.is_file():
            return False
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return text.startswith(LOADER_MARKER)


class Loaders(NamedTuple):
    """The loaders a publication writes and the ones it only observes."""

    managed: list[Path]
    observed: list[Path]


def loader_paths(data_root: Path, home: Path, canonical: Sequence[Path],
                 legacy: Sequence[Path]) -> Loaders:
    """The loader files this publication owns, and the ones it only observes.

    The canonical loader under the XDG data home is always managed, so a
    publication can never retire a generation the live loader still imports.
    A platform adds its native discovery copy as a canonical loader.

    A legacy loader is a path an earlier publication may have written. The
    publication takes it over only when the file on disk is demonstrably
    managed; a device file of the same name is preserved and observed, and a
    path without a file stays absent, because an existing native directory is
    no reason to create a duplicate loader.
    """
    managed = [safe_destination(data_root / "nushell/vendor/autoload/nu-scripts.nu", home)]
    for path in canonical:
        managed.append(safe_destination(path, home))
    ordered: list[Path] = []
    for path in managed:
        if path not in ordered:
            ordered.append(path)
    observed: list[Path] = []
    for path in legacy:
        destination = safe_destination(path, home)
        if destination in ordered:
            continue
        if managed_loader(destination):
            ordered.append(destination)
        elif destination.exists():
            observed.append(destination)
    return Loaders(ordered, observed)


def write_loader(path: Path, text: str) -> None:
    """Replace one managed loader with the published generation.

    The replacement is atomic, so a loader never holds a partial file. The
    temporary name carries no Nu suffix, so a publication that is interrupted
    leaves nothing a startup would try to parse.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".nu-scripts-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def switch_loaders(loaders: Sequence[Path], text: str) -> list[str]:
    """Switch every managed loader to the published generation.

    A loader the filesystem refuses keeps the generation it imports, so an
    interrupted publication leaves each loader with a complete generation.
    """
    failures = []
    for loader in loaders:
        try:
            write_loader(loader, text)
        except OSError as error:
            failures.append(f"{loader}: {error}")
    return failures


def loader_imports(text: str) -> list[str] | None:
    """The paths a loader imports, decoded from its encoded import syntax.

    A loader stores every import as a JSON string, so a path that carries a
    backslash or a quote appears escaped in the file. The raw text therefore
    cannot be matched against a filesystem path: a Windows path spells every
    separator twice, and a quoted home name escapes its quote. The encoded
    form is decoded instead.

    ``None`` reports an import the module cannot decode, so the caller keeps
    every generation.
    """
    decoder = json.JSONDecoder()
    imports: list[str] = []
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2 or parts[0] not in ("source", "use"):
            continue
        try:
            value, _ = decoder.raw_decode(parts[1].strip())
        except ValueError:
            return None
        if not isinstance(value, str):
            return None
        imports.append(value)
    return imports


def published_generation(path: str, published: dict[str, Path]) -> Path | None:
    """The published generation a decoded import path belongs to.

    The generation name is a path component of every import it publishes, so
    the component identifies the generation whatever separator or quoting the
    import path uses.
    """
    for part in re.split(r"[\\/]", path):
        entry = published.get(part)
        if entry is not None:
            return entry
    return None


def imported_generations(loaders: Sequence[Path], modules_root: Path) -> set[Path] | None:
    """The managed generations the managed loaders still import.

    ``None`` reports that a managed loader could not be read or decoded, so no
    generation can be retired safely.
    """
    if not modules_root.is_dir() or modules_root.is_symlink():
        return set()
    published = {entry.name: entry for entry in modules_root.iterdir()
                 if PUBLISHED_DIRECTORY.fullmatch(entry.name)}
    imported: set[Path] = set()
    for loader in loaders:
        try:
            text = loader.read_text(encoding="utf-8")
        except FileNotFoundError:
            # A loader that does not exist references no generation.
            continue
        except (OSError, UnicodeDecodeError):
            return None
        paths = loader_imports(text)
        if paths is None:
            return None
        for path in paths:
            entry = published_generation(path, published)
            if entry is not None:
                imported.add(entry)
    return imported


def mentioned_generations(loaders: Sequence[Path], modules_root: Path) -> set[Path]:
    """The published generations a preserved loader names.

    A device loader is not parsed as a managed import, so its text is
    searched for the generation name. The name is a plain token, so it
    survives every path encoding, and a generation a device loader names
    stays published under it.
    """
    if not modules_root.is_dir() or modules_root.is_symlink():
        return set()
    published = {entry.name: entry for entry in modules_root.iterdir()
                 if PUBLISHED_DIRECTORY.fullmatch(entry.name)}
    mentioned: set[Path] = set()
    for loader in loaders:
        try:
            text = loader.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # A loader that cannot be read may name any generation.
            return set(published.values())
        for name, entry in published.items():
            if name in text:
                mentioned.add(entry)
    return mentioned


def published_modules(directory: Path) -> list[tuple[str, Path]] | None:
    """The regular module files a published directory holds.

    The names are the module paths relative to the directory, which is how
    the publication named them. The publication writes only ``.nu`` module
    files and creates a directory only for the parents of those files, so an
    empty directory and a file of another kind are not part of a publication.
    A symlink or another irregular entry makes the directory something other
    than a publication, so the walk stops there.
    """
    modules: list[tuple[str, Path]] = []
    pending = [(directory, "")]
    while pending:
        current, prefix = pending.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            return None
        if not entries:
            # The publisher creates a directory only for the parents of the
            # module files it writes, so an empty one is a device entry.
            return None
        for entry in entries:
            name = prefix + entry.name
            if entry.is_symlink():
                return None
            if entry.is_dir():
                pending.append((entry, name + "/"))
            elif entry.is_file():
                if not entry.name.endswith(".nu"):
                    # Only the module files belong to a publication, so the
                    # bytes of another file are never read.
                    return None
                modules.append((name, entry))
            else:
                return None
    return modules


def published_digest(directory: Path) -> str | None:
    """The digest of the modules a published directory holds.

    A published directory is named after the digest of its modules, so a
    directory that recomputes to the digest in its name was published by
    this deployment. The recomputation reads the exact regular module files
    the directory holds, so a directory that carries an added or a foreign
    entry recomputes to a different digest and is never ours to remove. A
    directory that holds an entry the publisher never writes is not a
    publication at all, and no byte of it is read.

    ``None`` reports a directory this deployment cannot prove it published.
    """
    modules = published_modules(directory)
    if modules is None:
        return None
    digest = hashlib.sha256()
    for name, path in sorted(modules):
        try:
            content = path.read_bytes()
        except OSError:
            return None
        digest.update(name.encode() + b"\0" + content)
    return digest.hexdigest()


def published_by_deployment(directory: Path) -> bool:
    """Whether this deployment published the directory.

    The name of a published directory carries the digest of its modules, so
    a directory that recomputes to that digest is one this deployment
    published. A device directory that carries the published shape but other
    bytes recomputes to a different digest and is never removed.
    """
    _, _, digest = directory.name.partition("-")
    computed = published_digest(directory)
    return computed is not None and computed.startswith(digest)


def retire_published(root: Path, imported: set[Path]) -> None:
    """Remove the module directories no loader imports any more.

    Only a directory this deployment published is removed, and only after
    every managed loader stopped importing it and no preserved device loader
    names it. A device-created entry, a symlink, and a directory whose bytes
    do not match the digest in its name never match, so none of them is ever
    touched. A published generation that carries a device-created empty
    directory or a file of another kind is not provably ours, so it stays
    with that entry inside it.
    """
    if not root.is_dir() or root.is_symlink():
        return
    for entry in root.iterdir():
        if entry in imported or not PUBLISHED_DIRECTORY.fullmatch(entry.name):
            continue
        if entry.is_symlink() or not entry.is_dir():
            continue
        if not published_by_deployment(entry):
            continue
        shutil.rmtree(entry)


def validate_loader(nu: Path, text: str, directory: Path) -> None:
    """Check a loader with the installed Nu before any managed loader switches."""
    descriptor, name = tempfile.mkstemp(prefix=".nu-scripts-", suffix=".tmp", dir=directory)
    temporary = Path(name)
    os.close(descriptor)
    try:
        temporary.write_text(text, encoding="utf-8")
        validate(nu, temporary)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(config: Path, nu: Path, loaders: Sequence[Path] = (),
            legacy: Sequence[Path] = ()) -> int:
    """Publish the pinned completions to every managed loader.

    The canonical loader and the given extra loaders are switched to the
    published generation. A legacy loader is switched only when it is
    demonstrably managed. A generation is retired only after no loader
    imports it, so an interrupted publication leaves every loader usable.
    """
    home = Path(os.environ["HOME"]).absolute()
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    data_root = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
    pixi = Path(os.environ.get("PIXI_HOME", home / ".pixi"))
    safe_destination(config, home)
    catalog = read_catalog(config)
    selected = selected_modules(catalog, config_root, pixi, home)
    publication = loader_paths(data_root, home, loaders, legacy)
    managed = publication.managed
    modules_root = safe_destination(data_root / "nushell/completions/nu-scripts", home)
    modules_root.mkdir(parents=True, exist_ok=True)
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
        with tempfile.TemporaryDirectory(prefix=".nu-scripts-", dir=modules_root) as temporary:
            staging = Path(temporary)
            for path, content in contents.items():
                destination = staging / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o644)
            validate_loader(nu, loader_text(staging, selected), modules_root)
            if final_directory.exists():
                for path, content in contents.items():
                    destination = safe_destination(final_directory / path, home)
                    if not destination.is_file() or destination.read_bytes() != content:
                        raise CompletionError("managed Nu completion module differs from its pinned content")
            else:
                os.replace(staging, final_directory)
                # TemporaryDirectory cleanup tolerates the moved staging tree.
    text = loader_text(final_directory, selected)
    # The new generation is validated before any managed loader switches.
    validate_loader(nu, text, modules_root)
    failures = switch_loaders(managed, text)
    imported = imported_generations(managed, modules_root)
    if imported is None:
        print("dotfiles Nu completions: kept every published generation because a managed "
              "loader could not be read", file=sys.stderr)
    else:
        # The published directories carry a content digest, so a selection or
        # catalog change leaves the previous bytes behind. A generation is
        # retired once no managed loader imports it any more, and a preserved
        # device loader keeps the generation it names.
        retire_published(modules_root, imported | mentioned_generations(publication.observed, modules_root))
    if failures:
        raise CompletionError("managed Nu completion loader switch failed: " + "; ".join(failures))
    return len(selected)


def main() -> int:
    home = Path(os.environ["HOME"])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "dotfiles/nu-completions.json")
    parser.add_argument("--nu", type=Path, required=True)
    parser.add_argument("--loader", type=Path, action="append", default=[],
                        help="an additional managed loader file; repeat it for every active path")
    parser.add_argument("--legacy-loader", type=Path, action="append", default=[],
                        help="a loader path an earlier publication may own; it is taken over "
                             "only when the file on disk is demonstrably managed")
    arguments = parser.parse_args()
    try:
        count = prepare(arguments.config, arguments.nu, arguments.loader, arguments.legacy_loader)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"dotfiles Nu completions: {error}", file=sys.stderr)
        return 1
    print(f"dotfiles Nu completions: prepared {count} matching installed commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
