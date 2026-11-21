"""Read expected direct versions from the source catalogs in contract tests."""
import json
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


def common_pin(package):
    for line in (SOURCE / "deployment/common-tools.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        for specification in line.split("|")[1].split(","):
            name, version = specification.rsplit("==", 1)
            if name == package:
                return version
    raise AssertionError(f"missing common version pin: {package}")


def agent_default_pin(name):
    """The catalog default of one agent.

    The repository catalog owns the default version of every agent. The
    deployment-owned provider record (Bun or native) carries it; an
    installer-owned record carries only the floor the device accepts.
    """
    for record in (agent_pins(), native_agent_pins()):
        if name in record:
            return record[name]["version"]
    raise AssertionError(f"missing agent version pin: {name}")


def installer_floor_pin(name):
    """The catalog version floor of one installer-owned command."""
    for line in (SOURCE / "deployment/installer-tools.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if fields[0] == name:
            return fields[4]
    raise AssertionError(f"missing installer version floor: {name}")


def distinct_version(default):
    """A version that differs from the catalog default.

    A device override replaces the repository default, so the fixture needs a
    version of its own that stays different when the catalog moves.
    """
    parts = default.rsplit(".", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return f"{parts[0]}.{int(parts[1]) + 1}"
    return default + ".1"


def agent_pins():
    result = {}
    for line in (SOURCE / "deployment/agents/providers.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            fields = line.split("|")
            if fields[1] != "bun":
                continue
            name, package, version, commands, minimum_node, trusted = (
                fields[0], fields[2], fields[4], fields[6], fields[11], fields[12])
            result[name] = {"package": package, "version": version, "commands": commands,
                            "minimumNode": minimum_node, "trusted": trusted}
    return result


def native_agent_pins():
    result = {}
    for line in (SOURCE / "deployment/agents/providers.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            fields = line.split("|")
            if fields[1] != "native":
                continue
            name, version, commands, platforms, manifest = (
                fields[0], fields[4], fields[6], fields[7], fields[13])
            result[name] = {"version": version, "commands": commands,
                            "platforms": platforms, "manifest": manifest}
    return result


def windows_assets():
    assets = json.loads((SOURCE / "deployment/windows-assets.json").read_text(encoding="utf-8"))
    return {asset["name"]: asset for asset in assets}


def manager_pin(name):
    filename = "common.sh" if name in ("PIXI_VERSION", "RUSTUP_VERSION") else "managers.sh"
    text = (SOURCE / "deployment" / filename).read_text(encoding="utf-8")
    match = re.search(rf"^{name}=([^\r\n]+)$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"missing manager version pin: {name}")
    return match.group(1)
