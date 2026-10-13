"""Execute WSL acceptance in a disposable distro; never substitute Linux CI."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--probe-nu", action="store_true",
                      help="check ordinary Nu startup in an existing rendered home; never a native WSL2 pass")
    parser.add_argument("--role", choices=("workstation", "remote-compute"), default="workstation")
    parser.add_argument("--arch", choices=("x86_64", "aarch64"), default="x86_64")
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--windows-file")
    parser.add_argument("--windows-command")
    parser.add_argument("--interop-token")
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--run-url", default="")
    arguments = parser.parse_args()
    report = {"platform": "wsl", "role": arguments.role, "architecture": arguments.arch,
              "phase": "native-preflight", "nativePass": False,
              "commit": arguments.commit, "runUrl": arguments.run_url,
              "runtime": {"system": platform.system(), "kernel": platform.release(),
                          "architecture": platform.machine()}, "checks": []}
    environment = {"HOME": str(arguments.home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color",
                   "LANG": "C.UTF-8", "CODEGRAPH_NO_DOWNLOAD": "1", "DO_NOT_TRACK": "1",
                   "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "1",
                   "DISABLE_AUTOUPDATER": "1", "DOTFILES_TEST_TRACE_CLIENT_SETTINGS": "1"}
    for name in ("WSL_DISTRO_NAME", "WSL_INTEROP"):
        if os.environ.get(name):
            environment[name] = os.environ[name]

    def run(command, *, env=None, cwd=None, timeout=60, allow_failure=False):
        result = subprocess.run([str(part) for part in command], env=env or environment,
                                cwd=cwd or SOURCE, capture_output=True, text=True, timeout=timeout)
        if result.returncode and not allow_failure:
            raise RuntimeError(f"command {Path(command[0]).name} failed (exit {result.returncode}): "
                               + (result.stderr or result.stdout)[-5000:])
        return result

    def check(name, operation):
        started = time.monotonic()
        try:
            details = operation()
        except Exception:
            report["checks"].append({"name": name, "passed": False})
            raise
        report["checks"].append({"name": name, "passed": True,
                                 "seconds": round(time.monotonic() - started, 3), "details": details})
        print(f"native-wsl: passed {name}", flush=True)

    def require(condition, message):
        if not condition:
            raise RuntimeError(message)

    def ordinary_nu(script):
        # -e enters the REPL startup path; -c bypasses ordinary config/env
        # discovery even though explicit --config flags can hide that omission.
        return run([arguments.home / ".pixi/bin/nu", "-e", script + "; exit"], cwd=arguments.home)

    def probe_nu_startup():
        script = '''print ({
            editor: $env.EDITOR?, polling: $env.CHOKIDAR_USEPOLLING?, prompt: $env.STARSHIP_SHELL?,
            logs: (scope commands | where name == "logs" | length),
            zoxide: (scope aliases | where name == "z" | length),
            historyHooks: ($env.config.hooks.pre_execution | length)
        } | to json --raw)'''
        startup = json.loads(ordinary_nu(script).stdout)
        require(startup["editor"] == "hx", "Ordinary Nu startup did not load the managed env configuration")
        require(startup["polling"] == ("1" if arguments.role == "remote-compute" else "0"),
                "Ordinary Nu startup did not load its host-role setting")
        require(startup["logs"] == 1 and startup["zoxide"] == 1,
                "Ordinary Nu startup did not load the managed shell configuration")
        require(startup["prompt"] == "nu" and startup["historyHooks"] > 0,
                "Ordinary Nu startup did not load the prompt/history vendor resources")
        return startup

    try:
        if arguments.probe_nu:
            report["phase"] = "rendered-nu-startup"
            report["layer"] = "configuration"
            require(arguments.home.is_absolute(), "Select an absolute rendered home for the Nu probe")
            profile = json.loads((arguments.home / ".config/dotfiles/profile.json").read_text())
            require(profile["platform"] == "wsl" and profile["role"] == arguments.role,
                    "Nu probe requires the matching rendered WSL role")
            check("ordinary Nu env/config/vendor startup", probe_nu_startup)
            return 0
        kernel = platform.release().lower()
        if platform.system() != "Linux" or "microsoft" not in kernel or "wsl2" not in kernel:
            raise RuntimeError("Native WSL2 kernel required; ordinary Linux and WSL1 are not a WSL2 pass")
        require(platform.machine() == arguments.arch, "WSL architecture differs from the requested native target")
        require(os.geteuid() != 0, "Native acceptance must run as the disposable unprivileged Linux user")
        home = arguments.home.resolve()
        require(arguments.home.is_absolute() and home != Path.home().resolve(), "Select a separate absolute validation home")
        require(not home.exists(), "Native acceptance requires a fresh disposable validation home")
        require(not str(SOURCE.resolve()).startswith("/mnt/") and not str(home).startswith("/mnt/"),
                "Source and validation home must use the distro Linux filesystem")
        require(arguments.windows_file and arguments.windows_command and arguments.interop_token,
                "Native acceptance requires an explicit disposable Windows interoperability fixture")
        require(re.fullmatch(r"[A-Za-z0-9-]+", arguments.interop_token) is not None,
                "Interop token must contain only letters, digits, and hyphens")
        require(not any(char in arguments.windows_file for char in ('"', '\r', '\n')),
                "Windows fixture path contains unsupported command characters")
        require(" " in arguments.windows_file,
                "Keep the Windows interoperability fixture under a path containing spaces")
        environment["HOME"] = str(home)
        report["phase"] = "windows-interoperability"

        def interoperability():
            linux_file = run(["wslpath", "-u", arguments.windows_file]).stdout.strip()
            require(Path(linux_file).read_text().strip() == arguments.interop_token,
                    "The mounted Windows file does not contain the disposable fixture token")
            windows_roundtrip = run(["wslpath", "-w", linux_file]).stdout.strip()
            require(windows_roundtrip.lower() == arguments.windows_file.lower(),
                    "Windows fixture path failed its WSL conversion roundtrip")
            source_windows = run(["wslpath", "-w", str(SOURCE)]).stdout.strip()
            source_roundtrip = run(["wslpath", "-u", source_windows]).stdout.strip()
            require(Path(source_roundtrip).resolve() == SOURCE, "Linux source path failed its UNC roundtrip")
            windows_command = run(["wslpath", "-u", arguments.windows_command]).stdout.strip()
            # Run from the mounted fixture directory so cmd.exe resolves a
            # relative filename. This tests the spaced Windows cwd without
            # nesting absolute paths inside cmd.exe's /c quoting rules.
            output = run([windows_command, "/d", "/c", "type fixture.txt"],
                         cwd=Path(linux_file).parent).stdout
            require(arguments.interop_token in output, "Windows command execution did not read the fixture")
            return {"windowsCommand": "cmd.exe", "windowsPathWithSpaces": True, "linuxPathRoundtrip": True}

        check("Windows executable and path roundtrip", interoperability)
        report["phase"] = "deployment"
        command = ["/bin/bash", SOURCE / "bootstrap.sh", "--home", home, "--role", arguments.role]
        planned = run([*command, "--plan"])
        plan = json.loads(planned.stdout)
        require(plan["profile"] == f"wsl-{arguments.role}" and plan["arch"] == arguments.arch,
                "Bootstrap did not detect the actual WSL profile and Linux architecture")
        require(not plan["settings"]["systemChanges"] and not plan["settings"]["loginShellChanges"],
                "Ordinary WSL bootstrap must remain user-scoped")
        extra_registry = home / ".pixi/manifests/pixi-global.toml"
        extra_registry.parent.mkdir(parents=True)
        extra_registry.write_text('version = 1\n[envs.device-extra]\nchannels = ["conda-forge"]\n'
                                  'dependencies = { zoxide = "==0.10.0" }\n'
                                  'exposed = { device-zoxide = "zoxide" }\n')
        bun_registry = home / ".bun/install/global/package.json"
        bun_registry.parent.mkdir(parents=True)
        bun_registry.write_text('{"dependencies":{"device-extra":"1.0.0"}}\n')
        original_bun_registry = bun_registry.read_bytes()
        check("full default WSL bootstrap", lambda: run(command, timeout=2400).returncode)
        report["phase"] = "runtime"
        managed = dict(environment, PATH=f"{home}/.bun/bin:{home}/.local/bin:{home}/.pixi/bin:{home}/.cargo/bin:/usr/bin:/bin",
                       XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
                       XDG_STATE_HOME=str(home / ".local/state"), XDG_CACHE_HOME=str(home / ".cache"),
                       PIXI_HOME=str(home / ".pixi"), BUN_INSTALL=str(home / ".bun"),
                       CARGO_HOME=str(home / ".cargo"), RUSTUP_HOME=str(home / ".rustup"),
                       ATUIN_CONFIG_DIR=str(home / ".config/atuin"), ATUIN_DATA_DIR=str(home / ".local/share/atuin"),
                       CODEX_HOME=str(home / ".codex"), KIMI_CODE_HOME=str(home / ".kimi-code"),
                       PI_CODING_AGENT_DIR=str(home / ".pi/agent"), TMPDIR=str(home / ".cache/tmp"))

        def versions():
            # Conda normalizes numeric components: Helix's declared 25.07.1
            # appears as 25.7.1 in installed metadata. Compare exact components
            # rather than treating that spelling as a different release.
            def version_components(value):
                return tuple(int(part) if part.isdecimal() else part for part in value.split("."))

            seen = {}
            inventory = json.loads(run([home / ".pixi/bin/pixi", "global", "list", "--json"], env=managed).stdout)
            installed = {item["name"]: item for item in inventory}
            expected_platform = "linux-64" if arguments.arch == "x86_64" else "linux-aarch64"
            commands = {item: None for item in ("pixi", "chezmoi", "rustup")}
            for package in plan["packages"]:
                require(package["environment"] in installed, f"Missing Pixi environment {package['environment']}")
                actual = installed[package["environment"]]
                require(actual["platform"] == expected_platform, "Pixi installed an unexpected Linux subdir")
                actual_dependencies = {item["name"]: item["version"] for item in actual["dependencies"]}
                for dependency, pin in package["dependencies"].items():
                    require(dependency in actual_dependencies and
                            version_components(actual_dependencies[dependency]) == version_components(pin.removeprefix("==")),
                            f"Installed package {dependency} does not match its exact source pin")
                for exposed, binary in package["exposed"].items():
                    dependency = binary if binary in package["dependencies"] else next(iter(package["dependencies"]))
                    # npm/npx have their own bundled versions. Conda fzf
                    # reports only major/minor. Their exact package ownership
                    # is checked through Pixi above, separately from CLI output.
                    commands[exposed] = None if binary in ("npm", "npx", "fzf") else package["dependencies"][dependency].removeprefix("==")
            for package in plan["agentPackages"]:
                commands[package["name"]] = package["version"]
                if package["name"] == "opencode" and "opencode2" in plan["tools"]:
                    commands["opencode2"] = package["version"]
            for exposed, version in commands.items():
                location = run(["/bin/sh", "-c", f"command -v {exposed}"], env=managed).stdout.strip()
                require(location.startswith(str(home) + "/"), f"{exposed} is outside the managed home")
                diagnostic = run([location, "--version"], env=managed)
                output = diagnostic.stdout + diagnostic.stderr
                if version:
                    require(version in output, f"{exposed} did not report its pinned version {version}")
                seen[exposed] = version or output.splitlines()[0]
            return seen

        check("managed command and agent versions", versions)

        def standalone_shells():
            names = ("EDITOR", "UV_PYTHON_PREFERENCE", "PIP_INDEX_URL", "UV_DEFAULT_INDEX",
                     "CHOKIDAR_USEPOLLING", "ATUIN_CONFIG_DIR", "ATUIN_DATA_DIR")
            expected = ["hx", "managed", "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple",
                        "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple",
                        "1" if arguments.role == "remote-compute" else "0",
                        str(home / ".config/atuin"), str(home / ".local/share/atuin")]
            destination = home / "native-wsl-navigation"
            destination.mkdir()
            log = home / "application.log"
            log.write_text("2026-10-13 ERROR native-wsl-log-token count=42\n")
            for shell in ("bash", "zsh", "nu"):
                executable = home / ".pixi/bin" / shell
                if shell == "nu":
                    script = "print ($env | select " + " ".join(names) + " | to json --raw)"
                    result = ordinary_nu(script)
                    actual = json.loads(result.stdout)
                    require([actual[name] for name in names] == expected, "Standalone Nu shared values differ")
                    navigation = '^zoxide add native-wsl-navigation; z native-wsl-navigation; print $env.PWD; logs --print ../application.log'
                    output = ordinary_nu(navigation).stdout
                else:
                    script = '. "$HOME/.env_core"; . "$HOME/.env_core"; printf "%s\\n" ' + " ".join(f'"${{{name}}}"' for name in names)
                    require(run([executable, "-c", script], cwd=home).stdout.splitlines() == expected,
                            f"Standalone {shell} shared values differ")
                    navigation = 'zoxide add native-wsl-navigation; z native-wsl-navigation; pwd; logs --print ../application.log'
                    output = run([executable, "-i", "-c", navigation], cwd=home).stdout
                require(str(destination) in output and "native-wsl-log-token" in output,
                        f"{shell} zoxide/Tailspin behavior failed")
            pip = run([home / ".pixi/bin/pip", "config", "get", "global.index-url"], env=managed)
            require(pip.stdout.strip() == expected[2], "pip did not discover the TUNA configuration")
            uv = run([home / ".pixi/bin/uv", "--show-settings", "pip", "install", "--dry-run", "--system",
                      "--python", home / ".pixi/bin/python", "--offline", "dotfiles-unavailable==0.0.0"],
                     env=managed, allow_failure=True)
            # uv 0.13 prints the configured index without a trailing slash.
            require(expected[2] in uv.stdout + uv.stderr, "uv did not discover the TUNA configuration")
            return {"shells": ["nu", "bash", "zsh"], "mirrors": "TUNA", "legacyEnvironment": "absent"}

        check("standalone shells, navigation, logs and mirrors", standalone_shells)

        test_environment = dict(managed, DOTFILES_TEST_CHEZMOI=str(home / ".local/bin/chezmoi"),
                                DOTFILES_TEST_TOOL_HOME=str(home), DOTFILES_TEST_NODE=str(home / ".pixi/bin/node"),
                                DOTFILES_TEST_PLATFORM="wsl", DOTFILES_TEST_ROLE=arguments.role,
                                DOTFILES_TEST_PI_MODULE=str(home / ".bun/managed/pi/node_modules/@earendil-works/pi-coding-agent/dist/index.js"))
        for client in ("CODEX", "CLAUDE", "KIMI", "OPENCODE", "CODEGRAPH"):
            test_environment[f"DOTFILES_TEST_{client}"] = str(home / ".bun/bin" / client.lower())
        for pattern in ("test_shell_behavior.py", "test_agent_payload.py", "test_codegraph.py", "test_history_behavior.py"):
            def acceptance_suite(pattern=pattern):
                result = run([home / ".pixi/bin/python", "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"],
                             env=test_environment, timeout=420)
                output = result.stdout + result.stderr
                require("skipped" not in output.lower(), f"Native suite {pattern} reported unavailable acceptance")
                return "Actual WSL execution; synthetic fixture state and loopback endpoints only"
            check(pattern, acceptance_suite)

        report["phase"] = "reapplication"
        auth = home / ".codex/auth.json"
        auth.write_text('{"synthetic-device-state":"untouched"}\n')
        auth_before = auth.read_bytes()
        history_environment = dict(managed, ATUIN_SESSION=run([home / ".pixi/bin/atuin", "uuid"], env=managed).stdout.strip())
        record = run([home / ".pixi/bin/atuin", "history", "start", "--", "printf native-wsl-preserved-history"],
                     env=history_environment).stdout.strip()
        run([home / ".pixi/bin/atuin", "history", "end", "--exit", "0", record], env=history_environment)
        launchers = {name: (home / ".bun/bin" / name).read_bytes()
                     for name in ("kimi", "pi", "opencode", "claude", "codex")}

        def reapplication():
            run([*command, "--agents", "none"], timeout=2400)
            require(auth.read_bytes() == auth_before, "Reapplication replaced host-local authentication")
            require(bun_registry.read_bytes() == original_bun_registry, "Reapplication replaced the Bun global registry")
            for name, before in launchers.items():
                require((home / ".bun/bin" / name).read_bytes() == before, "Agent opt-out changed an existing launcher")
            require("native-wsl-preserved-history" in run([home / ".pixi/bin/atuin", "search", "--cmd-only",
                    "native-wsl-preserved-history"], env=managed).stdout, "Reapplication lost local command history")
            run([home / ".pixi/bin/device-zoxide", "--version"], env=managed)
            require("pending activation" in run([home / ".local/bin/dotfiles-history", "status"], env=managed).stdout.lower(),
                    "Ordinary bootstrap activated history sync")
            require(not (SOURCE / ".codegraph").exists() and not (home / ".codegraph").exists(),
                    "Ordinary deployment indexed a source or device project")
            return {"credentials": "preserved", "history": "preserved", "unrelatedInstall": "preserved",
                    "omittedAgents": "preserved", "activation": "pending"}

        check("reapplication and explicit device activation", reapplication)
        report["phase"] = "complete"
        report["nativePass"] = True
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        report["failure"] = str(error)
        print(f"native-wsl: {error}", file=sys.stderr)
        phase = report.get("phase", "unknown phase")
        print(f"::error title=Native WSL2 acceptance failed::{phase}", file=sys.stderr, flush=True)
        return 1
    finally:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
