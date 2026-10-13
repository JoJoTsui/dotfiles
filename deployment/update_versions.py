"""Refresh the repo-owned version set through an explicit review proposal.

Normal deployment never calls this module. ``refresh`` edits a temporary copy,
regenerates changed Bun locks, and installs the candidate into the worktree only
after all source and runtime compatibility checks pass.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_~-]*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
WINDOWS_ASSETS = {
    "pixi": "pixi", "chezmoi": "chezmoi", "rustup": "rustup",
    "bun": "bun", "atuin": "atuin", "git-bash": "git-bash",
    "helix": "helix", "jq": "jq",
}


class VersionError(ValueError):
    pass


def rows(path: Path, minimum_fields: int) -> list[list[str]]:
    result = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) < minimum_fields:
            raise VersionError(f"{path}:{line_number}: expected at least {minimum_fields} pipe-separated fields")
        result.append(fields)
    return result


def exact_specs(value: str, context: str) -> dict[str, str]:
    result = {}
    for item in value.split(","):
        if "==" not in item:
            raise VersionError(f"{context}: expected exact package pin, got {item!r}")
        package, version = item.rsplit("==", 1)
        if not package or not VERSION_RE.fullmatch(version):
            raise VersionError(f"{context}: invalid exact package pin {item!r}")
        if package in result:
            raise VersionError(f"{context}: duplicate package {package!r}")
        result[package] = version
    return result


def common_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for row in rows(root / "deployment/common-tools.tsv", 4):
        for package, version in exact_specs(row[1], f"common environment {row[0]}").items():
            if package in versions and versions[package] != version:
                raise VersionError(f"common package {package!r} has inconsistent pins")
            versions[package] = version
    return versions


def bundle_versions(root: Path) -> dict[tuple[str, str], str]:
    versions: dict[tuple[str, str], str] = {}
    for row in rows(root / "deployment/bundle-tools.tsv", 6):
        bundle = row[0]
        for package, version in exact_specs(row[2], f"bundle {bundle}/{row[1]}").items():
            key = (bundle, package)
            if key in versions and versions[key] != version:
                raise VersionError(f"bundle package {bundle}/{package} has inconsistent target pins")
            versions[key] = version
    return versions


def agent_rows(root: Path) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows(root / "deployment/agents/catalog.tsv", 6):
        name, package, version, commands, minimum_node, trusted = row[:6]
        if name in result:
            raise VersionError(f"duplicate agent catalog entry: {name}")
        if not VERSION_RE.fullmatch(version) or not re.fullmatch(r"\d+(?:\.\d+){1,2}", minimum_node):
            raise VersionError(f"invalid agent version or minimum Node pin for {name}")
        result[name] = {"package": package, "version": version, "commands": commands,
                        "minimumNode": minimum_node, "trusted": trusted}
    return result


def parse_bun_lock(path: Path) -> dict[str, Any]:
    # Bun's text lock is JSON with trailing commas.
    source = re.sub(r",(?=\s*[}\]])", "", path.read_text(encoding="utf-8"))
    try:
        parsed = json.loads(source)
    except json.JSONDecodeError as error:
        raise VersionError(f"invalid Bun lockfile {path}: {error}") from error
    if not isinstance(parsed, dict) or not isinstance(parsed.get("packages"), dict):
        raise VersionError(f"unsupported Bun lockfile structure: {path}")
    return parsed


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+].*)?", value)
    if not match:
        raise VersionError(f"unsupported Node version: {value!r}")
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def compare(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return (left > right) - (left < right)


def _range_token_matches(version: tuple[int, int, int], token: str) -> bool:
    token = token.strip().lstrip("v")
    if token in ("", "*", "x", "X"):
        return True
    wildcard = re.fullmatch(r"(\d+)(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?", token)
    if wildcard and any(part and part.lower() == "x" or part == "*" for part in wildcard.groups()[1:]):
        major, minor, patch = wildcard.groups()
        if version[0] != int(major):
            return False
        if minor and minor.lower() not in ("x", "*") and version[1] != int(minor):
            return False
        return not (patch and patch.lower() not in ("x", "*") and version[2] != int(patch))
    operator_match = re.match(r"^(>=|<=|>|<|=|\^|~)?(.+)$", token)
    if not operator_match:
        raise VersionError(f"unsupported Node engine range token: {token!r}")
    operator, raw = operator_match.groups()
    target = version_tuple(raw)
    if operator == "^":
        if compare(version, target) < 0:
            return False
        if target[0]:
            upper = (target[0] + 1, 0, 0)
        elif target[1]:
            upper = (0, target[1] + 1, 0)
        else:
            upper = (0, 0, target[2] + 1)
        return compare(version, upper) < 0
    if operator == "~":
        upper = (target[0], target[1] + 1, 0)
        return compare(version, target) >= 0 and compare(version, upper) < 0
    relation = compare(version, target)
    return {None: relation == 0, "=": relation == 0, ">=": relation >= 0,
            ">": relation > 0, "<=": relation <= 0, "<": relation < 0}[operator]


def node_satisfies(version: str, expression: str) -> bool:
    """Handle npm's common comparator, wildcard, caret, tilde and OR ranges."""
    satisfied = False
    for alternative in expression.split("||"):
        tokens = alternative.replace(",", " ").split()
        if tokens:
            matches = [_range_token_matches(version_tuple(version), token) for token in tokens]
            satisfied = satisfied or all(matches)
    return satisfied


