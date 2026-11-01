"""Checks for the Herdr-scoped Codex launcher and session hook."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
WRAPPER = SOURCE / "dot_local/bin/executable_codex-herdr"
HEALTH = SOURCE / "dot_local/bin/executable_dotfiles-agent-health"
HOOK = SOURCE / "dot_codex/executable_herdr-codex-resume.sh"
INSTALLER = SOURCE / "dot_local/bin/executable_dotfiles-codex-herdr"


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
