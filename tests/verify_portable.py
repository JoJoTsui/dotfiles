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
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

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
AGENTS = ("kimi", "pi", "opencode", "claude", "codex")
COMMON_TOOLS = {
    "pixi", "uv", "uvx", "bun", "bunx", "node", "nu", "rtk", "atuin",
    "zoxide", "tspin", "less", "python", "pip", "codegraph",
}
NATIVE_WORKFLOWS = {
    "macOS": ".github/workflows/native-macos.yml (Intel and Apple silicon; both roles)",
    "WSL2 x86-64": ".github/workflows/native-wsl.yml (Windows 2025; both roles)",
    "WSL2 ARM64": "opt-in self-hosted Windows ARM64 WSL2 runner; pending until available",
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
    if network:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"):
            if os.environ.get(name):
                environment[name] = os.environ[name]
    return environment


def read_rows(path: Path) -> list[list[str]]:
    return [line.split("|") for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")]


def invoke(command: list[str], *, environment: dict[str, str], timeout: int = 1800,
           cwd: Path = SOURCE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                          text=True, timeout=timeout, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def matrix_plan(root: Path, platform: str, arch: str, role: str,
                selection: tuple[str, ...] = ()) -> dict[str, Any]:
    index = len(list(root.glob("case-*")))
    case = root / f"case-{index:03d}"
    home = case / "target-home"
    environment = clean_environment(case / "control")
    command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
               "--home", str(home), "--platform", platform, "--arch", arch,
               "--role", role, *selection, "--plan"]
    result = invoke(command, environment=environment, timeout=60)
    if result.returncode:
        raise VerificationError(
            f"plan failed for {platform}-{arch}-{role} {selection}:\n{result.stderr[-5000:]}"
        )
    try:
        plan = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError(f"invalid plan JSON for {platform}-{arch}-{role}: {error}") from error
    require(not home.exists(), f"plan created target home {home}")
    require(plan.get("platform") == platform and plan.get("arch") == arch and plan.get("role") == role,
            f"plan selected the wrong target for {platform}-{arch}-{role}")
    require(plan.get("profile") == f"{platform}-{role}", f"profile preset mismatch for {platform}-{role}")
    require(plan.get("home") == str(home), "plan target home does not match the isolated path")
    require(plan.get("settings", {}).get("mode") == "copy", "deployment must use copy mode")
    settings = plan.get("settings", {})
    require(settings.get("primaryShell") == "nu", "Nushell is not the preferred managed shell")
    require(not settings.get("systemChanges") and not settings.get("loginShellChanges"),
            "ordinary deployment plan includes a system or account login-shell change")
    roots = plan.get("roots", {})
    for key, relative in (("config", ".config"), ("data", ".local/share"), ("state", ".local/state"),
                          ("cache", ".cache"), ("pixi", ".pixi"), ("bun", ".bun")):
        require(roots.get(key) == str(home / relative), f"{key} state escapes the isolated target home")

    exposed_tools = set(plan.get("tools", ()))
    require(COMMON_TOOLS <= exposed_tools,
            f"common defaults are missing on {platform}-{arch}: {sorted(COMMON_TOOLS - exposed_tools)}")
    if platform == "windows":
        require("zsh" not in exposed_tools, "native Windows must not claim a managed Zsh")
    else:
        require({"bash", "zsh"} <= exposed_tools, f"Unix shell trio is incomplete on {platform}-{arch}")

    selected_agents = list(plan.get("agents", ()))
    packages = {entry["name"]: entry for entry in plan.get("agentPackages", ())}
    expected_agent_names = set(selected_agents) | {"codegraph"}
    require(set(packages) == expected_agent_names,
            f"agent packages do not match selection on {platform}-{arch}-{role}: {sorted(packages)}")
    require(set(AGENTS) <= set(selected_agents) if not selection else True,
            f"default agent selection is incomplete on {platform}-{arch}-{role}")
    require(all(item.get("manager") == "bun" for item in packages.values()),
            "an agent or CodeGraph package is not assigned to Bun")
    require(not plan.get("bundles"), "optional bundles must be absent from the default plan")
    return plan


def verify_local_matrix(root: Path) -> dict[str, int]:
    cells = 0
    plans = 0
    bundle_outcomes = 0
    declarations = {
        bundle: set(supported.split(","))
        for bundle, supported, _prerequisites in read_rows(SOURCE / "deployment/bundles.tsv")
    }
    for platform, arch in MATRIX:
        for role in ROLES:
            base = matrix_plan(root, platform, arch, role)
            cells += 1
            plans += 1
            require(base["agents"] == list(AGENTS), f"default agents changed on {platform}-{arch}-{role}")
            none = matrix_plan(root, platform, arch, role, ("--agents", "none"))
            require(none["agents"] == [] and {item["name"] for item in none["agentPackages"]} == {"codegraph"},
                    f"--agents none did not retain only CodeGraph on {platform}-{arch}-{role}")
            plans += 1
            selected = matrix_plan(root, platform, arch, role, ("--agents", "codex,kimi"))
            require(selected["agents"] == ["kimi", "codex"],
                    f"named agent selection changed on {platform}-{arch}-{role}")
            plans += 1
            pair = f"{platform}-{arch}"
            for bundle, supported_targets in declarations.items():
                case = root / f"case-{len(list(root.glob('case-*'))):03d}"
                home = case / "target-home"
                environment = clean_environment(case / "control")
                command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                           "--home", str(home), "--platform", platform, "--arch", arch,
                           "--role", role, "--bundles", bundle, "--plan"]
                result = invoke(command, environment=environment, timeout=60)
                supported = pair in supported_targets
                if supported:
                    if result.returncode:
                        raise VerificationError(
                            f"declared {bundle} plan failed for {platform}-{arch}-{role}: {result.stderr[-5000:]}"
                        )
                    selected_plan = json.loads(result.stdout)
                    require(selected_plan.get("bundles") == [bundle],
                            f"supported {bundle} bundle missing from {platform}-{arch}-{role} plan")
                    require(bool(selected_plan.get("bundlePackages")),
                            f"supported {bundle} bundle has no declared packages on {platform}-{arch}")
                    require(not home.exists(), f"bundle plan created target home {home}")
                else:
                    require(result.returncode != 0, f"unsupported {bundle} bundle unexpectedly passed for {platform}-{arch}")
                    require("unsupported bundle" in result.stderr,
                            f"unsupported {bundle} rejection was not explicit for {platform}-{arch}: {result.stderr}")
                    require(not home.exists(), f"rejected bundle plan created target home {home}")
                plans += 1
                bundle_outcomes += 1
    return {"matrixCells": cells, "plans": plans, "bundleOutcomes": bundle_outcomes}


def run_suite(label: str, *, pattern: str | None = None, environment: dict[str, str],
              report: dict[str, Any], timeout: int = 2400) -> None:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    if pattern:
        command.extend(("-p", pattern))
    result = invoke(command, environment=environment, timeout=timeout)
    output = result.stdout + result.stderr
    print(output, end="" if output.endswith("\n") else "\n")
    report.setdefault("commands", []).append({"name": label, "exitCode": result.returncode})
    require(result.returncode == 0, f"{label} failed (exit {result.returncode})")


def verify_local(report: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory(prefix="dotfiles-verify-local-") as temporary:
        root = Path(temporary)
        environment = clean_environment(root / "control")
        matrix = verify_local_matrix(root / "matrix")
        report["local"] = {"status": "passed", **matrix}
        print(f"local matrix: passed {matrix['matrixCells']} cells, {matrix['plans']} read-only plans, "
              f"{matrix['bundleOutcomes']} declared bundle outcomes")
        update = invoke([sys.executable, "deployment/update_versions.py", "check"], environment=environment)
        print(update.stdout + update.stderr, end="" if (update.stdout + update.stderr).endswith("\n") else "\n")
        require(update.returncode == 0, "version catalog consistency check failed")
        report["local"]["versionCatalog"] = "passed"
        run_suite("deterministic unittest suite", environment=environment, report=report)
        report["local"]["testSuite"] = "passed"
    report["native"] = {
        "status": "pending native CI",
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
        run_suite("all five Bun-managed agent installations and harmless diagnostics",
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
    parser.add_argument("--report", type=Path, help="write a JSON summary to this path")
    arguments = parser.parse_args()
    report: dict[str, Any] = {"schemaVersion": 1, "source": str(SOURCE), "layers": {}}
    try:
        verify_local(report)
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
