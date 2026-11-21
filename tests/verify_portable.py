"""Run isolated local deployment checks and optionally network acceptance.

The default pass uses plan mode for every supported profile/architecture/role
and runs the deterministic suite. It gives each plan a fresh temporary target
home and a scrubbed environment. ``--network`` additionally resolves all
declared Pixi targets, installs the Linux common toolchain in a temporary home,
and executes shell/history diagnostics against it. Native macOS, Windows, and
WSL execution remains owned by the platform workflows and is reported pending
here until those runners complete.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import native_report

SOURCE = Path(__file__).resolve().parents[1]
MATRIX = (
    ("linux", "x86_64"),
    ("linux", "aarch64"),
    ("wsl", "x86_64"),
    ("wsl", "aarch64"),
    ("macos", "x86_64"),
    ("macos", "aarch64"),
    ("windows", "x86_64"),
)
ROLES = ("workstation", "remote-compute")
AGENTS = ("kimi", "pi", "opencode", "claude", "codex", "minimax", "qoder", "dsh", "dsh-tui")
COMMON_TOOLS = {
    "pixi", "uv", "uvx", "bun", "bunx", "node", "nu", "rtk", "atuin",
    "zoxide", "tspin", "less", "python", "pip", "codegraph",
}
# Every platform has its own public deployment adapter. The Unix adapter is
# bootstrap.sh; the native Windows adapter is bootstrap.ps1. A platform plan
# is read from the adapter that owns it, so one adapter cannot stand in for
# another.
ADAPTERS = {"linux": "bash", "wsl": "bash", "macos": "bash", "windows": "powershell"}
BASH_STEPS = ("install-managers", "apply-source", "install-common", "install-agents", "prepare-shell")
POWERSHELL_STEPS = ("install-managers", "apply-source", "install-common", "install-agents",
                    "install-magpie-cli", "prepare-shell")
# The deployment steps only one adapter owns. A plan that carries another
# adapter's step came from the wrong interface.
BASH_ONLY_STEPS = ("apply-source.skills", "apply-source.agent-payload", "apply-source.skills-prune",
                   "apply-source.client-settings", "apply-source.macos-discovery",
                   "install-installer-tools", "magpie-apply")
POWERSHELL_ONLY_STEPS = ("install-magpie-cli",)
NATIVE_WORKFLOWS = {
    "macOS": ".github/workflows/native-macos.yml (Intel and Apple silicon; both roles)",
    "WSL2 x86-64": ".github/workflows/native-wsl.yml (Windows 2025; both roles)",
    "WSL2 ARM64": "self-hosted Windows ARM64 WSL2 runner; none configured, so not scheduled",
    "Windows x86-64": ".github/workflows/native-windows.yml (Windows 2025; both roles)",
}


class VerificationError(RuntimeError):
    pass


def clean_environment(root: Path, *, network: bool = False) -> dict[str, str]:
    """Build a controlled environment without inherited shell/tool state."""
    root.mkdir(parents=True, exist_ok=True)
    environment = {
        "HOME": str(root / "home"),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(root / "tmp"),
        "TMP": str(root / "tmp"),
        "TEMP": str(root / "tmp"),
        "LANG": "C.UTF-8",
        "TERM": "xterm-256color",
        "CI": "1",
    }
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    # Explicit borrowed executables are read-only prerequisites, not inherited
    # host state. Keep their paths while all runtime writes use disposable roots.
    for name in ("DOTFILES_TEST_CHEZMOI", "DOTFILES_TEST_NU", "DOTFILES_TEST_MAMBA",
                 "DOTFILES_TEST_POWERSHELL", "DOTFILES_TEST_PWSH", "DOTFILES_TEST_TOOL_HOME"):
        if os.environ.get(name):
            environment[name] = str(Path(os.environ[name]).resolve())
    if network:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"):
            if os.environ.get(name):
                environment[name] = os.environ[name]
    return environment


def read_rows(path: Path) -> list[list[str]]:
    return [line.split("|") for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")]


def checkout_identity() -> dict[str, Any]:
    """The checkout this verification ran against."""
    identity = native_report.checkout_identity_or_unknown(SOURCE)
    return {"commit": identity["commit"], "tree": identity["tree"],
            "working_tree_dirty": identity["working_tree_dirty"]}


def invoke(command: list[str], *, environment: dict[str, str], timeout: int = 1800,
           cwd: Path = SOURCE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                          text=True, timeout=timeout, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def powershell_executable():
    """The PowerShell runtime that renders the native Windows plan.

    The native Windows adapter is a separate public interface. The portable
    check calls it directly instead of reading a Windows plan through the
    Unix adapter, and it records a skipped scenario when the host provides no
    PowerShell runtime.
    """
    for variable in ("DOTFILES_TEST_POWERSHELL", "DOTFILES_TEST_PWSH"):
        value = os.environ.get(variable)
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    found = shutil.which("pwsh") or shutil.which("powershell")
    return str(Path(found).resolve()) if found else None


def case_directory(root: Path) -> Path:
    """A fresh isolated case directory for one plan."""
    return root / f"case-{len(list(root.glob('case-*'))):03d}"


def parse_plan(result: subprocess.CompletedProcess[str], platform: str, arch: str,
               role: str) -> dict[str, Any]:
    if result.returncode:
        raise VerificationError(
            f"plan failed for {platform}-{arch}-{role}:\n{result.stderr[-5000:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError(f"invalid plan JSON for {platform}-{arch}-{role}: {error}") from error


def bash_plan(case: Path, platform: str, arch: str, role: str,
              selection: tuple[tuple[str, str], ...] = ()) -> dict[str, Any]:
    """Render a plan through the public Unix adapter."""
    home = case / "target-home"
    environment = clean_environment(case / "control")
    command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
               "--home", str(home), "--platform", platform, "--arch", arch, "--role", role]
    for option, value in selection:
        command += [option, value]
    command.append("--plan")
    plan = parse_plan(invoke(command, environment=environment, timeout=60), platform, arch, role)
    require(not home.exists(), f"plan created target home {home}")
    require(plan.get("home") == str(home), "plan target home does not match the isolated path")
    return plan


def powershell_plan(case: Path, platform: str, arch: str, role: str,
                    selection: tuple[tuple[str, str], ...] = ()) -> dict[str, Any]:
    """Render a plan through the public native Windows adapter."""
    executable = powershell_executable()
    require(executable is not None, "the native Windows adapter needs a PowerShell runtime")
    home = case / "target-home"
    environment = clean_environment(case / "control")
    command = [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
               str(SOURCE / "bootstrap.ps1"), "-Plan", "-Source", str(SOURCE),
               "-TargetHome", str(home), "-Platform", platform, "-Role", role, "-Arch", arch]
    for option, value in selection:
        command += [option, value]
    plan = parse_plan(invoke(command, environment=environment, timeout=120), platform, arch, role)
    require(not home.exists(), f"plan created target home {home}")
    require(plan.get("home") == str(home), "plan target home does not match the isolated path")
    return plan


def public_plan(root: Path, platform: str, arch: str, role: str,
                selection: tuple[tuple[str, str], ...] = ()) -> dict[str, Any]:
    """The plan the platform's own public adapter produces."""
    case = case_directory(root)
    if ADAPTERS[platform] == "powershell":
        return powershell_plan(case, platform, arch, role, selection)
    return bash_plan(case, platform, arch, role, selection)