def check(root: Path) -> dict[str, int]:
    common = common_versions(root)
    bundles = bundle_versions(root)
    agents = agent_rows(root)
    if not agents:
        raise VersionError("agent catalog is empty")
    node_pin = common.get("nodejs")
    if node_pin is None:
        raise VersionError("common catalog is missing the Node runtime pin")
    for name, agent in agents.items():
        if version_tuple(node_pin) < version_tuple(agent["minimumNode"]):
            raise VersionError(f"Node {node_pin} is below {name}'s declared minimum {agent['minimumNode']}")
        directory = root / "deployment/agents" / name
        try:
            package_json = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise VersionError(f"cannot read {name} package.json: {error}") from error
        if package_json.get("dependencies") != {agent["package"]: agent["version"]}:
            raise VersionError(f"{name} catalog and package.json pins disagree")
        lock = parse_bun_lock(directory / "bun.lock")
        workspace = lock.get("workspaces", {}).get("")
        if not isinstance(workspace, dict) or workspace.get("dependencies") != package_json["dependencies"]:
            raise VersionError(f"{name} package.json and bun.lock workspace pins disagree")
        locked_package = lock["packages"].get(agent["package"])
        expected = f"{agent['package']}@{agent['version']}"
        if not isinstance(locked_package, list) or not locked_package or locked_package[0] != expected:
            raise VersionError(f"{name} bun.lock package entry does not resolve to {expected}")
        if package_json.get("trustedDependencies", []) != lock.get("trustedDependencies", []):
            raise VersionError(f"{name} trusted lifecycle dependencies differ from bun.lock")

    assets_path = root / "deployment/windows-assets.json"
    try:
        assets_list = json.loads(assets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VersionError(f"cannot read Windows asset catalog: {error}") from error
    assets = {item.get("name"): item for item in assets_list if isinstance(item, dict)}
    if set(assets) != set(WINDOWS_ASSETS):
        raise VersionError("Windows asset catalog must contain exactly the eight declared managed exceptions")
    for name, asset in assets.items():
        if not isinstance(asset.get("url"), str) or not asset["url"].startswith("https://"):
            raise VersionError(f"Windows asset {name} must use HTTPS")
        if not SHA256_RE.fullmatch(str(asset.get("sha256", ""))):
            raise VersionError(f"Windows asset {name} must have a lowercase SHA-256 digest")
        if not VERSION_RE.fullmatch(str(asset.get("version", ""))):
            raise VersionError(f"Windows asset {name} has an invalid version")

    common_asset_pairs = {"bun": "bun", "atuin": "atuin", "helix": "helix", "jq": "jq"}
    for asset_name, package in common_asset_pairs.items():
        if assets[asset_name]["version"] != common.get(package):
            raise VersionError(f"Windows {asset_name} exception and common {package} pins disagree")
    for asset_name, constant, file_name in (
        ("pixi", "PIXI_VERSION", "common.sh"),
        ("rustup", "RUSTUP_VERSION", "common.sh"),
        ("chezmoi", "CHEZMOI_VERSION", "managers.sh"),
    ):
        text = (root / "deployment" / file_name).read_text(encoding="utf-8")
        match = re.search(rf"^{constant}=([^\r\n]+)$", text, re.MULTILINE)
        if not match or match.group(1) != assets[asset_name]["version"]:
            raise VersionError(f"Windows {asset_name} exception and {constant} pin disagree")

    return {
        "commonEnvironments": len(rows(root / "deployment/common-tools.tsv", 4)),
        "commonPins": len(common),
        "bundleToolRows": len(rows(root / "deployment/bundle-tools.tsv", 6)),
        "bundlePins": len(bundles),
        "agents": len(agents),
        "windowsAssets": len(assets),
    }


def _rewrite_tsv_pins(path: Path, updates: dict[str, str], field_index: int,
                      name_for_error: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    found: set[str] = set()
    output = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            output.append(line)
            continue
        fields = line.rstrip("\r\n").split("|")
        specs = exact_specs(fields[field_index], f"{path}:{fields[0]}")
        for package, version in updates.items():
            if package in specs:
                specs[package] = version
                found.add(package)
        fields[field_index] = ",".join(f"{package}=={version}" for package, version in specs.items())
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        output.append("|".join(fields) + ending)
    missing = set(updates) - found
    if missing:
        raise VersionError(f"unknown {name_for_error} package(s): {', '.join(sorted(missing))}")
    path.write_text("".join(output), encoding="utf-8")


def _rewrite_bundle_pins(path: Path, updates: dict[str, dict[str, str]]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    found: set[tuple[str, str]] = set()
    output = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            output.append(line)
            continue
        fields = line.rstrip("\r\n").split("|")
        bundle = fields[0]
        specs = exact_specs(fields[2], f"{path}:{bundle}/{fields[1]}")
        for package, version in updates.get(bundle, {}).items():
            if package in specs:
                specs[package] = version
                found.add((bundle, package))
        fields[2] = ",".join(f"{package}=={version}" for package, version in specs.items())
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        output.append("|".join(fields) + ending)
    missing = {(bundle, package) for bundle, packages in updates.items() for package in packages} - found
    if missing:
        names = ", ".join(f"{bundle}/{package}" for bundle, package in sorted(missing))
        raise VersionError(f"unknown bundle package(s): {names}")
    path.write_text("".join(output), encoding="utf-8")


def _proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VersionError("proposal root must be a JSON object")
    allowed = {"common", "bundles", "agents", "managers", "windowsAssets"}
    if set(value) - allowed:
        raise VersionError(f"unknown proposal section(s): {', '.join(sorted(set(value) - allowed))}")
    if not value:
        raise VersionError("proposal must change at least one pin")
    for section in ("common", "agents", "managers"):
        entries = value.get(section, {})
        if not isinstance(entries, dict):
            raise VersionError(f"proposal {section} must be an object")
        for name, version in entries.items():
            if not isinstance(name, str) or not isinstance(version, str) or not VERSION_RE.fullmatch(version):
                raise VersionError(f"invalid version entry in proposal {section}: {name!r}")
    bundle_entries = value.get("bundles", {})
    if not isinstance(bundle_entries, dict):
        raise VersionError("proposal bundles must be an object")
    normalized_bundles: dict[str, dict[str, str]] = {}
    for key, version in bundle_entries.items():
        parts = key.split("/", 1) if isinstance(key, str) else []
        if len(parts) != 2 or not all(parts) or not isinstance(version, str) or not VERSION_RE.fullmatch(version):
            raise VersionError(f"bundle proposal keys must be bundle/package with an exact version: {key!r}")
        normalized_bundles.setdefault(parts[0], {})[parts[1]] = version
    value["bundles"] = normalized_bundles
    managers = value.get("managers", {})
    if set(managers) - {"pixi", "rustup", "chezmoi"}:
        raise VersionError("manager proposal keys are limited to pixi, rustup, and chezmoi")
    windows_assets = value.get("windowsAssets", {})
    if not isinstance(windows_assets, dict):
        raise VersionError("proposal windowsAssets must be an object")
    if set(windows_assets) - set(WINDOWS_ASSETS):
        raise VersionError("proposal contains an unknown Windows exception asset")
    for name, asset in windows_assets.items():
        if not isinstance(asset, dict) or set(asset) != {"version", "url", "sha256"}:
            raise VersionError(f"Windows asset proposal for {name} must contain version, url, and sha256")
        if not isinstance(asset["version"], str) or not VERSION_RE.fullmatch(asset["version"]):
            raise VersionError(f"invalid Windows asset version for {name}")
        if not isinstance(asset["url"], str) or not asset["url"].startswith("https://"):
            raise VersionError(f"Windows asset proposal for {name} must use HTTPS")
        if not isinstance(asset["sha256"], str) or not SHA256_RE.fullmatch(asset["sha256"]):
            raise VersionError(f"Windows asset proposal for {name} requires a lowercase SHA-256")
    value["windowsAssets"] = windows_assets
    return value


def _set_constant(path: Path, name: str, version: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(name)}=[^\r\n]+$", re.MULTILINE)
    updated, count = pattern.subn(f"{name}={version}", text)
    if count != 1:
        raise VersionError(f"expected one {name} pin in {path}")
    path.write_text(updated, encoding="utf-8")


def npm_metadata(package: str, version: str) -> dict[str, Any]:
    url = f"https://registry.npmjs.org/{quote(package, safe='@')}/{quote(version, safe='')}"
    try:
        with urlopen(url, timeout=30) as response:
            payload = response.read()
    except HTTPError as error:
        if error.code == 429 or error.code >= 500:
            raise VersionError(f"npm registry unavailable (HTTP {error.code}) for {package}@{version}; engine verification is pending") from error
        raise VersionError(f"npm registry returned HTTP {error.code} for {package}@{version}") from error
    except URLError as error:
        raise VersionError(f"npm registry unavailable for {package}@{version}; engine verification is pending ({type(error.reason).__name__})") from error
    except TimeoutError as error:
        raise VersionError(f"npm registry timed out for {package}@{version}; engine verification is pending") from error
    try:
        metadata = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise VersionError(f"npm registry returned invalid metadata for {package}@{version}") from error
    if not isinstance(metadata, dict) or metadata.get("version") != version:
        raise VersionError(f"npm registry did not return the requested package {package}@{version}")
    return metadata


def validate_node_engine(metadata: dict[str, Any], node_pin: str, name: str, version: str) -> None:
    engines = metadata.get("engines", {})
    if not isinstance(engines, dict):
        raise VersionError(f"npm metadata for {name}@{version} has an invalid engines object")
    node_range = engines.get("node")
    if node_range is None:
        return
    if not isinstance(node_range, str):
        raise VersionError(f"npm metadata for {name}@{version} has an invalid Node engine")
    if not node_satisfies(node_pin, node_range):
        raise VersionError(f"Node {node_pin} does not satisfy {name}@{version} engine {node_range!r}")


def tool_diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    output = result.stderr + result.stdout
    if re.search(r"enotfound|econn|timed? ?out|network|failed.{0,30}fetch|fetch.{0,30}failed|http 5\d\d|http 429|connection refused|unable to connect",
                 output, re.IGNORECASE):
        return "network or registry unavailable; verification for this package is pending"
    safe_lines = []
    for line in output.splitlines():
        if re.search(r"token|password|authorization|secret|credential", line, re.IGNORECASE):
            safe_lines.append("[sensitive diagnostic line redacted]")
            continue
        safe_lines.append(re.sub(r"(https?://)[^/\s@]+@", r"\1[redacted]@", line))
    return "\n".join(safe_lines[-8:])[-1200:] or "no diagnostic output"


def _isolated_env(home: Path, executable: Path) -> dict[str, str]:
    allowed = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment.update({
        "HOME": str(home), "PATH": os.pathsep.join((str(executable.parent), "/usr/bin", "/bin")),
        "BUN_INSTALL": str(home / ".bun"), "BUN_INSTALL_CACHE_DIR": str(home / ".cache/bun"),
        "NPM_CONFIG_GLOBAL": "false", "npm_config_global": "false", "npm_config_location": "project",
        "CI": "1", "DO_NOT_TRACK": "1",
    })
    return environment


def _regenerate_bun_locks(root: Path, changed_agents: set[str], bun: Path,
                          current_bun_pin: str) -> None:
    if not changed_agents:
        return
    if not bun.is_absolute() or not bun.is_file():
        raise VersionError("--bun must point to an absolute Bun executable")
    try:
        actual = subprocess.run([str(bun), "--version"], check=True, capture_output=True,
                                text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise VersionError(f"cannot run Bun from --bun: {type(error).__name__}") from error
    if actual != current_bun_pin:
        raise VersionError(f"lock refresh requires the currently pinned Bun {current_bun_pin}; got {actual}")
    with tempfile.TemporaryDirectory(prefix="dotfiles-bun-lock-") as temporary:
        isolated_home = Path(temporary) / "home"
        isolated_home.mkdir()
        environment = _isolated_env(isolated_home, bun)
        for name in sorted(changed_agents):
            source = root / "deployment/agents" / name
            project = Path(temporary) / "projects" / name
            project.mkdir(parents=True)
            shutil.copy2(source / "package.json", project / "package.json")
            shutil.copy2(source / "bun.lock", project / "bun.lock")
            result = subprocess.run([str(bun), "install", "--cwd", str(project),
                                     "--lockfile-only", "--ignore-scripts"],
                                   check=False, env=environment, capture_output=True, text=True, timeout=900)
            if result.returncode:
                detail = tool_diagnostic(result)
                raise VersionError(f"Bun lock refresh failed for {name} (exit {result.returncode}): {detail}")
            if not (project / "bun.lock").is_file():
                raise VersionError(f"Bun did not write the expected lockfile for {name}")
            shutil.copy2(project / "bun.lock", source / "bun.lock")


def refresh(root: Path, proposal_path: Path, bun: Path) -> list[Path]:
    try:
        proposal = _proposal(json.loads(proposal_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise VersionError(f"cannot read version proposal: {type(error).__name__}") from error
    check(root)
    current_bun_pin = common_versions(root).get("bun")
    if current_bun_pin is None:
        raise VersionError("cannot find the current Bun pin")
    original_agents = agent_rows(root)

    with tempfile.TemporaryDirectory(prefix="dotfiles-version-candidate-") as temporary:
        stage = Path(temporary)
        shutil.copytree(root / "deployment", stage / "deployment",
                        ignore=shutil.ignore_patterns("agent-payload"))
        staged_deployment = stage / "deployment"
        _rewrite_tsv_pins(staged_deployment / "common-tools.tsv", proposal.get("common", {}), 1, "common")
        _rewrite_bundle_pins(staged_deployment / "bundle-tools.tsv", proposal.get("bundles", {}))

        manager_constants = {"pixi": ("PIXI_VERSION", "common.sh"),
                             "rustup": ("RUSTUP_VERSION", "common.sh"),
                             "chezmoi": ("CHEZMOI_VERSION", "managers.sh")}
        for manager, version in proposal.get("managers", {}).items():
            constant, filename = manager_constants[manager]
            _set_constant(staged_deployment / filename, constant, version)

        assets_path = staged_deployment / "windows-assets.json"
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
        asset_map = {item["name"]: item for item in assets}
        for name, update in proposal.get("windowsAssets", {}).items():
            asset_map[name].update(update)
        assets_path.write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8")

        changed_agents: set[str] = set()
        for name, version in proposal.get("agents", {}).items():
            if name not in original_agents:
                raise VersionError(f"unknown agent in proposal: {name}")
            package = original_agents[name]["package"]
            package_path = staged_deployment / "agents" / name / "package.json"
            package_json = json.loads(package_path.read_text(encoding="utf-8"))
            package_json["dependencies"][package] = version
            package_path.write_text(json.dumps(package_json, indent=2) + "\n", encoding="utf-8")
            catalog_path = staged_deployment / "agents/catalog.tsv"
            catalog_lines = catalog_path.read_text(encoding="utf-8").splitlines(keepends=True)
            updated_lines = []
            seen = False
            for line in catalog_lines:
                fields = line.rstrip("\r\n").split("|")
                if fields and fields[0] == name:
                    if seen:
                        raise VersionError(f"duplicate agent catalog entry: {name}")
                    fields[2] = version
                    ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                    line = "|".join(fields) + ending
                    seen = True
                updated_lines.append(line)
            if not seen:
                raise VersionError(f"missing agent catalog entry: {name}")
            catalog_path.write_text("".join(updated_lines), encoding="utf-8")
            changed_agents.add(name)

        # Validate the release metadata's Node engine before generating locks.
        candidate_node = common_versions(stage).get("nodejs")
        if candidate_node is None:
            raise VersionError("candidate common catalog is missing Node")
        for name in sorted(changed_agents):
            package = original_agents[name]["package"]
            version = proposal["agents"][name]
            metadata = npm_metadata(package, version)
            validate_node_engine(metadata, candidate_node, name, version)

        _regenerate_bun_locks(stage, changed_agents, bun, current_bun_pin)
        check(stage)

        changed = []
        for candidate in sorted((stage / "deployment").rglob("*")):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(stage)
            destination = root / relative
            if not destination.is_file() or candidate.read_bytes() != destination.read_bytes():
                changed.append(relative)
        for relative in changed:
            source = stage / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_file = tempfile.mkstemp(prefix=".dotfiles-version-", dir=destination.parent)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(source.read_bytes())
                os.chmod(temporary_file, source.stat().st_mode & 0o777)
                os.replace(temporary_file, destination)
            finally:
                if os.path.exists(temporary_file):
                    os.unlink(temporary_file)
        return changed


def verify_bun_locks(root: Path, bun: Path) -> None:
    current_bun_pin = common_versions(root).get("bun")
    if not bun.is_absolute() or not bun.is_file():
        raise VersionError("--bun must point to an absolute Bun executable")
    try:
        actual = subprocess.run([str(bun), "--version"], check=True, capture_output=True,
                                text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise VersionError(f"cannot run Bun from --bun: {type(error).__name__}") from error
    if actual != current_bun_pin:
        raise VersionError(f"verification requires Bun {current_bun_pin}; got {actual}")
    with tempfile.TemporaryDirectory(prefix="dotfiles-bun-verify-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir()
        environment = _isolated_env(home, bun)
        for agent in sorted(agent_rows(root)):
            project = Path(temporary) / "projects" / agent
            project.mkdir(parents=True)
            source = root / "deployment/agents" / agent
            shutil.copy2(source / "package.json", project / "package.json")
            shutil.copy2(source / "bun.lock", project / "bun.lock")
            result = subprocess.run([str(bun), "install", "--cwd", str(project),
                                     "--frozen-lockfile", "--dry-run", "--ignore-scripts"],
                                   check=False, env=environment, capture_output=True, text=True, timeout=900)
            if result.returncode:
                detail = tool_diagnostic(result)
                raise VersionError(f"frozen Bun lock verification failed for {agent} (exit {result.returncode}): {detail}")


def verify_agent_engines(root: Path) -> None:
    node_pin = common_versions(root)["nodejs"]
    for name, agent in sorted(agent_rows(root).items()):
        metadata = npm_metadata(agent["package"], agent["version"])
        validate_node_engine(metadata, node_pin, name, agent["version"])


def run_schema_tests(root: Path) -> None:
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("DOTFILES_", "XDG_", "BUN_", "PIXI_", "NPM_", "ATUIN_",
                                          "CARGO_", "RUSTUP_", "UV_", "PIP_", "KIMI_", "PI_",
                                          "OPENCODE_", "CODEX_", "CLAUDE_"))
                   and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                   "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN", "NODE_OPTIONS", "ENV", "BASH_ENV")}
    with tempfile.TemporaryDirectory(prefix="dotfiles-version-schema-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir()
        environment.update(HOME=str(home), PATH="/usr/bin:/bin", CI="1")
        for pattern in ("test_agents.py", "test_codegraph.py", "test_windows_deployment.py"):
            command = [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-p", pattern]
            result = subprocess.run(command, check=False, cwd=root, env=environment,
                                    capture_output=True, text=True, timeout=900)
            if result.returncode:
                sys.stderr.write(result.stdout + result.stderr)
                raise VersionError(f"version-dependent integration checks failed for {pattern}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "refresh", "verify"))
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--proposal", type=Path, help="reviewed JSON pin proposal (refresh only)")
    parser.add_argument("--bun", type=Path, help="absolute path to the currently pinned Bun binary")
    parser.add_argument("--pixi", type=Path, help="absolute path to the currently pinned Pixi binary")
    parser.add_argument("--resolve", action="store_true", help="also resolve all common and supported bundle targets")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    try:
        if arguments.command == "check":
            counts = check(root)
            print("version catalog is internally consistent")
            labels = (
                ("commonEnvironments", "common environments"),
                ("commonPins", "distinct common package pins"),
                ("bundleToolRows", "bundle-tool rows"),
                ("bundlePins", "distinct bundle package pins"),
                ("agents", "agents"),
                ("windowsAssets", "Windows exceptions"),
            )
            print("; ".join(f"{counts[key]} {label}" for key, label in labels))
            print("Pixi global packages use exact direct pins; Pixi global has no committed transitive lock.")
        elif arguments.command == "refresh":
            if not arguments.proposal or not arguments.bun:
                raise VersionError("refresh requires --proposal FILE and --bun /absolute/path/to/currently-pinned-bun")
            changed = refresh(root, arguments.proposal, arguments.bun.resolve())
            print(f"refreshed {len(changed)} files; review with git diff")
            for path in changed:
                print(path.as_posix())
            print("Run deployment/update_versions.py verify before applying this version set.")
        else:
            check(root)
            if not arguments.bun:
                raise VersionError("verify requires --bun /absolute/path/to/pinned-bun")
            verify_agent_engines(root)
            verify_bun_locks(root, arguments.bun.resolve())
            run_schema_tests(root)
            print("Bun frozen-lock and version-dependent configuration checks passed.")
            print("Native client execution and Windows assets still require their native runners.")
            if arguments.resolve:
                if not arguments.pixi:
                    raise VersionError("--resolve also requires --pixi /absolute/path/to/pinned-pixi")
                environment = {key: value for key, value in os.environ.items()
                               if not key.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "UV_", "NPM_"))}
                environment.update(DOTFILES_TEST_PACKAGE_RESOLUTION="1",
                                   DOTFILES_TEST_PIXI=str(arguments.pixi.resolve()))
                command = [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"),
                           "-p", "test_package_resolution.py"]
                result = subprocess.run(command, check=False, cwd=root, env=environment, text=True)
                if result.returncode:
                    raise VersionError("common and supported bundle target resolution failed")
                print("All supported common and declared bundle package targets resolved.")
    except VersionError as error:
        print(f"dotfiles: version update: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
