"""Observable shell behavior in separately writable simulated homes.

DOTFILES_TEST_TOOL_HOME may borrow read-only, pinned common executables from an
isolated installation. Fixture links expose only those declared tools; this
suite does not claim to install them. Full deployment ownership is checked by
test_common_install and the final native matrix.
"""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time
import unittest

if os.name == "posix":
    import fcntl
    import pty
    import termios

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Unix shell execution; native Windows has a separate adapter suite")
class ShellBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-shell-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "device"
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color",
                    "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library")}
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        self.tool_home = Path(os.environ["DOTFILES_TEST_TOOL_HOME"]) if os.environ.get("DOTFILES_TEST_TOOL_HOME") else None
        if not self.chezmoi or not self.tool_home:
            self.skipTest("shell execution requires chezmoi and DOTFILES_TEST_TOOL_HOME with pinned tools")
        self.binaries = {}
        for command, environment in {
            "bash": "bash", "zsh": "zsh", "nu": "nushell", "zoxide": "zoxide",
            "tspin": "tailspin", "less": "less", "rtk": "rtk-cli", "micromamba": "micromamba",
            "starship": "starship", "direnv": "direnv", "fzf": "fzf", "vivid": "vivid",
        }.items():
            binary = self.tool_home / ".pixi/envs" / environment / "bin" / command
            if not binary.is_file():
                self.skipTest(f"missing borrowed pinned tool: {binary}")
            self.binaries[command] = str(binary)
            target = self.home / ".pixi/bin" / command
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(binary)
        (self.home / ".bun/bin").mkdir(parents=True)
        (self.home / ".cargo/bin").mkdir(parents=True)
        pixi = self.tool_home / ".pixi/bin/pixi"
        if not pixi.is_file():
            self.skipTest("borrowed install lacks its pinned Pixi manager")
        launcher = self.home / ".pixi/bin/pixi"
        launcher.write_text('#!/bin/sh\nexec "' + str(pixi) + '" "$@"\n')
        launcher.chmod(0o755)
        self.bash_version = subprocess.check_output(
            [self.binaries['bash'], '--noprofile', '--norc', '-c', 'printf "%s" "$BASH_VERSION"'],
            env=self.env, text=True, timeout=10)

    def deploy(self, role=None, *, overrides=None):
        role = role or os.environ.get("DOTFILES_TEST_ROLE", "workstation")
        result = subprocess.run([
            "bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
            "--home", str(self.home), "--platform", os.environ.get("DOTFILES_TEST_PLATFORM", "linux"),
            "--role", role, "--apply-only",
        ], env=dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi, **(overrides or {})), cwd=SOURCE,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def shell(self, name, script, *, overrides=None, interactive=False):
        env = dict(self.env, XDG_CONFIG_HOME=str(self.home / ".config"),
                   XDG_DATA_HOME=str(self.home / ".local/share"),
                   XDG_STATE_HOME=str(self.home / ".local/state"),
                   XDG_CACHE_HOME=str(self.home / ".cache"),
                   HISTFILE=str(self.home / ".bash_history"), **(overrides or {}))
        if name == "nu":
            arguments = [self.binaries[name], "--config", str(self.home / ".config/nushell/config.nu"),
                         "--env-config", str(self.home / ".config/nushell/env.nu"), "-c", script]
        else:
            arguments = [self.binaries[name], *( ["-i"] if interactive else [] ), "-c", script]
        return subprocess.run(arguments, env=env, cwd=self.home, capture_output=True, text=True, timeout=20)

    def environment(self, name, *, overrides=None):
        names = ["EDITOR", "UV_PYTHON_PREFERENCE", "PIP_INDEX_URL", "UV_DEFAULT_INDEX",
                 "RUSTUP_DIST_SERVER", "RUSTUP_UPDATE_ROOT", "CHOKIDAR_USEPOLLING", "MAMBA_EXE",
                 "JOEY", "GIZMO", "JSHELL"]
        if name == "nu":
            script = "$env | select " + " ".join(names) + " PATH | to json --raw"
        else:
            script = '. "$HOME/.env_core"; . "$HOME/.env_core"; '
            script += "printf '%s\\n' " + " ".join(f'"${{{name}}}"' for name in names) + ' "$PATH"'
        result = self.shell(name, script, overrides=overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), "")
        if name == "nu":
            return json.loads(result.stdout)
        values = result.stdout.splitlines()
        self.assertEqual(len(values), len(names) + 1, result.stdout)
        return dict(zip([*names, "PATH"], [*values[:-1], values[-1].split(":")]))

    def test_fresh_shells_share_managed_paths_and_role_defaults(self):
        for role, polling in (("workstation", "0"), ("remote-compute", "1")):
            self.deploy(role)
            for name in ("bash", "zsh", "nu"):
                with self.subTest(role=role, shell=name):
                    actual = self.environment(name)
                    self.assertEqual(actual["EDITOR"], "hx")
                    self.assertEqual(actual["UV_PYTHON_PREFERENCE"], "managed")
                    self.assertEqual(actual["PIP_INDEX_URL"], "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
                    self.assertEqual(actual["UV_DEFAULT_INDEX"], "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
                    self.assertEqual(actual["RUSTUP_DIST_SERVER"], "https://mirrors.tuna.tsinghua.edu.cn/rustup")
                    self.assertEqual(actual["RUSTUP_UPDATE_ROOT"], "https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup")
                    self.assertEqual(actual["CHOKIDAR_USEPOLLING"], polling)
                    self.assertEqual(actual["MAMBA_EXE"], str(self.home / ".pixi/bin/micromamba"))
                    self.assertEqual(actual["JOEY"], str(self.home / "joey"))
                    expected_paths = [str(self.home / path) for path in (".bun/bin", ".local/bin", ".pixi/bin", ".cargo/bin")]
                    self.assertEqual(actual["PATH"][:4], expected_paths)
                    self.assertEqual(len(actual["PATH"]), len(set(actual["PATH"])))
                    self.assertNotIn(actual["GIZMO"], actual["PATH"])

    def test_shared_overrides_survive_each_shell_and_repeated_initialization(self):
        self.deploy("remote-compute")
        overrides = {
            "EDITOR": "device-editor", "UV_PYTHON_PREFERENCE": "system",
            "PIP_INDEX_URL": "https://device.example/simple", "UV_DEFAULT_INDEX": "https://uv.example/simple",
            "RUSTUP_DIST_SERVER": "https://rust.example/dist", "RUSTUP_UPDATE_ROOT": "https://rust.example/update",
            "CHOKIDAR_USEPOLLING": "0", "MAMBA_EXE": "/device/managed-micromamba",
            "JOEY": str(self.home / "custom-legacy-root"),
        }
        for name in ("bash", "zsh", "nu"):
            with self.subTest(shell=name):
                actual = self.environment(name, overrides=overrides)
                self.assertEqual({key: actual[key] for key in overrides}, overrides)
                if name == "nu":
                    script = 'source "' + str(self.home / ".config/nushell/env.nu") + '"; $env.PATH | to json --raw'
                    result = self.shell(name, script, overrides=overrides)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), actual["PATH"])

    def test_proxy_helpers_agree_and_unset_all_variants(self):
        proxy = 'http://127.0.0.1:17777/?quoted=\'"value\\path'
        self.deploy(overrides={"HTTP_PROXY_URL": proxy})
        for name in ("bash", "zsh", "nu"):
            with self.subTest(shell=name):
                if name == "nu":
                    script = 'noproxy; print ([$env.http_proxy $env.https_proxy $env.HTTP_PROXY $env.HTTPS_PROXY] | to json --raw); unproxy; $env | columns | where {|name| $name in [http_proxy https_proxy HTTP_PROXY HTTPS_PROXY] } | to json --raw'
                else:
                    script = '. "$HOME/.env_core"; noproxy; printf "%s\\n" "$http_proxy" "$https_proxy" "$HTTP_PROXY" "$HTTPS_PROXY"; unproxy; printf "%s\\n" "${http_proxy+set}${https_proxy+set}${HTTP_PROXY+set}${HTTPS_PROXY+set}"'
                result = self.shell(name, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = result.stdout.splitlines()
                if name == "nu":
                    self.assertEqual(json.loads(lines[0]), [proxy] * 4)
                    self.assertEqual(json.loads(lines[1]), [])
                else:
                    self.assertEqual(lines, [proxy] * 4 + [""])

    def test_zoxide_navigation_and_tailspin_logs_work_in_each_shell(self):
        self.deploy()
        destination = self.home / "navigation-unique-token"
        destination.mkdir()
        logfile = self.home / "application.log"
        logfile.write_text("2026-10-13 ERROR portable-log-token count=42\n")
        for name in ("bash", "zsh", "nu"):
            with self.subTest(shell=name):
                if name == "nu":
                    script = '^zoxide add navigation-unique-token; z navigation-unique-token; print $env.PWD; logs --print ../application.log; ^rtk --version'
                else:
                    script = 'zoxide add navigation-unique-token; z navigation-unique-token; pwd; logs --print ../application.log; rtk --version'
                result = self.shell(name, script, interactive=name != "nu")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(str(destination), result.stdout)
                self.assertIn("portable-log-token", result.stdout)
                self.assertIn("rtk", result.stdout.lower())

    def test_launcher_keeps_scripts_and_agent_subprocesses_in_bash(self):
        self.deploy()
        launcher = self.home / ".local/bin/nu-login"
        for overrides in ({}, {"CLAUDECODE": "1"}, {"ANTHROPIC_AUTH_TOKEN": "synthetic-session-marker"}):
            with self.subTest(overrides=overrides):
                result = subprocess.run([str(launcher), "-c", 'printf "SECONDARY-%s\\n" "$BASH_VERSION"'],
                                        env=dict(self.env, **overrides), cwd=self.home,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'SECONDARY-' + self.bash_version)

    def terminal(self, arguments, command, *, overrides=None):
        primary, secondary = pty.openpty()
        env = dict(self.env, XDG_CONFIG_HOME=str(self.home / ".config"),
                   XDG_DATA_HOME=str(self.home / ".local/share"),
                   XDG_STATE_HOME=str(self.home / ".local/state"),
                   XDG_CACHE_HOME=str(self.home / ".cache"), **(overrides or {}))
        def terminal_session():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        process = subprocess.Popen(arguments, env=env, cwd=self.home, stdin=secondary,
                                   stdout=secondary, stderr=secondary, preexec_fn=terminal_session)
        os.close(secondary)
        output = bytearray()
        try:
            time.sleep(0.3)
            if command:
                os.write(primary, command.encode())
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                readable, _, _ = select.select([primary], [], [], 0.1)
                if readable:
                    try:
                        output.extend(os.read(primary, 65536))
                    except OSError:
                        break
                elif process.poll() is not None:
                    break
            self.assertIsNotNone(process.poll(), output.decode(errors="replace"))
            self.assertEqual(process.returncode, 0, output.decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            os.close(primary)
        return output.decode(errors="replace")

    def test_launcher_prefers_nu_on_a_terminal_and_honors_secondary_shell_guard(self):
        self.deploy()
        launcher = str(self.home / ".local/bin/nu-login")
        output = self.terminal([launcher], 'print (["PREFERRED" "NU"] | str join "-"); exit\n')
        self.assertIn("PREFERRED-NU", output)
        for overrides in ({"CLAUDECODE": "1"}, {"DOTFILES_SECONDARY_SHELL": "1"}):
            output = self.terminal([launcher], 'printf "SECONDARY-%s\\n" "$BASH_VERSION"; exit\n', overrides=overrides)
            self.assertIn('SECONDARY-' + self.bash_version, output)

    def test_logs_uses_the_default_less_pager(self):
        self.deploy()
        logfile = self.home / "application.log"
        logfile.write_text("ERROR pager-log-token count=42\n")
        pager = self.home / ".local/bin/less"
        pager.write_text('#!/bin/sh\nprintf "PAGER-REACHED\\n" >&2\nexec "' + self.binaries["less"] + '" -F -X "$@"\n')
        pager.chmod(0o755)
        for name in ("bash", "zsh", "nu"):
            with self.subTest(shell=name):
                arguments = [self.binaries[name], "--config", str(self.home / ".config/nushell/config.nu"), "--env-config", str(self.home / ".config/nushell/env.nu"), "-c", "logs application.log"] if name == "nu" else [self.binaries[name], "-c", '. "$HOME/.env_core"; logs application.log']
                output = self.terminal(arguments, "")
                self.assertIn("PAGER-REACHED", output)
                self.assertIn("pager-log-token", output)

    def test_prepared_nu_startup_loads_prompt_and_completions_without_a_checkout(self):
        self.deploy()
        command = [str(self.home / ".local/bin/dotfiles-shell-prepare")]
        before = None
        for _ in range(2):
            result = subprocess.run(command, env=self.env, cwd=self.home, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Vendor autoload is an interactive boundary; normal -c execution
            # intentionally omits it in Nu. Start without explicit config flags
            # to verify ordinary Linux discovery and the actual autoload path.
            output = self.terminal([self.binaries["nu"]], 'print $"PREPARED-($env.STARSHIP_SHELL?)"; print $"COMPLETIONS-((scope commands | where name == "pixi" | length))"; exit\n')
            self.assertIn("PREPARED-nu", output)
            self.assertIn("COMPLETIONS-1", output)
            artifacts = {path.name: path.read_bytes() for path in (self.home / ".local/share/nushell/vendor/autoload").glob("*.nu")}
            if before is not None:
                self.assertEqual(artifacts, before)
            before = artifacts
        self.assertFalse((self.home / ".config/nushell/nu_scripts").exists())

    def test_invalid_generated_resource_preserves_the_last_working_startup(self):
        self.deploy()
        command = [str(self.home / ".local/bin/dotfiles-shell-prepare")]
        prepared = subprocess.run(command, env=self.env, cwd=self.home, capture_output=True, text=True, timeout=20)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        directory = self.home / ".local/share/nushell/vendor/autoload"
        before = {path.name: path.read_bytes() for path in directory.glob("*.nu")}
        pixi = self.home / ".pixi/bin/pixi"
        pixi.write_text('#!/bin/sh\nprintf "def broken [\\n"\n')
        result = subprocess.run(command, env=self.env, cwd=self.home, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual({path.name: path.read_bytes() for path in directory.glob("*.nu")}, before)

    def test_applied_shells_start_before_tool_installation_without_external_resources(self):
        self.deploy()
        for path in (self.home / ".pixi/bin").iterdir():
            path.unlink()
        for name in ("bash", "zsh", "nu"):
            with self.subTest(shell=name):
                script = 'print "standalone-ok"' if name == "nu" else '. "$HOME/.bashrc"; printf "standalone-ok\\n"' if name == "bash" else 'printf "standalone-ok\\n"'
                result = self.shell(name, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "standalone-ok")
                self.assertEqual(result.stderr.strip(), "")


if __name__ == "__main__":
    unittest.main()
