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


def agent_pins():
    result = {}
    for line in (SOURCE / "deployment/agents/catalog.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, package, version, commands, minimum_node, trusted = line.split("|")[:6]
            result[name] = {"package": package, "version": version, "commands": commands,
                            "minimumNode": minimum_node, "trusted": trusted}
    return result


def native_agent_pins():
    result = {}
    for line in (SOURCE / "deployment/agents/native.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, version, commands, platforms, manifest = line.split("|")[:5]
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
