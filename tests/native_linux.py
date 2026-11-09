"""Linux remote-compute acceptance in a fresh, unprivileged validation home.

The caller owns the Linux runtime, image, resource limits, and network route.
This gate installs only the default selection; it never claims T9K kernel,
network-filesystem, legacy-home migration, or native Windows evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
import unittest

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

from pins import common_pin, manager_pin

SOURCE = Path(__file__).resolve().parents[1]
REQUIRED_SUITES = (
    "test_shell_behavior.py", "test_agent_payload.py", "test_codegraph.py",
    "test_history_behavior.py", "test_local_history_behavior.py", "test_portable_history_import.py",
)
DEFAULT_AGENTS = {"kimi", "pi", "opencode", "claude", "codex", "minimax", "qoder"}
LOG_LIMIT = 2 * 1024 * 1024
TASK_CPUS = 4
TASK_MEMORY_BYTES = 8 * 1024 ** 3


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_json(path, value):
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_paths(home, artifacts, source=SOURCE):
    require(home.is_absolute() and artifacts.is_absolute(), "home and artifacts must be absolute paths")
    require(home == home.resolve() and artifacts == artifacts.resolve(), "validation paths must not traverse symlinks")
    require(not home.exists() and not home.is_symlink(), "validation home must be fresh and absent")
    require(home != Path.home().resolve(), "validation home must differ from the account home")
    require(not (home.is_relative_to(source) or artifacts.is_relative_to(source)),
            "validation home and artifacts must be outside the source tree")
    require(not (home.is_relative_to(artifacts) or artifacts.is_relative_to(home)),
            "validation home and artifacts must not overlap")
    require(not artifacts.exists() or (artifacts.is_dir() and not any(artifacts.iterdir())),
            "artifacts must be absent or an empty directory")


def resource_snapshot(cgroup=Path("/sys/fs/cgroup")):
    host_cpus = os.cpu_count() or 1
    cpu_quota = None
    cpu_stat = {}
    cpu_path = None
    for root, quota_name, period_name in (
            (cgroup, "cpu.max", None),
            (cgroup / "cpu", "cpu.cfs_quota_us", "cpu.cfs_period_us"),
            (cgroup / "cpu,cpuacct", "cpu.cfs_quota_us", "cpu.cfs_period_us")):
        if not (root / quota_name).is_file():
            continue
        cpu_path = str(root)
        if period_name is None:
            quota, period = (root / quota_name).read_text().split()
        else:
            quota = (root / quota_name).read_text().strip()
            period = (root / period_name).read_text().strip()
        if quota != "max" and int(quota) > 0:
            cpu_quota = int(quota) / int(period)
        if (root / "cpu.stat").is_file():
            cpu_stat = {name: int(value) for name, value in
                        (line.split() for line in (root / "cpu.stat").read_text().splitlines())}
        break
    memory_limit = None
    memory_path = None
    for path in (cgroup / "memory.max", cgroup / "memory/memory.limit_in_bytes"):
        if path.is_file():
            memory_path = str(path)
            value = path.read_text().strip()
            if value != "max" and 0 < int(value) < 2 ** 60:
                memory_limit = int(value)
            break
    usable = min(host_cpus, TASK_CPUS, cpu_quota if cpu_quota is not None else TASK_CPUS)
    return {"host_visible_cpus": host_cpus, "task_cpu_grant": TASK_CPUS,
            "cgroup_cpu_quota": cpu_quota, "usable_cpus": usable,
            "child_parallelism": max(1, int(usable) - 1), "cpu_cgroup": cpu_path,
            "cpu_stat": cpu_stat, "task_memory_bytes": TASK_MEMORY_BYTES,
            "cgroup_memory_limit_bytes": memory_limit, "memory_cgroup": memory_path}


def clean_environment(home, temporary):
    parallelism = str(resource_snapshot()["child_parallelism"])
    environment = {
        "HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TERM": "xterm-256color", "LANG": "C.UTF-8", "CI": "1",
        "TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "CODEGRAPH_NO_DOWNLOAD": "1", "CODEGRAPH_NO_DAEMON": "1", "DO_NOT_TRACK": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "1",
        "DISABLE_AUTOUPDATER": "1", "OMP_NUM_THREADS": parallelism, "OPENBLAS_NUM_THREADS": parallelism,
        "RAYON_NUM_THREADS": parallelism, "MAKEFLAGS": "-j" + parallelism,
        "NODE_OPTIONS": "--max-old-space-size=2048",
    }
    # Only network routing/CA inputs cross the controller boundary. No account,
    # shell, package cache, or agent authentication state is inherited.
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy",
                 "all_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR"):
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


def managed_environment(home, temporary):
    environment = clean_environment(home, temporary)
    environment.update(
        PATH=f"{home}/.bun/bin:{home}/.local/bin:{home}/.pixi/bin:{home}/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
        XDG_STATE_HOME=str(home / ".local/state"), XDG_CACHE_HOME=str(home / ".cache"),
        PIXI_HOME=str(home / ".pixi"), BUN_INSTALL=str(home / ".bun"),
        CARGO_HOME=str(home / ".cargo"), RUSTUP_HOME=str(home / ".rustup"),
        ATUIN_CONFIG_DIR=str(home / ".config/atuin"), ATUIN_DATA_DIR=str(home / ".local/share/atuin"),
        CODEX_HOME=str(home / ".codex"), CLAUDE_CONFIG_DIR=str(home / ".claude"),
        KIMI_CODE_HOME=str(home / ".kimi-code"), PI_CODING_AGENT_DIR=str(home / ".pi/agent"),
    )
    return environment


def deterministic_environment(home, temporary, tools):
    environment = clean_environment(home, temporary)
    # These tests own their HOME, state roots, PATH and fake executables. Borrow
    # only explicitly requested read-only tools, never the installed device env.
    for name in ("DOTFILES_TEST_CHEZMOI", "DOTFILES_TEST_TOOL_HOME", "DOTFILES_TEST_NODE",
                 "DOTFILES_TEST_NU", "DOTFILES_TEST_MAMBA", "DOTFILES_TEST_BASH", "DOTFILES_TEST_ZSH",
                 "DOTFILES_TEST_KIMI", "DOTFILES_TEST_OPENCODE", "DOTFILES_TEST_POWERSHELL", "DOTFILES_TEST_PWSH"):
        if name in tools:
            environment[name] = tools[name]
    return environment


def run(command, *, env, cwd, timeout, log, records):
    """Bound output and stop the entire subprocess group on timeout."""
    command = [str(part) for part in command]
    started = time.monotonic()
    output = bytearray()
    total = 0
    timed_out = False
    with subprocess.Popen(command, env=env, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, start_new_session=True) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        timed_out = True
                        break
                    for key, _events in selector.select(min(remaining, 0.5)):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        output.extend(chunk)
                        if len(output) > LOG_LIMIT:
                            del output[:-LOG_LIMIT]
                if not timed_out:
                    try:
                        process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
                    except subprocess.TimeoutExpired:
                        timed_out = True
        finally:
            if timed_out:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                # A child can outlive its parent and close the output pipe.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            process.stdout.close()
    prefix = b"[earlier output omitted; bounded tail follows]\n" if total > LOG_LIMIT else b""
    log.write_bytes(prefix + output)
    records.append({"command": command, "exit_code": process.returncode,
                    "timed_out": timed_out, "timeout_seconds": timeout,
                    "seconds": round(time.monotonic() - started, 3), "log": log.name,
                    "output_bytes": total, "log_truncated": total > LOG_LIMIT,
                    "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
    require(not timed_out, f"command timed out; see {log.name}")
    require(process.returncode == 0, f"command exited {process.returncode}; see {log.name}")
    return output.decode("utf-8", errors="replace")


def classify_skip(identifier, reason):
    """Allow named foreign or unselected cases, never a missing Linux runtime."""
    module = identifier.split(".", 1)[0]
    foreign = {
        "test_portable_history_import.PortableHistoryImportTests.test_macos_nu_defaults_import_the_only_native_history":
            "native macOS history discovery",
        "test_portable_history_import.PortableHistoryImportTests.test_macos_explicit_nu_file_selects_one_of_two_default_histories":
            "native macOS history discovery",
        "test_macos.MacOSProfileTests.test_native_verifier_reports_foreign_execution_as_unavailable":
            "this check exercises refusal on a foreign runtime",
        "test_wsl.WSLNativeBoundaryTests.test_disposable_distro_plan_pins_rootfs_and_never_provisions":
            "PowerShell parser/planning check requires DOTFILES_TEST_PWSH",
        "test_wsl.WSLNativeBoundaryTests.test_provisioning_refuses_an_ordinary_linux_host_without_creating_state":
            "the non-Windows refusal check requires Linux PowerShell",
        "test_wsl.WSLNativeBoundaryTests.test_native_gate_reports_linux_as_unavailable_before_bootstrap":
            "this check demonstrates that ordinary Linux cannot establish a WSL pass",
    }
    if foreign.get(identifier) == reason:
        return "foreign-platform"
    if (identifier.startswith("test_windows_deployment.WindowsBoundaryTests.")
            and reason == "set DOTFILES_TEST_POWERSHELL for the public Windows boundary"):
        return "foreign-platform"
    if (identifier.startswith("test_windows_deployment.WindowsNativeInstallTests.")
            and reason == "actual Windows installation runs on the native runner"):
        return "foreign-platform"
    opt_in = {
        "test_common_install": "requires explicit isolated network installation",
        "test_agents": "requires explicit isolated network agent installation",
        "test_bundle_install": "requires explicit isolated bundle installation",
        "test_bundle_resolution": "requires explicit foreign package resolution",
        "test_package_resolution": "requires explicit isolated Pixi resolution for all supported targets",
        "test_agent_herdr": "herdr is not installed",
    }
    if opt_in.get(module) == reason:
        return "unselected-scope"
    return "unexpected"


def audit_suite(summary):
    require(summary.get("tests_run", 0) > 0, "suite executed no tests")
    require(summary.get("successful") and not summary.get("expected_failures"),
            "suite reported a failure, error, or expected failure")
    skipped = [{**item, "classification": classify_skip(item["test"], item["reason"])}
               for item in summary.get("skipped", [])]
    unexpected = [item for item in skipped if item["classification"] == "unexpected"]
    require(not unexpected, "unexpected acceptance skips: " + ", ".join(item["test"] for item in unexpected))
    return {**summary, "skipped": skipped, "unexpected_skips": 0}


def suite_main(pattern, destination, exclude_required=False):
    # Run suites in their own bounded process and preserve structured skip IDs;
    # string searches for 'skipped' confuse test names and platform exclusions.
    sys.path.insert(0, str(SOURCE))
    suite = unittest.defaultTestLoader.discover(str(SOURCE / "tests"), pattern=pattern)
    if exclude_required:
        def selected(tests):
            for test in tests:
                if isinstance(test, unittest.TestSuite):
                    yield from selected(test)
                elif test.__class__.__module__ + ".py" not in REQUIRED_SUITES:
                    yield test
        suite = unittest.TestSuite(selected(suite))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {"pattern": pattern, "tests_run": result.testsRun,
               "successful": result.wasSuccessful(),
               "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
               "failures": [test.id() for test, _detail in result.failures],
               "errors": [test.id() for test, _detail in result.errors],
               "expected_failures": [test.id() for test, _detail in result.expectedFailures],
               "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]}
    write_json(destination, summary)
    return 0 if result.wasSuccessful() else 1


def first_line_version_matches(output, pin):
    first_line = output.splitlines()[0] if output.splitlines() else ""
    tokens = re.findall(r"(?<![A-Za-z0-9_.+-])v?([0-9]+(?:\.[0-9]+)+(?:[-+][A-Za-z0-9.-]+)?)(?![A-Za-z0-9_.+-])",
                        first_line)
    return pin in tokens


def snapshot_fingerprint(path, home):
    require(path.is_file() and not path.is_symlink(), f"managed file must be regular: {path.relative_to(home)}")
    contents = path.read_bytes()
    return {"sha256": hashlib.sha256(contents).hexdigest(), "mode": path.stat().st_mode & 0o777}


def trampoline_metadata(home, plan):
    registry = tomllib.loads((home / ".pixi/manifests/pixi-global.toml").read_text())
    owners = {command: name for name, environment in registry["envs"].items()
              for command in environment.get("exposed", {})}
    expected = {command: package["environment"] for package in plan["packages"]
                for command in package["exposed"]}
    directory = home / ".pixi/bin/trampoline_configuration"
    for command, owner in expected.items():
        require(owners.get(command) == owner, f"Pixi exposure has an unexpected owner: {command}")
        require((directory / (command + ".json")).is_file(), f"missing Pixi trampoline metadata: {command}")
    captured = {}
    for path in sorted(directory.glob("*.json")):
        fingerprint = snapshot_fingerprint(path, home)
        values = json.loads(path.read_bytes())
        require(isinstance(values, dict) and isinstance(values.get("exe"), str),
                f"Pixi trampoline metadata has no executable: {path.name}")
        require(path.stem in owners, f"Pixi trampoline metadata has no registry owner: {path.name}")
        executable = Path(values["exe"])
        prefix = home / ".pixi/envs" / owners[path.stem]
        require(executable.is_absolute() and executable.resolve().is_relative_to(prefix)
                and executable.is_file() and os.access(executable, os.X_OK),
                f"Pixi trampoline executable is missing, not executable, or outside its owned prefix: {path.name}")
        captured[str(path.relative_to(home))] = {**fingerprint, "values": values,
                                               "resolved_executable": str(executable.resolve())}
    return captured


def source_managed_paths(home):
    # Chezmoi owns source-name mapping, ignore rules and profile selection.
    # Its inventory lists desired paths even when a target has been removed.
    result = subprocess.run([
        str(home / ".local/bin/chezmoi"), "--source", str(SOURCE), "--destination", str(home),
        "--config", str(home / ".config/chezmoi/chezmoi.toml"),
        "--cache", str(home / ".cache/chezmoi"),
        "--persistent-state", str(home / ".config/chezmoi/chezmoistate.boltdb"),
        "--no-tty", "managed", "--include=files", "--path-style=relative", "--nul-path-separator",
    ], env=managed_environment(home, home / ".cache/tmp"), capture_output=True, check=True, timeout=30)
    paths = set()
    for name in result.stdout.split(b"\0"):
        if not name:
            continue
        relative = Path(os.fsdecode(name))
        require(not relative.anchor and relative.parts and ".." not in relative.parts,
                "Chezmoi returned an invalid source-owned path")
        paths.add(home / relative)
    return paths


def snapshot(home, plan):
    paths = source_managed_paths(home)
    trees = {".config/nushell", ".local/share/nushell/vendor", ".local/bin", ".local/lib/dotfiles"}
    for line in (SOURCE / "deployment/agent-payload/targets.tsv").read_text().splitlines():
        if line and not line.startswith("#"):
            kind, _source, destination = line.split("|")
            if kind == "tree":
                trees.add(destination)
            elif kind in {"file", "block"}:
                paths.add(home / destination)
    # Runtime client settings are intentionally excluded from Chezmoi and
    # merged by the adapter; its target catalog remains their ownership source.
    for line in (SOURCE / "deployment/client-settings/targets.tsv").read_text().splitlines():
        if line and not line.startswith("#"):
            _format, _source, destination, _policy = line.split("|")
            paths.add(home / destination)
    for relative in trees:
        paths.update(path for path in (home / relative).rglob("*") if path.is_file())
    for package in plan["packages"]:
        paths.update(home / ".pixi/bin" / command for command in package["exposed"])
    for package in plan["agentPackages"]:
        paths.update(home / ".local/bin" / command for command in package["commands"])
    return {str(path.relative_to(home)): snapshot_fingerprint(path, home) for path in sorted(paths)}


def seed_device(home):
    originals = {
        ".codex/auth.json": '{"synthetic-device-state":"untouched"}\n',
        ".bash_history": "echo synthetic-existing-history\n",
        ".bun/install/global/package.json": '{"dependencies":{"device-extra":"1.0.0"}}\n',
        ".bun/bin/device-extra": "#!/bin/sh\nprintf 'synthetic-device-extra\\n'\n",
        ".agents/skills/device-extra/SKILL.md": "---\nname: device-extra\ndescription: Synthetic device skill.\n---\nPreserve this skill.\n",
    }
    for relative, contents in originals.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    (home / ".bun/bin/device-extra").chmod(0o755)
    settings_path = home / ".claude/settings.json"
    settings = json.loads(settings_path.read_text())
    settings.setdefault("env", {})["DOTFILES_SYNTHETIC_DEVICE"] = "preserved"
    write_json(settings_path, settings)
    registry_path = home / ".pixi/manifests/pixi-global.toml"
    registry = tomllib.loads(registry_path.read_text())
    registry["envs"]["device-extra"] = {
        "channels": ["conda-forge"], "dependencies": {"zoxide": "==" + common_pin("zoxide")},
        "exposed": {"device-zoxide": "zoxide"}}
    # Reuse the existing manifest encoder; preservation assertions below check
    # the sentinel environment independently of the merge implementation.
    sys.path.insert(0, str(SOURCE / "deployment"))
    from merge_pixi import toml_value
    registry_path.write_text("\n".join(f"{toml_value(key)} = {toml_value(value)}"
                                        for key, value in registry.items()) + "\n")
    return originals


def check_preservation(home, originals):
    for relative, contents in originals.items():
        path = home / relative
        require(path.is_file() and not path.is_symlink() and path.read_text() == contents,
                f"synthetic device state changed: {relative}")
    require(json.loads((home / ".claude/settings.json").read_text())["env"]["DOTFILES_SYNTHETIC_DEVICE"] == "preserved",
            "reapplication lost a nonowned client setting")
    registry = tomllib.loads((home / ".pixi/manifests/pixi-global.toml").read_text())
    extra = registry["envs"]["device-extra"]
    require(extra["exposed"] == {"device-zoxide": "zoxide"}
            and extra["dependencies"]["zoxide"] == "==" + common_pin("zoxide"),
            "reapplication lost unrelated package ownership")


def main():
    if sys.argv[1:2] == ["--run-suite"]:
        return suite_main(sys.argv[2], Path(sys.argv[3]), "--exclude-required" in sys.argv[4:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--ubuntu-release", choices=("20.04", "24.04"), required=True)
    parser.add_argument("--execution", choices=("emulated", "native"), required=True,
                        help="runtime origin supplied by the outer runner; x86_64 uname cannot detect emulation")
    parser.add_argument("--install-timeout", type=int, default=3600)
    parser.add_argument("--suite-timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.install_timeout <= 0 or args.suite_timeout <= 0:
        parser.error("installation and suite timeouts must be positive")
    try:
        validate_paths(args.home, args.artifacts)
    except RuntimeError as error:
        parser.error(str(error))
    args.artifacts.mkdir(parents=True, exist_ok=True)
    temporary = args.artifacts / "tmp"
    temporary.mkdir()
    report_path = args.artifacts / "report.json"
    report = {"schema_version": 1, "status": "running", "profile": "linux-remote-compute",
              "execution": args.execution, "native_t9k_pass": False, "installation_cache": "empty",
              "home": str(args.home), "checks": [], "commands": [], "suites": [],
              "limits": "Linux userspace evidence; no T9K kernel/netfs/legacy migration or Windows claim"}
    report["resources_before"] = resource_snapshot()
    report["disk_free_bytes_before"] = shutil.disk_usage(args.artifacts).free
    started = time.monotonic()
    environment = clean_environment(args.home, temporary)

    def command(name, arguments, *, env=environment, cwd=SOURCE, timeout=60):
        write_json(report_path, report)
        return run(arguments, env=env, cwd=cwd, timeout=timeout,
                   log=args.artifacts / f"{len(report['commands']) + 1:03d}-{name}.log",
                   records=report["commands"])

    def check(name, operation):
        report["current_check"] = name
        write_json(report_path, report)
        print(f"linux acceptance: {name}", flush=True)
        tick = time.monotonic()
        try:
            details = operation()
        except Exception:
            report["checks"].append({"name": name, "passed": False})
            raise
        report["checks"].append({"name": name, "passed": True,
                                 "seconds": round(time.monotonic() - tick, 3), "details": details})

    def source_identity():
        git = ["/usr/bin/git", "--no-optional-locks", "-c", f"safe.directory={SOURCE}", "-C", SOURCE]
        identity = {"commit": command("source-commit", [*git, "rev-parse", "HEAD"]).strip(),
                    "tree": command("source-tree", [*git, "rev-parse", "HEAD^{tree}"]).strip()}
        require(not command("source-status", [*git, "status", "--porcelain", "--untracked-files=normal"]).strip(),
                "Linux acceptance requires a clean committed source snapshot")
        return identity

    try:
        def preflight():
            require(sys.version_info >= (3, 11), "controller Python 3.11 or newer is required")
            require(not any(character.isspace() for character in sys.executable),
                    "controller Python path must contain no whitespace for deterministic fixture shebangs")
            require(sys.platform == "linux" and platform.machine() == "x86_64", "Linux x86_64 execution is required")
            require(os.geteuid() != 0, "Linux acceptance must run as an unprivileged user")
            release = {}
            for line in Path("/etc/os-release").read_text().splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    release[key] = value.strip('"')
            require(release.get("ID") == "ubuntu" and release.get("VERSION_ID") == args.ubuntu_release,
                    "actual Ubuntu userspace differs from the selected baseline")
            report["runtime"] = {"system": platform.system(), "kernel": platform.release(),
                                 "architecture": platform.machine(), "uid": os.geteuid(),
                                 "ubuntu_release": release["VERSION_ID"], "glibc": platform.libc_ver(),
                                 "controller_python": sys.version.split()[0], "execution_claim": "caller-supplied"}
            report["source"] = source_identity()
            return report["runtime"]
        check("runtime, source identity, and fresh target", preflight)
        bootstrap = ["/bin/bash", SOURCE / "bootstrap.sh", "--source", SOURCE, "--home", args.home]

        def planning():
            plan = json.loads(command("remote-plan", [*bootstrap, "--profile", "linux-remote-compute", "--plan"]))
            legacy = json.loads(command("legacy-plan", [*bootstrap, "--class", "t9k", "--plan"]))
            require(plan == legacy, "legacy T9K and canonical remote-compute plans differ")
            require(not args.home.exists(), "planning created the validation home")
            require(plan["platform"] == "linux" and plan["arch"] == "x86_64" and plan["role"] == "remote-compute",
                    "plan does not target Linux x86_64 remote compute")
            require(set(plan["agents"]) == DEFAULT_AGENTS and len(plan["agents"]) == len(DEFAULT_AGENTS)
                    and {item["name"] for item in plan["agentPackages"]} == DEFAULT_AGENTS | {"codegraph"},
                    "plan does not include all seven default agents and CodeGraph")
            require(not plan["bundles"] and not plan["settings"]["systemChanges"]
                    and not plan["settings"]["loginShellChanges"] and plan["settings"]["mode"] == "copy",
                    "plan expands beyond default copy-mode user deployment")
            write_json(args.artifacts / "plan.json", plan)
            return plan
        check("canonical and legacy default plans", planning)
        plan = json.loads((args.artifacts / "plan.json").read_text())
        full = [*bootstrap, "--profile", "linux-remote-compute"]
        check("full default bootstrap from empty home and caches",
              lambda: command("bootstrap-first", full, timeout=args.install_timeout) and "completed")
        require(not (args.home / ".codex/auth.json").exists(), "fresh bootstrap created authentication")
        require("REPLACE_ME" in (args.home / ".claude/settings.json").read_text(),
                "fresh configuration did not retain placeholder credentials")
        require(not any((args.home / name).exists() for name in
                        ("docs", "deployment", "tests", "bootstrap.sh", "README.md", ".github")),
                "source bookkeeping was deployed into the validation home")
        profile = json.loads((args.home / ".config/dotfiles/profile.json").read_text())
        require(all(profile[key] == plan[key] for key in ("platform", "role", "arch", "profile"))
                and profile["mode"] == "copy" and not profile["bundles"], "rendered profile differs from plan")
        managed = managed_environment(args.home, temporary)

        def pinned_commands():
            trampoline_metadata(args.home, plan)
            inventory = json.loads(command("pixi-inventory", [args.home / ".pixi/bin/pixi", "global", "list", "--json"], env=managed))
            installed = {item["name"]: item for item in inventory}
            for package in plan["packages"]:
                require(package["environment"] in installed, f"missing installed environment: {package['environment']}")
                actual = installed[package["environment"]]
                require(actual["platform"] == "linux-64", "installed package has a foreign platform")
                dependencies = {item["name"]: item["version"] for item in actual["dependencies"]}
                for name, version in package["dependencies"].items():
                    normalized = lambda value: tuple(int(part) if part.isdecimal() else part for part in value.split("."))
                    require(name in dependencies and normalized(dependencies[name]) == normalized(version.removeprefix("==")),
                            f"installed dependency differs from its catalog pin: {name}")
            tools = {command for package in plan["packages"] for command in package["exposed"]}
            tools.update(("pixi", "chezmoi", "rustup"))
            pins = {"pixi": manager_pin("PIXI_VERSION"), "chezmoi": manager_pin("CHEZMOI_VERSION"),
                    "rustup": manager_pin("RUSTUP_VERSION")}
            for package in plan["agentPackages"]:
                for exposed in package["commands"]:
                    tools.add(exposed)
                    pins[exposed] = package["version"]
                    launcher = args.home / ".local/bin" / exposed
                    require(launcher.is_file() and not launcher.is_symlink(), f"missing regular agent launcher: {exposed}")
                    if package["manager"] == "bun":
                        require(launcher.read_bytes() == (args.home / ".bun/bin" / exposed).read_bytes(),
                                f"agent launcher copies differ: {exposed}")
            versions = {}
            for exposed in sorted(tools):
                require(re.fullmatch(r"[a-zA-Z0-9_.+-]+", exposed), "catalog has an invalid command name")
                location = Path(command("locate-" + exposed, ["/bin/sh", "-c", "command -v " + exposed], env=managed).strip())
                require(location.is_relative_to(args.home) and location.is_file() and os.access(location, os.X_OK),
                        f"command is not owned by the validation home: {exposed}")
                output = command("version-" + exposed, [location, "version" if exposed == "git-lfs" else "--version"], env=managed)
                if exposed in pins:
                    require(first_line_version_matches(output, pins[exposed]),
                            f"command differs from its catalog version: {exposed}")
                versions[exposed] = output.strip().splitlines()[0]
            report["versions"] = versions
            report.setdefault("managed_snapshot", snapshot(args.home, plan))
            return {"commands": len(versions), "installed_environments": len(installed)}
        check("regular managed files, installed pins, and executable commands", pinned_commands)

        def installed_skills(stage):
            destination = args.artifacts / ("installed-skills-" + stage)
            summary = None
            try:
                command("installed-skills-" + stage,
                        [args.home / ".pixi/envs/python/bin/python", SOURCE / "tests/installed_skill_discovery.py",
                         "--home", args.home, "--artifacts", destination], env=managed, timeout=300)
            finally:
                if (destination / "report.json").is_file():
                    summary = json.loads((destination / "report.json").read_text())
                    report.setdefault("installed_skill_discovery", {})[stage] = summary
            require(summary is not None and summary["status"] == "passed",
                    "installed selected skill discovery did not pass")
            return {"selected_skills": summary["selected_count"], "clients": len(summary["clients"])}
        check("actual fetched default skill discovery after fresh installation", lambda: installed_skills("fresh"))

        def reapplication():
            originals = seed_device(args.home)
            history_env = dict(managed)
            history_env["ATUIN_SESSION"] = command("history-uuid", [args.home / ".pixi/bin/atuin", "uuid"], env=managed).strip()
            token = "printf synthetic-linux-preserved-history"
            record = command("history-start", [args.home / ".pixi/bin/atuin", "history", "start", "--", token], env=history_env).strip()
            command("history-end", [args.home / ".pixi/bin/atuin", "history", "end", "--exit", "0", record], env=history_env)
            before = snapshot(args.home, plan)
            metadata_before = trampoline_metadata(args.home, plan)
            report["trampoline_metadata"] = {"before": metadata_before}
            command("bootstrap-reapply", full, timeout=args.install_timeout)
            check_preservation(args.home, originals)
            after = snapshot(args.home, plan)
            metadata_after = trampoline_metadata(args.home, plan)
            # Activation env/path_diff depend on the installer's current PATH.
            # Preserve their full values as evidence; runtime checks establish
            # the resulting behavior instead of requiring generated identity.
            metadata_changed = sorted(path for path in metadata_before.keys() | metadata_after.keys()
                                      if metadata_before.get(path) != metadata_after.get(path))
            report["trampoline_metadata"].update(after=metadata_after, changed=metadata_changed)
            changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
            require(not changed, "managed reapplication changed files: " + ", ".join(changed[:20]))
            require("synthetic-linux-preserved-history" in command("history-preserved", [args.home / ".pixi/bin/atuin", "search", "--cmd-only", "synthetic-linux-preserved-history"], env=history_env),
                    "reapplication lost synthetic command history")
            command("device-package", [args.home / ".pixi/bin/device-zoxide", "--version"], env=managed)
            require("synthetic-device-extra" in command("device-bun", [args.home / ".bun/bin/device-extra"], env=managed),
                    "reapplication lost the unrelated Bun launcher")
            require("pending activation" in command("history-status", [args.home / ".local/bin/dotfiles-history", "status"], env=managed).lower(),
                    "ordinary bootstrap activated history sync")
            require(not (SOURCE / ".codegraph").exists() and not (args.home / ".codegraph").exists(),
                    "ordinary deployment indexed a source or device home")
            report["reapplication_snapshot"] = after
            return {"synthetic_auth": "preserved", "settings": "preserved", "history": "preserved",
                    "pixi_and_bun_inventory": "preserved", "managed_files": "stable", "sync": "pending activation",
                    "generated_metadata_changed": len(metadata_changed)}
        check("full default reapplication and synthetic device preservation", reapplication)
        check("installed inventory, exact pins, and executable commands after reapplication", pinned_commands)
        check("actual fetched default skill discovery after reapplication", lambda: installed_skills("reapplied"))

        test_env = dict(managed, DOTFILES_TEST_PLATFORM="linux", DOTFILES_TEST_ROLE="remote-compute",
                        DOTFILES_TEST_CHEZMOI=str(args.home / ".local/bin/chezmoi"), DOTFILES_TEST_TOOL_HOME=str(args.home),
                        DOTFILES_TEST_NODE=str(args.home / ".pixi/bin/node"), DOTFILES_TEST_NU=str(args.home / ".pixi/bin/nu"),
                        DOTFILES_TEST_BASH=str(args.home / ".pixi/bin/bash"), DOTFILES_TEST_ZSH=str(args.home / ".pixi/bin/zsh"),
                        DOTFILES_TEST_MAMBA=str(args.home / ".pixi/bin/micromamba"),
                        DOTFILES_TEST_ATUIN=str(args.home / ".pixi/envs/atuin/bin/atuin"),
                        DOTFILES_TEST_PYTHON=str(args.home / ".pixi/envs/python/bin/python"),
                        DOTFILES_TEST_PI_MODULE=str(args.home / ".bun/managed/pi/node_modules/@earendil-works/pi-coding-agent/dist/index.js"))
        for name in ("codegraph", "codex", "claude", "kimi", "opencode"):
            test_env["DOTFILES_TEST_" + name.upper()] = str(args.home / ".local/bin" / name)
        for key, value in test_env.items():
            if key.startswith("DOTFILES_TEST_") and key not in {"DOTFILES_TEST_PLATFORM", "DOTFILES_TEST_ROLE", "DOTFILES_TEST_TOOL_HOME"}:
                require(Path(value).is_file(), f"required installed test prerequisite missing: {key}")
        python = args.home / ".pixi/envs/python/bin/python"
        for pattern in (*REQUIRED_SUITES, "test*.py"):
            def behavior(pattern=pattern):
                destination = args.artifacts / (pattern.replace("*", "-deterministic") + ".json")
                suite_python, suite_env = python, test_env
                if pattern == "test*.py":
                    control_home = args.artifacts / "deterministic-home"
                    control_home.mkdir()
                    suite_env = deterministic_environment(control_home, temporary, test_env)
                    # Fixture executables embed sys.executable in a shebang;
                    # the deployed home deliberately contains spaces, so keep
                    # that runtime proof in the five required suites above.
                    suite_python = Path(sys.executable)
                    report["deterministic_context"] = {
                        "python": str(suite_python), "home": str(control_home), "path": suite_env["PATH"],
                        "borrowed_prerequisites": sorted(name for name in suite_env if name.startswith("DOTFILES_TEST_"))}
                arguments = [suite_python, SOURCE / "tests/native_linux.py", "--run-suite", pattern, destination]
                if pattern == "test*.py":
                    arguments.append("--exclude-required")
                summary = None
                try:
                    command(pattern.replace("*", "-deterministic"), arguments, env=suite_env, timeout=args.suite_timeout)
                finally:
                    if destination.exists():
                        summary = json.loads(destination.read_text())
                        report["suites"].append(summary)
                require(summary is not None, "suite did not produce its structured result")
                audited = audit_suite(summary)
                report["suites"][-1] = audited
                return {"tests_run": audited["tests_run"], "classified_skips": len(audited["skipped"]), "unexpected_skips": 0}
            label = "remaining deterministic acceptance" if pattern == "test*.py" else "actual installed runtime: " + pattern
            check(label, behavior)
        check("source remains unchanged", lambda: require(source_identity() == report["source"], "source changed during acceptance"))
        report["status"] = "passed"
        report["unexpected_required_skips"] = 0
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report["status"] = "failed"
        report["reason"] = str(error)
        print(f"linux acceptance failed: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        report["resources_after"] = resource_snapshot()
        report["cpu_stat_delta"] = {name: value - report["resources_before"]["cpu_stat"].get(name, value)
                                    for name, value in report["resources_after"]["cpu_stat"].items()}
        report["seconds"] = round(time.monotonic() - started, 3)
        write_json(report_path, report)


if __name__ == "__main__":
    sys.exit(main())