def require_shared_plan(plan: dict[str, Any], platform: str, arch: str, role: str) -> None:
    """The plan fields every adapter agrees on."""
    require(plan.get("platform") == platform and plan.get("arch") == arch and plan.get("role") == role,
            f"plan selected the wrong target for {platform}-{arch}-{role}")
    require(plan.get("profile") == f"{platform}-{role}", f"profile preset mismatch for {platform}-{role}")
    require(plan.get("settings", {}).get("mode") == "copy", "deployment must use copy mode")
    settings = plan.get("settings", {})
    require(settings.get("primaryShell") == "nu", "Nushell is not the preferred managed shell")
    require(not settings.get("systemChanges") and not settings.get("loginShellChanges"),
            "ordinary deployment plan includes a system or account login-shell change")
    home = plan.get("home", "")
    roots = plan.get("roots", {})
    for key, relative in (("config", ".config"), ("data", ".local/share"), ("state", ".local/state"),
                          ("cache", ".cache"), ("pixi", ".pixi"), ("bun", ".bun")):
        require(roots.get(key) == str(Path(home) / relative),
                f"{key} state escapes the isolated target home")

    selected_agents = list(plan.get("agents", ()))
    packages = {entry["name"]: entry for entry in plan.get("agentPackages", ())}
    expected_agent_names = set(selected_agents) | {"codegraph"}
    require(set(packages) == expected_agent_names,
            f"agent packages do not match selection on {platform}-{arch}-{role}: {sorted(packages)}")
    require(all(item.get("manager") in ("bun", "native", "homebrew") for item in packages.values()),
            "an agent or CodeGraph package has an unknown installation manager")
    require(packages["codegraph"]["manager"] == "bun", "CodeGraph is not assigned to Bun")
    # Every entry describes its own provider: an installer-owned entry names
    # the Homebrew package and carries no deployment-owned lock.
    for name, item in packages.items():
        if item.get("manager") != "homebrew":
            continue
        require(item.get("package") and item.get("packageKind") in ("formula", "cask"),
                f"a Homebrew agent entry does not name its package: {name}")
        require("lock" not in item and "minimumNode" not in item,
                f"a Homebrew agent entry carries a deployment-owned project field: {name}")
        require(item.get("fallback", {}).get("provider") in ("bun", "native"),
                f"a Homebrew agent entry does not name its fallback: {name}")
    if "qoder" in selected_agents:
        require(packages["qoder"]["manager"] == "native", "Qoder is not assigned to its native installer")
    else:
        require("qoder" not in packages, "Qoder leaked into an unselected plan")


