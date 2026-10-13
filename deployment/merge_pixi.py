"""Merge repo-owned desired entries while preserving the device's registry.

Executed by a pinned Pixi Python bootstrap environment, before global sync.
This module is an installer adapter, not a source payload applied into HOME.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib


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
    desired_path, registry_path = map(Path, sys.argv[1:])
    if registry_path.is_symlink() or registry_path.parent.is_symlink():
        raise ValueError("Pixi registry or parent is a symlink")
    with desired_path.open("rb") as handle:
        desired = tomllib.load(handle)
    existing = {"version": 1, "envs": {}}
    if registry_path.exists():
        with registry_path.open("rb") as handle:
            existing = tomllib.load(handle)
    if existing.get("version") != 1:
        raise ValueError("unsupported Pixi registry version")
    environments = existing.setdefault("envs", {})
    for name, owned in desired["envs"].items():
        environment = environments.setdefault(name, {})
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
