"""Checks for the Herdr-scoped Codex launcher and session hook."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
WRAPPER = SOURCE / "dot_local/bin/executable_codex-herdr"
HEALTH = SOURCE / "dot_local/bin/executable_dotfiles-agent-health"
HOOK = SOURCE / "dot_codex/executable_herdr-codex-resume.sh"
INSTALLER = SOURCE / "dot_local/bin/executable_dotfiles-codex-herdr"


@unittest.skipUnless(os.name == "posix", "Unix shell startup; Windows has a native adapter suite")
class ShellCodexRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-codex-shell-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "device with spaces"
        self.bin = self.home / "bin"
        self.bin.mkdir(parents=True)
        self.local = self.home / ".config/dotfiles"
        self.local.mkdir(parents=True)
        self.env = {
            "HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin",
            "TERM": "xterm-256color", "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
        }
        (self.home / ".env_core").write_text(
            'export MAMBA_EXE="$HOME/missing-mamba"\n'
            'export DOTFILES_COMMON_BIN="$HOME/missing-bin"\n', encoding="utf-8")
        for command in ("codex", "codex-herdr"):
            executable = self.bin / command
            executable.write_text(
                f'#!/bin/sh\nprintf "%s\\n" {command} "$@"\n', encoding="utf-8")
            executable.chmod(0o755)

    def shell(self, name, *, herdr=None, native_copy=False):
        executable = os.environ.get(f"DOTFILES_TEST_{name.upper()}") or shutil.which(name)
        if not executable:
            self.skipTest(f"{name} is not installed")
        command = 'codex --version "path with spaces"'
        if name == "nu":
            # Native adapters copy the complete adjacent resource directory to
            # their discovery location; no resource may assume .config/nushell.
            config = self.home / ("native/nushell" if native_copy else ".config/nushell")
            config.mkdir(parents=True, exist_ok=True)
            for resource in (SOURCE / "dot_config/nushell").glob("*.nu"):
                shutil.copyfile(resource, config / resource.name)
            (config / "proxy.nu").write_text("# No proxy needed in this routing fixture.\n")
            arguments = [executable, "--env-config", "/dev/null", "--config", str(config / "config.nu"),
                         "-c", command]
        elif name == "bash":
            arguments = [executable, "--noprofile", "--norc", "-ic",
                         f'. {json.dumps(str(SOURCE / "dot_bashrc"))}; {command}']
        else:
            arguments = [executable, "-f", "-ic",
                         f'. "$HOME/.env_core"; . {json.dumps(str(SOURCE / "dot_zshrc"))}; {command}']
        env = dict(self.env)
        if herdr is not None:
            env["HERDR_ENV"] = herdr
        return subprocess.run(arguments, env=env, cwd=self.home,
                              capture_output=True, text=True, timeout=20)

    def test_managed_codex_routes_only_herdr_panes_and_forwards_arguments(self):
        for name in ("bash", "zsh", "nu"):
            for herdr in (None, "0", "1"):
                with self.subTest(shell=name, herdr=herdr):
                    result = self.shell(name, herdr=herdr)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines(),
                                     ["codex-herdr" if herdr == "1" else "codex",
                                      "--version", "path with spaces"])

    def test_device_local_codex_overrides_managed_command_in_every_shell(self):
        for name in ("bash.local.sh", "zsh.local.zsh"):
            (self.local / name).write_text(
                'codex() { printf "%s\\n" device-local-codex "$@"; }\n', encoding="utf-8")
        (self.local / "nu.local.nu").write_text(
            'def --wrapped codex [...args] { print device-local-codex ...$args }\n', encoding="utf-8")
        for name in ("bash", "zsh", "nu"):
            for herdr in (None, "1"):
                with self.subTest(shell=name, herdr=herdr):
                    result = self.shell(name, herdr=herdr)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines(),
                                     ["device-local-codex", "--version", "path with spaces"])

    def test_native_nu_resource_copy_keeps_local_command_precedence(self):
        (self.local / "nu.local.nu").write_text(
            'def --wrapped codex [...args] { print device-local-codex ...$args }\n', encoding="utf-8")
        result = self.shell("nu", herdr="1", native_copy=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ["device-local-codex", "--version", "path with spaces"])


class AgentHerdrTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.health = self.bin / "dotfiles-agent-health"
        self.health.write_text("#!/bin/sh\nexit ${HEALTH_EXIT:-0}\n", encoding="utf-8")
        self.health.chmod(0o755)
        self.args = self.root / "args.txt"
        self.with_proxy = self.bin / "with-proxy"
        self.with_proxy.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_FILE"\n', encoding="utf-8")
        self.with_proxy.chmod(0o755)
        self.herdr = self.bin / "herdr"
        self.herdr.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.herdr.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update(
            HOME=str(self.root / "home"),
            PATH=f"{self.bin}:/usr/bin:/bin",
            DOTFILES_AGENT_HEALTH=str(self.health),
            DOTFILES_WITH_PROXY=str(self.with_proxy),
            ARGS_FILE=str(self.args),
        )

    def run_wrapper(self):
        return subprocess.run(
            ["/bin/bash", str(WRAPPER), "--version"],
            env=self.env,
            cwd=SOURCE,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_wrapper_runs_codex_with_proxy_and_no_daemon(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.args.read_text(encoding="utf-8").splitlines(),
                         ["codex", "--no-daemon", "--version"])

    def test_wrapper_refuses_when_health_fails(self):
        self.env["HEALTH_EXIT"] = "1"
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unhealthy", result.stderr)
        self.assertFalse(self.args.exists())

    def test_hook_dry_run_reports_unknown_state_with_resume_wrapper(self):
        result = subprocess.run(
            ["/bin/bash", str(HOOK), "--dry-run"],
            env=dict(self.env, HERDR_ENV="1", HERDR_SOCKET_PATH="/tmp/herdr.sock",
                     HERDR_PANE_ID="wTest:p1"),
            input='{"hook_event_name":"SessionStart","session_id":"test-123","source":"startup"}\n',
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout
        self.assertIn("report-agent wTest:p1", output)
        self.assertIn("--state unknown", output)
        self.assertIn("--seq ", output)
        self.assertIn("--session-start-source startup", output)
        self.assertIn("codex-herdr resume test-123", output)
        self.assertEqual(len(output.strip().splitlines()), 2)

    def test_herdr_config_is_valid(self):
        herdr = shutil.which("herdr")
        if not herdr:
            self.skipTest("herdr is not installed")
        home = self.root / "herdr-home"
        config = home / ".config/herdr/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text((SOURCE / "dot_config/herdr/config.toml").read_text(encoding="utf-8"),
                          encoding="utf-8")
        result = subprocess.run(
            [herdr, "config", "check"],
            env=dict(self.env, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config")),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hook_installer_is_idempotent_and_preserves_other_hooks(self):
        hooks = self.root / "hooks.json"
        hooks.write_text(
            '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"bash /managed/hook"}]}],'
            '"Stop":[{"hooks":[{"type":"command","command":"stop"}]}]}}\n',
            encoding="utf-8",
        )
        env = dict(self.env, DOTFILES_CODEX_HOOKS=str(hooks))
        for _ in range(2):
            result = subprocess.run(
                ["/bin/bash", str(INSTALLER), "install"],
                env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(hooks.read_text(encoding="utf-8"))
        session = data["hooks"]["SessionStart"]
        self.assertEqual(len(session), 2)
        commands = [item["hooks"][0]["command"] for item in session]
        self.assertEqual(commands[0], "bash /managed/hook")
        self.assertIn("herdr-codex-resume.sh", commands[1])
        self.assertEqual(data["hooks"]["Stop"][0]["hooks"][0]["command"], "stop")
        status = subprocess.run(
            ["/bin/bash", str(INSTALLER), "status"],
            env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(status.returncode, 0, status.stderr)

    def test_scripts_parse_and_shell_configs_route_herdr_codex(self):
        for script in (WRAPPER, HEALTH, HOOK, INSTALLER):
            result = subprocess.run(["/bin/bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")
        for relative in ("dot_bashrc", "dot_zshrc", "dot_config/nushell/config.nu"):
            text = (SOURCE / relative).read_text(encoding="utf-8")
            self.assertIn("codex-herdr", text, relative)
            self.assertIn("HERDR_ENV", text, relative)


if __name__ == "__main__":
    unittest.main()