def require_platform_tools(plan: dict[str, Any], platform: str) -> None:
    """The tool selection the platform's own adapter makes."""
    exposed = set(plan.get("tools", ()))
    require(COMMON_TOOLS <= exposed,
            f"common defaults are missing on {platform}: {sorted(COMMON_TOOLS - exposed)}")
    if platform == "windows":
        require("zsh" not in exposed, "native Windows must not claim a managed Zsh")
        require({"bash", "sh"} <= exposed, "native Windows must expose its Git Bash runtime")
    elif platform == "macos":
        require("zsh" in exposed, "macOS must expose the managed Zsh")
        require("bash" not in exposed, "macOS must not claim a managed Bash")
    else:
        require({"bash", "zsh"} <= exposed, f"Unix shell trio is incomplete on {platform}")


def require_platform_steps(plan: dict[str, Any], platform: str) -> None:
    """The deployment steps the platform's own adapter runs."""
    steps = list(plan.get("steps", ()))
    expected = BASH_STEPS if ADAPTERS[platform] == "bash" else POWERSHELL_STEPS
    missing = [step for step in expected if step not in steps]
    require(not missing, f"the {platform} plan is missing deployment steps: {missing}")
    foreign = BASH_ONLY_STEPS if ADAPTERS[platform] == "powershell" else POWERSHELL_ONLY_STEPS
    borrowed = [step for step in foreign if step in steps]
    require(not borrowed, f"the {platform} plan carries another adapter's steps: {borrowed}")


