"""Merge repo-owned desired entries while preserving the device's registry.

Executed by a pinned Pixi Python bootstrap environment, before global sync.
This module is an installer adapter, not a source payload applied into HOME.
"""
import json
import os
import sys
import tempfile
import tomllib
from pathlib import Path

# Frozen ownership from the former uutils catalog row. Only identity mappings
# in the selected uutils environment are retired; device aliases stay local.
RETIRED_UUTILS_EXPOSURES = frozenset({
    '[', 'arch', 'b2sum', 'base32', 'base64', 'basename', 'basenc',
    'cat', 'chgrp', 'chmod', 'chown', 'chroot', 'cksum', 'comm',
    'cp', 'csplit', 'cut', 'date', 'dd', 'df', 'dir',
    'dircolors', 'dirname', 'du', 'echo', 'env', 'expand', 'expr',
    'factor', 'false', 'fmt', 'fold', 'groups', 'head', 'hostid',
    'hostname', 'id', 'install', 'join', 'kill', 'link', 'ln',
    'logname', 'ls', 'md5sum', 'mkdir', 'mkfifo', 'mknod', 'mktemp',
    'more', 'mv', 'nice', 'nl', 'nohup', 'nproc', 'numfmt',
    'od', 'paste', 'pathchk', 'pinky', 'pr', 'printenv', 'printf',
    'ptx', 'pwd', 'readlink', 'realpath', 'rm', 'rmdir', 'seq',
    'sha1sum', 'sha224sum', 'sha256sum', 'sha384sum', 'sha512sum', 'shred', 'shuf',
    'sleep', 'sort', 'split', 'stat', 'stdbuf', 'stty', 'sum',
    'sync', 'tac', 'tail', 'tee', 'test', 'timeout', 'touch',
    'tr', 'true', 'truncate', 'tsort', 'tty', 'uname', 'unexpand',
    'uniq', 'unlink', 'uptime', 'users', 'vdir', 'wc', 'who',
    'whoami', 'yes',
})


def retire_uutils_aliases(name, desired, environment):
    if name != "uutils-coreutils" or desired.get("exposed") != {"coreutils": "coreutils"}:
        return False
    exposed = environment.get("exposed", {})
    retired = [alias for alias in RETIRED_UUTILS_EXPOSURES if exposed.get(alias) == alias]
    for alias in retired:
        del exposed[alias]
    return bool(retired)


def backup_before_coreutils_migration(registry_path, contents):
    backup = registry_path.with_name(registry_path.name + ".before-coreutils-namespacing.bak")
    if backup.is_symlink() or (backup.exists() and not backup.is_file()):
        raise ValueError("coreutils migration backup must be a regular file")
    if backup.exists():
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".coreutils-backup-", dir=registry_path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        # Publish a complete private snapshot without replacing an earlier one.
        try:
            os.link(temporary, backup)
        except FileExistsError:
            if backup.is_symlink() or not backup.is_file():
                raise ValueError("coreutils migration backup must be a regular file")
    finally:
        os.unlink(temporary)


def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{toml_value(key)} = {toml_value(item)}" for key, item in value.items()) + " }"
    raise ValueError(f"unsupported manifest value: {type(value).__name__}")


def main():
    arguments = sys.argv[1:]
    provided = set()
    if arguments[:1] == ["--providers"]:
        providers = Path(arguments[1])
        if providers.is_symlink() or not providers.is_file():
            raise ValueError("common provider state must be a regular file")
        for line in providers.read_text(encoding="utf-8").splitlines():
            name, provider, _version, _minimum = line.split("|")
            if provider in ("homebrew", "adopted"):
                provided.add(name)
        arguments = arguments[2:]
    desired_paths = list(map(Path, arguments[:-1]))
    registry_path = Path(sys.argv[-1])
    if not desired_paths:
        raise ValueError("at least one desired manifest is required")
    if registry_path.is_symlink() or registry_path.parent.is_symlink():
        raise ValueError("Pixi registry or parent is a symlink")
    existing = {"version": 1, "envs": {}}
    original = None
    if registry_path.exists():
        original = registry_path.read_bytes()
        existing = tomllib.loads(original.decode("utf-8"))
    if existing.get("version") != 1:
        raise ValueError("unsupported Pixi registry version")
    environments = existing.setdefault("envs", {})
    retired_coreutils = False
    for desired_path in desired_paths:
        with desired_path.open("rb") as handle:
            desired = tomllib.load(handle)
        for name, owned in desired["envs"].items():
            if name in provided:
                continue
            environment = environments.setdefault(name, {})
            retired_coreutils |= retire_uutils_aliases(name, owned, environment)
            for field, value in owned.items():
                if field in ("dependencies", "exposed"):
                    environment.setdefault(field, {}).update(value)
                elif field == "channels":
                    environment[field] = list(dict.fromkeys(value + environment.get(field, [])))
                else:
                    environment[field] = value
    exposed_owners = {}
    for name, environment in environments.items():
        for command in environment.get("exposed", {}):
            if command in exposed_owners:
                raise ValueError(f"exposed command {command!r} is also owned by {exposed_owners[command]!r}; resolve the collision explicitly")
            exposed_owners[command] = name
    # Inline TOML values support the global schema's nested source-package
    # specifications as well as ordinary dependency/exposure tables.
    text = "# Device-local registry merged with dotfiles desired entries.\n"
    text += "\n".join(f"{toml_value(key)} = {toml_value(value)}" for key, value in existing.items()) + "\n"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if retired_coreutils and original is not None:
        backup_before_coreutils_migration(registry_path, original)
    mode = registry_path.stat().st_mode & 0o777 if registry_path.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix=".dotfiles-", dir=registry_path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, registry_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError) as error:
        print(f"dotfiles: merge Pixi registry: {error}", file=sys.stderr)
        sys.exit(1)
