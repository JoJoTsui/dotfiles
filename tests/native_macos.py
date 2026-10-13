"""Native macOS installation and observable behavior, confined to temporary homes.

Invoke directly on the target runtime. The report contains check results and
runtime metadata; homes, credentials, history, and client configuration are
never artifacts. Foreign execution fails with an unavailable report.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
MIRROR = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(arguments, *, env, cwd, timeout=60, allow_failure=False):
    result = subprocess.run(arguments, env=env, cwd=cwd, capture_output=True,
                            text=True, timeout=timeout)
    if not allow_failure:
        failure = next((line for line in result.stderr.splitlines() if line.startswith("dotfiles: step ")),
                       f"command failed: {Path(arguments[0]).name}")
        require(result.returncode == 0, failure)
    return result


def minimal_environment(home):
    return {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "TERM": "xterm-256color", "LANG": "en_US.UTF-8"}


def managed_environment(home):
    environment = minimal_environment(home)
    environment.update(PATH=f"{home}/.bun/bin:{home}/.local/bin:{home}/.pixi/bin:{home}/.cargo/bin:{environment['PATH']}",
                       XDG_CONFIG_HOME=str(home / ".config"),
                       XDG_DATA_HOME=str(home / ".local/share"),
                       XDG_STATE_HOME=str(home / ".local/state"),
                       XDG_CACHE_HOME=str(home / ".cache"),
                       PIXI_HOME=str(home / ".pixi"),
                       CARGO_HOME=str(home / ".cargo"), RUSTUP_HOME=str(home / ".rustup"),
                       ATUIN_CONFIG_DIR=str(home / ".config/atuin"),
                       ATUIN_DATA_DIR=str(home / ".local/share/atuin"),
                       CODEGRAPH_NO_DOWNLOAD="1", DO_NOT_TRACK="1",
                       CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                       DISABLE_TELEMETRY="1", DISABLE_AUTOUPDATER="1")
    return environment


def managed_snapshot(home):
    snapshot = {}
    for relative in (".config/nushell", ".config/pip", ".config/uv", ".config/opencode",
                     "Library/Application Support/nushell", "Library/Application Support/pip",
                     ".agents/skills", ".claude/skills"):
        for path in (home / relative).rglob("*"):
            if path.is_file():
                snapshot[str(path.relative_to(home))] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Compare owned configs/instructions and preservation sentinels, rather
    # than timestamps in unrelated runtime client logs or session caches.
    for relative in (".env_core", ".claude/settings.json", ".claude.json", ".bash_history",
                     ".codex/config.toml", ".codex/auth.json", ".codex/AGENTS.md",
                     ".kimi-code/config.toml", ".kimi-code/tui.toml", ".kimi-code/mcp.json", ".kimi-code/AGENTS.md",
                     ".pi/agent/settings.json", ".pi/agent/models-store.json", ".pi/agent/AGENTS.md",
                     ".agents/AGENTS.md", ".claude/CLAUDE.md",
                     ".bun/install/global/package.json", ".local/share/atuin/device-sentinel"):
        path = home / relative
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def check_native_discovery(home, role):
    """Ordinary startup has no XDG, Nu config flags, or Python mirror overrides."""
    env = minimal_environment(home)
    native = home / "Library/Application Support/nushell"
    nu = str(home / ".pixi/bin/nu")
    script = ('print ({config_dir: $nu.default-config-dir, editor: $env.EDITOR, '
              'polling: $env.CHOKIDAR_USEPOLLING, paths: $env.PATH, '
              'preference: $env.UV_PYTHON_PREFERENCE, index: $env.UV_DEFAULT_INDEX} | to json --raw)')
    # -e enters REPL startup and executes after user/vendor autoload. In the
    # pinned release -c takes the command path even when combined with -i.
    result = run([nu, "-e", script + "; exit"], env=env, cwd=home)
    values = json.loads(result.stdout)
    require(values["config_dir"] == str(native), "ordinary macOS Nu config discovery")
    require(values["editor"] == "hx", "standalone Nu editor")
    require(values["polling"] == ("1" if role == "remote-compute" else "0"), "standalone Nu role")
    require(values["preference"] == "managed" and values["index"] == MIRROR, "standalone Nu Python defaults")
    require(values["paths"][:4] == [str(home / path) for path in
            (".bun/bin", ".local/bin", ".pixi/bin", ".cargo/bin")], "standalone Nu managed path order")
    require(len(values["paths"]) == len(set(values["paths"])), "standalone Nu idempotent path")
    autoload = run([nu, "-e",
                    'print ({starship: $env.STARSHIP_SHELL?, pixi: (scope commands | where name == "pixi" | length), '
                    'history_hooks: ($env.config.hooks.pre_execution | length), device: $env.DOTFILES_DEVICE_STARTUP?} | to json --raw); exit'],
                   env=env, cwd=home)
    hooks = json.loads(autoload.stdout)
    require(hooks["starship"] == "nu" and hooks["pixi"] == 1, "native Nu prompt and completion discovery")
    require(hooks["history_hooks"] > 0, "native Nu Atuin hook discovery")
    require(hooks["device"] == "preserved", "unrelated native Nu startup preserved")
    require(any(str(native / "autoload") == path for path in json.loads(run(
        [nu, "-e", 'print ($nu.user-autoload-dirs | to json --raw); exit'], env=env, cwd=home).stdout)),
        "native Nu user autoload path")
    pip = str(home / ".pixi/bin/pip")
    mirror = run([pip, "config", "get", "global.index-url"], env=env, cwd=home)
    require(mirror.stdout.strip() == MIRROR, "ordinary native pip TUNA discovery")
    debug = run([pip, "config", "debug"], env=env, cwd=home)
    require(str(home / "Library/Application Support/pip/pip.conf") in debug.stdout,
            "native pip discovery path")
    uv_command = str(home / ".pixi/bin/uv")
    uv_arguments = ["pip", "install", "--dry-run", "--system", "--python",
                    str(home / ".pixi/bin/python"), "--offline", "dotfiles-unavailable==0.0.0"]
    uv_settings = run([uv_command, "--show-settings", *uv_arguments],
                      env=env, cwd=home, allow_failure=True)
    require(uv_settings.returncode == 0 and MIRROR + "/" in uv_settings.stdout + uv_settings.stderr,
            "ordinary uv settings discovery")
    offline = run([uv_command, *uv_arguments], env=env, cwd=home, allow_failure=True)
    require(offline.returncode != 0, "ordinary uv offline dry run")
    # Validate ordinary discovery plus relative imports; --config flags would
    # hide a broken native location and are deliberately absent above.
    for name in ("env.nu", "config.nu", "proxy.nu", "direnv.nu", "micromamba.nu", "zoxide.nu"):
        path = native / name
        require(path.is_file() and not path.is_symlink(), f"native Nu regular file: {name}")
        require(path.read_bytes() == (home / ".config/nushell" / name).read_bytes(), f"canonical Nu copy: {name}")
    for name in ("starship.nu", "pixi-completions.nu", "atuin.nu"):
        require((native / "autoload" / name).read_bytes() ==
                (home / ".local/share/nushell/vendor/autoload" / name).read_bytes(),
                f"canonical startup copy: {name}")


def check_pinned_tools(home, plan, report):
    env = managed_environment(home)
    versions = {}
    tools = {exposed for package in plan["packages"] for exposed in package["exposed"]}
    tools.update(("pixi", "rustup"))
    for command in sorted(tools):
        location = home / (".cargo/bin" if command == "rustup" else ".pixi/bin") / command
        require(location.is_file() and os.access(location, os.X_OK), f"managed exposure: {command}")
        arguments = [str(location), "version" if command == "git-lfs" else "--version"]
        diagnostic = run(arguments, env=env, cwd=home)
        versions[command] = (diagnostic.stdout + diagnostic.stderr).strip().splitlines()[0]
    for package in plan["agentPackages"]:
        commands = [package["name"]] + (["opencode2"] if package["name"] == "opencode" else [])
        for command in commands:
            location = home / ".bun/bin" / command
            require(location.is_file() and not location.is_symlink(), f"owned Bun launcher: {command}")
            require(location.read_bytes() == (home / ".local/bin" / command).read_bytes(), f"owned agent copy: {command}")
            result = run([str(location), "--version"], env=env, cwd=home)
            require(package["version"] in result.stdout + result.stderr, f"pinned agent version: {command}")
            versions[command] = (result.stdout + result.stderr).strip().splitlines()[0]
    report["versions"] = versions
    status = run([str(home / ".local/bin/dotfiles-history"), "status"], env=env, cwd=home)
    require("pending activation" in status.stdout, "history stays pending without account setup")
    require(not (home / ".codegraph").exists() and not (SOURCE / ".codegraph").exists(),
            "installation does not index a repository")
    require(not (home / ".github").exists(), "workflow bookkeeping excluded from target")


def seed_device(home):
    values = {
        ".claude/settings.json": '{"env":{"DEVICE_VALUE":"keep"}}\n',
        ".codex/auth.json": '{"synthetic-only":"untouched"}\n',
        ".bash_history": 'echo existing-device-history\n',
        ".bun/install/global/package.json": '{"dependencies":{"device-extra":"1.0.0"}}\n',
        ".local/share/atuin/device-sentinel": 'unrelated history state\n',
        "Library/Application Support/nushell/autoload/device.nu": '$env.DOTFILES_DEVICE_STARTUP = "preserved"\n',
        ".agents/skills/device-extra/SKILL.md": '---\nname: device-extra\ndescription: Unrelated device skill.\n---\nRetain this device skill.\n',
        ".pixi/manifests/pixi-global.toml": 'version = 1\n[envs.device-extra]\nchannels = ["conda-forge"]\ndependencies = { zoxide = "==0.10.0" }\nexposed = { device-zoxide = "zoxide" }\n',
    }
    for relative, content in values.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return values


def check_preservation(home, originals):
    for relative in (".codex/auth.json", ".bash_history", ".bun/install/global/package.json",
                     ".local/share/atuin/device-sentinel", ".agents/skills/device-extra/SKILL.md",
                     "Library/Application Support/nushell/autoload/device.nu"):
        require((home / relative).read_text() == originals[relative], f"unrelated state preserved: {relative}")
    settings = json.loads((home / ".claude/settings.json").read_text())
    require(settings["env"]["DEVICE_VALUE"] == "keep", "unrelated client settings preserved")
    import tomllib
    registry = tomllib.loads((home / ".pixi/manifests/pixi-global.toml").read_text())
    require(registry["envs"]["device-extra"]["exposed"] == {"device-zoxide": "zoxide"},
            "unrelated Pixi exposure preserved")


def check_portable_suites(home, role, report):
    env = managed_environment(home)
    env.update(TMPDIR=str(home / ".cache/tmp"), DOTFILES_TEST_PLATFORM="macos", DOTFILES_TEST_ROLE=role,
               DOTFILES_TEST_CHEZMOI=str(home / ".local/bin/chezmoi"), DOTFILES_TEST_TOOL_HOME=str(home),
               DOTFILES_TEST_NODE=str(home / ".pixi/bin/node"),
               DOTFILES_TEST_PI_MODULE=str(home / ".bun/managed/pi/node_modules/@earendil-works/pi-coding-agent/dist/index.js"))
    for name in ("claude", "codex", "kimi", "opencode", "codegraph"):
        env["DOTFILES_TEST_" + name.upper()] = str(home / ".local/bin" / name)
    summaries = []
    for pattern in ("test_shell_behavior.py", "test_agent_payload.py", "test_codegraph.py", "test_history_behavior.py"):
        result = run([str(home / ".pixi/bin/python"), "-m", "unittest", "discover", "-s", "tests",
                      "-p", pattern, "-v"], env=env, cwd=SOURCE, timeout=600, allow_failure=True)
        # Required native checks may not be converted to successful skips.
        if result.returncode != 0 or "skipped=" in result.stderr:
            print(result.stderr, file=sys.stderr)
        require(result.returncode == 0 and "skipped=" not in result.stderr,
                f"native observable suite failed or skipped: {pattern}")
        summary = next((line for line in result.stderr.splitlines() if line.startswith("Ran ")), "")
        require(bool(summary), f"native suite did not run: {pattern}")
        summaries.append({"suite": pattern, "result": summary, "skips": 0})
    report["behavior_suites"] = summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("x86_64", "aarch64"), required=True)
    parser.add_argument("--role", choices=("workstation", "remote-compute"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    machine = platform.machine()
    actual_arch = {"arm64": "aarch64", "aarch64": "aarch64", "x86_64": "x86_64"}.get(machine, machine)
    report = {"platform": "macos", "arch": args.arch, "actual_arch": actual_arch,
              "role": args.role, "native_execution": sys.platform == "darwin", "status": "unavailable",
              "runtime": platform.platform(), "image_version": os.environ.get("ImageVersion", "unknown"),
              "commit": os.environ.get("GITHUB_SHA", "local"), "checks": []}
    if os.environ.get("GITHUB_RUN_ID"):
        report["run_url"] = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    phase = "runtime"
    started = time.monotonic()
    try:
        require(sys.platform == "darwin", "native macOS execution requires Darwin; foreign rendering is separate")
        require(actual_arch == args.arch, "native macOS runner architecture does not match the requested target")
        version = subprocess.check_output(["/usr/bin/sw_vers", "-productVersion"], text=True).strip()
        report["os_version"] = version
        require(int(version.split(".")[0]) >= 13, "common defaults require macOS 13 or newer")
        report["checks"].append("native runtime and architecture")
        report["status"] = "failed"
        # Every install/cache/client fixture belongs to this temporary tree.
        with tempfile.TemporaryDirectory(prefix="dotfiles-native-macos-", dir=os.environ.get("RUNNER_TEMP")) as temporary:
            home = Path(temporary) / "device with spaces"
            originals = seed_device(home)
            env = minimal_environment(home)
            command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(home), "--role", args.role]
            phase = "profile detection"
            plan = json.loads(run([*command, "--plan"], env=env, cwd=SOURCE).stdout)
            require(plan["platform"] == "macos" and plan["arch"] == args.arch and plan["role"] == args.role,
                    "detected macOS deployment profile")
            report["checks"].append(phase)
            snapshot = None
            for attempt in (1, 2):
                phase = f"default installation {attempt}"
                run(command, env=env, cwd=SOURCE, timeout=2400)
                check_preservation(home, originals)
                current = managed_snapshot(home)
                if snapshot is not None:
                    require(snapshot == current, "managed files are idempotent after default reapplication")
                snapshot = current
                report["checks"].append(phase)
            phase = "pinned commands and pending history"
            check_pinned_tools(home, plan, report)
            report["checks"].append(phase)
            phase = "ordinary native configuration discovery"
            check_native_discovery(home, args.role)
            report["checks"].append(phase)
            phase = "native shell, instruction, CodeGraph and encrypted-history behavior"
            check_portable_suites(home, args.role, report)
            report["checks"].append(phase)
        report["status"] = "passed"
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        report["failed_check"] = phase
        # Errors contain test/check labels only, never config or account data.
        report["reason"] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"native macOS {args.arch} {args.role}: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