def shared_plan_differences(first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    """The shared plan fields two public adapters disagree on.

    The comparison covers the fields both adapters own. The tool list, the
    deployment steps, the manager pins, and the platform-only metadata stay
    with the adapter that owns them.
    """
    differences = []
    for field in ("platform", "role", "arch", "profile", "mirror"):
        if first.get(field) != second.get(field):
            differences.append(f"{field}: {first.get(field)!r} != {second.get(field)!r}")
    for field in ("source", "home"):
        left = os.path.realpath(first.get(field, "") or ".")
        right = os.path.realpath(second.get(field, "") or ".")
        if left != right:
            differences.append(f"{field}: {first.get(field)!r} != {second.get(field)!r}")
    for field in ("agents", "bundles"):
        if sorted(first.get(field, ())) != sorted(second.get(field, ())):
            differences.append(f"{field}: {first.get(field)} != {second.get(field)}")
    for field, key in (("packages", "environment"), ("bundlePackages", "environment"),
                       ("agentPackages", "name")):
        left = {entry[key]: entry for entry in first.get(field, ())}
        right = {entry[key]: entry for entry in second.get(field, ())}
        for name in sorted(set(left) | set(right)):
            if left.get(name) != right.get(name):
                differences.append(f"{field}.{name}: {left.get(name)} != {right.get(name)}")
    for field in ("mode", "primaryShell", "systemChanges", "loginShellChanges"):
        left = first.get("settings", {}).get(field)
        right = second.get("settings", {}).get(field)
        if left != right:
            differences.append(f"settings.{field}: {left!r} != {right!r}")
    for field in ("config", "data", "state", "cache", "pixi", "bun"):
        left = os.path.realpath(first.get("roots", {}).get(field, "") or ".")
        right = os.path.realpath(second.get("roots", {}).get(field, "") or ".")
        if left != right:
            differences.append(f"roots.{field}: {left!r} != {right!r}")
    return differences


def verify_local_matrix(root: Path) -> dict[str, Any]:
    cells = 0
    plans = 0
    bundle_outcomes = 0
    scenarios: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    declarations = {
        bundle: set(supported.split(","))
        for bundle, supported, _prerequisites in read_rows(SOURCE / "deployment/bundles.tsv")
    }
    for platform, arch in MATRIX:
        for role in ROLES:
            if ADAPTERS[platform] == "powershell" and not powershell_executable():
                # The native Windows adapter needs a PowerShell runtime. Its
                # absence leaves the cell unrun, not passed.
                skipped.append({
                    "scenario": f"{platform}-{arch}-{role} public plan",
                    "reason": "the native Windows adapter needs a PowerShell runtime, which this host does not provide",
                })
                continue
            base = public_plan(root, platform, arch, role)
            require_shared_plan(base, platform, arch, role)
            require_platform_tools(base, platform)
            require_platform_steps(base, platform)
            cells += 1
            plans += 1
            require(base["agents"] == list(AGENTS), f"default agents changed on {platform}-{arch}-{role}")
            require(not base.get("bundles"), "optional bundles must be absent from the default plan")
            none = public_plan(root, platform, arch, role, (("--agents", "none"),))
            require_shared_plan(none, platform, arch, role)
            require(none["agents"] == [] and {item["name"] for item in none["agentPackages"]} == {"codegraph"},
                    f"--agents none did not retain only CodeGraph on {platform}-{arch}-{role}")
            plans += 1
            selected = public_plan(root, platform, arch, role, (("--agents", "codex,kimi"),))
            require_shared_plan(selected, platform, arch, role)
            require(selected["agents"] == ["kimi", "codex"],
                    f"named agent selection changed on {platform}-{arch}-{role}")
            plans += 1
            pair = f"{platform}-{arch}"
            for bundle, supported_targets in declarations.items():
                supported = pair in supported_targets
                option = ("--bundles", bundle) if ADAPTERS[platform] == "bash" else ("-Bundles", bundle)
                if supported:
                    selected_plan = public_plan(root, platform, arch, role, (option,))
                    require_shared_plan(selected_plan, platform, arch, role)
                    require(selected_plan.get("bundles") == [bundle],
                            f"supported {bundle} bundle missing from {platform}-{arch}-{role} plan")
                    require(bool(selected_plan.get("bundlePackages")),
                            f"supported {bundle} bundle has no declared packages on {platform}-{arch}")
                else:
                    case = case_directory(root)
                    home = case / "target-home"
                    environment = clean_environment(case / "control")
                    if ADAPTERS[platform] == "bash":
                        command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                   "--home", str(home), "--platform", platform, "--arch", arch,
                                   "--role", role, "--bundles", bundle, "--plan"]
                    else:
                        command = [powershell_executable(), "-NoLogo", "-NoProfile", "-NonInteractive",
                                   "-File", str(SOURCE / "bootstrap.ps1"), "-Plan", "-Source", str(SOURCE),
                                   "-TargetHome", str(home), "-Platform", platform, "-Role", role,
                                   "-Arch", arch, "-Bundles", bundle]
                    result = invoke(command, environment=environment, timeout=120)
                    require(result.returncode != 0,
                            f"unsupported {bundle} bundle unexpectedly passed for {platform}-{arch}")
                    require("unsupported bundle" in result.stderr,
                            f"unsupported {bundle} rejection was not explicit for {platform}-{arch}: {result.stderr}")
                    require(not home.exists(), f"rejected bundle plan created target home {home}")
                plans += 1
                bundle_outcomes += 1
            scenarios.append({"name": f"{platform}-{arch}-{role} public plan", "outcome": "passed"})
    scenarios.extend({"name": entry["scenario"], "outcome": "skipped", "reason": entry["reason"]}
                     for entry in skipped)
    return {"matrixCells": cells, "plans": plans, "bundleOutcomes": bundle_outcomes,
            "scenarios": scenarios, "skipped": skipped}


def compare_public_adapters(root: Path) -> dict[str, Any]:
    """Compare the shared plan fields of the two public adapters.

    Both adapters describe the same deployment target, so the fields they
    share have to agree. The tool list, the deployment steps, and the
    platform-only metadata stay with the adapter that owns them and are
    checked in that adapter's own scenario.
    """
    if not powershell_executable():
        return {"name": "public adapter comparison", "outcome": "skipped",
                "reason": "the native Windows adapter needs a PowerShell runtime, which this host does not provide"}
    case = case_directory(root)
    # Both adapters describe the same target home, so the comparison covers
    # the plan itself and not two different targets.
    unix_plan = bash_plan(case, "windows", "x86_64", "workstation")
    windows_plan = powershell_plan(case, "windows", "x86_64", "workstation")
    differences = shared_plan_differences(unix_plan, windows_plan)
    require(not differences,
            "the public adapters disagree on the shared plan fields: " + "; ".join(differences))
    return {"name": "public adapter comparison", "outcome": "passed",
            "target": "windows-x86_64-workstation", "compared": ["platform", "role", "arch", "profile",
                                                               "mirror", "source", "home", "agents",
                                                               "bundles", "packages", "bundlePackages",
                                                               "agentPackages", "settings", "roots"]}


def run_suite(label: str, *, pattern: str | None = None, environment: dict[str, str],
              report: dict[str, Any], timeout: int = 2400, require_runtime: bool = False) -> None:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    if pattern:
        command.extend(("-p", pattern))
    result = invoke(command, environment=environment, timeout=timeout)
    output = result.stdout + result.stderr
    print(output, end="" if output.endswith("\n") else "\n")
    report.setdefault("commands", []).append({"name": label, "exitCode": result.returncode})
    require(result.returncode == 0, f"{label} failed (exit {result.returncode})")
    if require_runtime:
        required = ('test_portable_config.', 'test_skills.', 'test_nu_completions.', 'test_cli_catalog.')
        require(not any('skipped ' in line and any(module in line for module in required)
                        for line in output.splitlines()), "a required runtime check was skipped")


def verify_local(report: dict[str, Any], *, require_runtime: bool = False) -> None:
    if require_runtime:
        require(sys.version_info >= (3, 11), "required runtime checks need Python 3.11 or newer")
        for variable, command in (("DOTFILES_TEST_CHEZMOI", "chezmoi"), ("DOTFILES_TEST_NU", "nu"),
                                  ("DOTFILES_TEST_MAMBA", "micromamba"), ("DOTFILES_TEST_POWERSHELL", "pwsh")):
            executable = os.environ.get(variable) or shutil.which(command)
            require(bool(executable) and Path(executable).is_file(), f"required prerequisite missing: {variable}")
            os.environ[variable] = str(Path(executable).resolve())
        os.environ["DOTFILES_TEST_PWSH"] = os.environ["DOTFILES_TEST_POWERSHELL"]
    with tempfile.TemporaryDirectory(prefix="dotfiles-verify-local-") as temporary:
        root = Path(temporary)
        environment = clean_environment(root / "control")
        matrix = verify_local_matrix(root / "matrix")
        report["local"] = {"status": "passed", **matrix}
        report["local"]["scenarios"].append(compare_public_adapters(root / "comparison"))
        # A cell that could not run leaves the local layer without full
        # coverage, so acceptance needs every planned scenario to have run.
        report["local"]["acceptance"] = not any(
            scenario["outcome"] != "passed" for scenario in report["local"]["scenarios"])
        print(f"local matrix: passed {matrix['matrixCells']} cells, {matrix['plans']} read-only plans, "
              f"{matrix['bundleOutcomes']} declared bundle outcomes")
        for entry in report["local"]["scenarios"]:
            if entry["outcome"] != "passed":
                print(f"local matrix: {entry['outcome']} {entry['name']}: {entry.get('reason', '')}")
        update = invoke([sys.executable, "deployment/update_versions.py", "check"], environment=environment)
        print(update.stdout + update.stderr, end="" if (update.stdout + update.stderr).endswith("\n") else "\n")
        require(update.returncode == 0, "version catalog consistency check failed")
        report["local"]["versionCatalog"] = "passed"
        skill_pins = invoke([sys.executable, "deployment/update_skills.py", "check"], environment=environment)
        print(skill_pins.stdout + skill_pins.stderr)
        require(skill_pins.returncode == 0, "skill catalog pins are inconsistent")
        report["local"]["skillPins"] = "passed"
        run_suite("deterministic unittest suite", environment=environment, report=report, require_runtime=require_runtime)
        report["local"]["testSuite"] = "passed"
    report["native"] = {
        "status": "pending native CI",
        "acceptance": False,
        "targets": {name: {"status": "pending", "runner": runner}
                    for name, runner in NATIVE_WORKFLOWS.items()},
        "limit": "Foreign plan/render and package resolution do not count as native execution.",
    }
    report["network"] = {
        "status": "not run; invoke with --network",
        "command": "python3 tests/verify_portable.py --network",
    }


def verify_network(report: dict[str, Any]) -> None:
    report["network"] = {
        "status": "running",
        "linuxCommonInstall": "pending",
        "codingAgents": "pending",
        "shellDiagnostics": "pending",
        "syntheticHistory": "pending",
        "targetResolution": "pending",
    }
    with tempfile.TemporaryDirectory(prefix="dotfiles-verify-network-") as temporary:
        root = Path(temporary)
        common_home = root / "linux" / "home"
        environment = clean_environment(root / "control", network=True)
        environment.update(DOTFILES_TEST_INSTALL="1", DOTFILES_TEST_INSTALL_HOME=str(common_home))
        run_suite("isolated Linux common installation and CLI diagnostics",
                  pattern="test_common_install.py", environment=environment, report=report,
                  timeout=3600)
        report["network"]["linuxCommonInstall"] = "passed"

        tool_home = common_home
        chezmoi = tool_home / ".local/bin/chezmoi"
        shell_environment = clean_environment(root / "shell-tests")
        shell_environment.update(DOTFILES_TEST_CHEZMOI=str(chezmoi), DOTFILES_TEST_TOOL_HOME=str(tool_home))
        agent_environment = clean_environment(root / "agent-install", network=True)
        agent_environment.update(
            DOTFILES_TEST_AGENT_INSTALL="1",
            DOTFILES_TEST_CHEZMOI=str(chezmoi),
            DOTFILES_TEST_BUN=str(tool_home / ".pixi/envs/bun/bin/bun"),
            DOTFILES_TEST_NODE=str(tool_home / ".pixi/envs/nodejs/bin/node"),
        )
        run_suite("all selected Bun-managed agents, native Qoder, and harmless diagnostics",
                  pattern="test_agents.py", environment=agent_environment,
                  report=report, timeout=3600)
        report["network"]["codingAgents"] = "passed"
        run_suite("Linux Nushell/Bash/Zsh execution with scrubbed inherited paths",
                  pattern="test_shell_behavior.py", environment=shell_environment,
                  report=report, timeout=1200)
        report["network"]["shellDiagnostics"] = "passed"
        run_suite("synthetic shared-history behavior in isolated shells",
                  pattern="test_history_behavior.py", environment=shell_environment,
                  report=report, timeout=1200)
        report["network"]["syntheticHistory"] = "passed"
        import_environment = dict(shell_environment)
        import_environment.update(
            DOTFILES_TEST_ATUIN=str(tool_home / ".pixi/envs/atuin/bin/atuin"),
            DOTFILES_TEST_PYTHON=str(tool_home / ".pixi/envs/python/bin/python"),
        )
        run_suite("synthetic portable-history importer",
                  pattern="test_portable_history_import.py", environment=import_environment,
                  report=report, timeout=1200)

        pixi = tool_home / ".pixi/bin/pixi"
        resolution_environment = clean_environment(root / "resolution", network=True)
        resolution_environment.update(DOTFILES_TEST_PACKAGE_RESOLUTION="1", DOTFILES_TEST_PIXI=str(pixi))
        run_suite("all common and declared bundle target resolutions",
                  pattern="test_package_resolution.py", environment=resolution_environment,
                  report=report, timeout=3600)
        report["network"]["targetResolution"] = "passed"
        report["network"]["status"] = "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", action="store_true",
                        help="also run isolated Linux installs, shell/history diagnostics, and all-target package resolution")
    parser.add_argument("--require-runtime", action="store_true",
                        help="require Python 3.11+, Chezmoi, Nu, Micromamba and PowerShell; fail if core runtime checks skip")
    parser.add_argument("--report", type=Path, help="write a JSON summary to this path")
    arguments = parser.parse_args()
    report: dict[str, Any] = {"schemaVersion": 1, "source": str(SOURCE),
                              "checkout": checkout_identity(), "layers": {}}
    try:
        verify_local(report, require_runtime=arguments.require_runtime)
        report["layers"]["local"] = "passed"
        if arguments.network:
            verify_network(report)
            report["layers"]["network"] = "passed"
        if arguments.report:
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not arguments.network:
            print("network: pending (not requested); native macOS/Windows/WSL: pending CI")
        else:
            print("network: passed; native macOS/Windows/WSL: pending CI")
        return 0
    except (VerificationError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        report["status"] = "failed"
        report["failure"] = str(error)
        if report.get("network", {}).get("status") == "running":
            report["network"]["status"] = "failed"
            report["network"]["failure"] = str(error)
        if arguments.report:
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
