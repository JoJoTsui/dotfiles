"""The Herdr-scoped Codex routes: a restore keeps the thread's own settings.

The seams are the public commands a Herdr pane runs: the Herdr-scoped
launcher, and the hook commands that register, report, and remove the
managed entry. Both are exercised in a disposable home, so nothing here
reads the device's own Codex state.

The launcher has two routes and they stay distinct. A fresh launch keeps the
plain route. A restore resumes a thread that saved its own provider, model,
and reasoning effort, so it goes through the managed resume command, which
carries provider definitions and never a selection.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    from .test_codex_resume import FAKE_CODEX, PROFILE
except ImportError:  # pragma: no cover - direct module execution
    from test_codex_resume import FAKE_CODEX, PROFILE

SOURCE = Path(__file__).resolve().parents[1]
LAUNCHER = SOURCE / "dot_local/bin/executable_codex-herdr"
RESUME = SOURCE / "dot_local/bin/executable_dotfiles-codex-resume"
HOOKS = SOURCE / "dot_local/bin/executable_dotfiles-codex-herdr"

SESSION = "0199abcd-session"
MAGPIE_TOKEN = "placeholder-gateway-token"
MANAGED_COMMAND = 'bash "$HOME/.codex/herdr-codex-resume.sh"'

# A device hook file with a mixed SessionStart group: the device command
# stands beside the managed one, the group carries its own metadata, Herdr
# owns the next group, and another event carries a device command of its own.
MIXED_HOOKS = {
    "hooks": {
        "SessionStart": [
            {
                "matcher": "startup",
                "hooks": [
                    {"type": "command", "command": "device-hook", "timeout": 30},
                    {"type": "command", "command": MANAGED_COMMAND, "timeout": 5},
                ],
            },
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'bash "$HOME/.codex/herdr-agent-state.sh"',
                        "timeout": 5,
                    },
                ],
            },
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "device-stop"}]}],
    },
}


class DisposableHome:
    """A disposable home with the managed commands a Herdr pane runs."""

    def build(self, root):
        self.root = root
        self.home = root / "home"
        self.bin = root / "bin"
        self.bin.mkdir(parents=True)
        self.local = self.home / ".local/bin"
        self.local.mkdir(parents=True)
        self.codex_home = self.home / ".codex"
        self.codex_home.mkdir(parents=True)

        # The health gate and the proxy gate stand in for the managed ones.
        health = self.local / "dotfiles-agent-health"
        health.write_text("#!/bin/sh\nexit ${HEALTH_EXIT:-0}\n", encoding="utf-8")
        health.chmod(0o755)
        self.proxy_record = root / "proxy-args.txt"
        proxy = self.local / "with-proxy"
        proxy.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$@" > "$PROXY_ARGS"\n'
            'if [ "$1" = "--if-available" ]; then shift; fi\n'
            'exec "$@"\n',
            encoding="utf-8",
        )
        proxy.chmod(0o755)

        # The managed resume command is the one the launcher reaches for, at
        # the path the launcher resolves by default.
        shutil.copyfile(RESUME, self.local / "dotfiles-codex-resume")
        (self.local / "dotfiles-codex-resume").chmod(0o755)

        # A fake Codex records the argv and the environment it was given.
        self.record = root / "codex-record.json"
        codex = self.bin / "codex"
        codex.write_text(FAKE_CODEX, encoding="utf-8")
        codex.chmod(0o755)
        (self.bin / "python3").symlink_to(sys.executable)

        self.env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "FAKE_CODEX_RECORD": str(self.record),
            "PROXY_ARGS": str(self.proxy_record),
            # The managed interpreter is resolved the way the deployment
            # resolves it, so the interpreter of this run stands in for it.
            "PIXI_HOME": str(root / "no-pixi"),
        }

    def write_profile(self):
        (self.codex_home / "magpie.config.toml").write_text(
            PROFILE.format(token=MAGPIE_TOKEN), encoding="utf-8")

    def proxy_args(self):
        if not self.proxy_record.exists():
            return []
        return self.proxy_record.read_text(encoding="utf-8").splitlines()

    def recorded(self):
        self.assertTrue(self.record.exists(), "the fake codex was never run")
        return json.loads(self.record.read_text(encoding="utf-8"))

    def overrides(self, payload=None):
        payload = payload or self.recorded()
        argv = payload["argv"]
        values = []
        for index, item in enumerate(argv):
            if item in ("-c", "--config"):
                values.append(argv[index + 1])
            elif item.startswith("--config="):
                values.append(item.split("=", 1)[1])
        return values


class HerdrRestoreRouteTests(unittest.TestCase, DisposableHome):
    """The Herdr-scoped launcher keeps the fresh route and repairs the restore."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-restore-")
        self.addCleanup(temporary.cleanup)
        self.build(Path(temporary.name))

    def run_launcher(self, *args, env=None):
        environment = dict(self.env)
        if env:
            environment.update(env)
        return subprocess.run(["/bin/bash", str(LAUNCHER), *args], env=environment,
                              capture_output=True, text=True, timeout=60)

    def test_a_fresh_launch_keeps_its_existing_route(self):
        result = self.run_launcher("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.proxy_args(),
                         ["--if-available", "codex", "--no-daemon", "--version"])

    def test_a_restore_routes_through_the_provider_preserving_resume(self):
        result = self.run_launcher("resume", SESSION)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.proxy_args(),
            ["--if-available", str(self.local / "dotfiles-codex-resume"),
             "--no-daemon", SESSION],
        )

    def test_a_restore_keeps_the_saved_provider_model_and_effort(self):
        # The managed command adds provider definitions and never a
        # selection, so Codex restores the settings the thread saved.
        self.write_profile()
        result = self.run_launcher("resume", SESSION)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.recorded()
        values = self.overrides(payload)
        selected = [
            value for value in values
            if value.split("=", 1)[0] in {"model", "model_provider", "model_reasoning_effort"}
        ]
        self.assertEqual(selected, [], "the restore selected a model, a provider, or an effort")
        self.assertIn('model_providers.magpie.base_url="http://127.0.0.1:39411/v1"', values)
        # The credential reaches the child through the environment only.
        self.assertNotIn(MAGPIE_TOKEN, " ".join(payload["argv"]))
        self.assertEqual(payload["env"]["DOTFILES_CODEX_RESUME_MAGPIE_TOKEN"], MAGPIE_TOKEN)

    def test_a_restore_leaves_the_provider_the_device_defines_alone(self):
        # The device's own provider is a supported path of its own: the
        # restore must not override it and must not select it.
        (self.codex_home / "config.toml").write_text(
            '[model_providers.alpha]\nname = "alpha"\n'
            'base_url = "http://127.0.0.1:39555/v1"\nwire_api = "responses"\n',
            encoding="utf-8",
        )
        self.write_profile()
        result = self.run_launcher("resume", SESSION)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.overrides()
        self.assertEqual([value for value in values if value.startswith("model_providers.alpha.")],
                         [], "the restore overrode the provider the device defines")

    def test_a_restore_without_a_gateway_or_a_device_provider_keeps_the_plain_route(self):
        # The plain subscription is a supported path of its own: the restore
        # adds no provider definition, so the thread keeps the provider the
        # device subscribes to.
        result = self.run_launcher("resume", SESSION)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.overrides(), [],
                         "the restore added a provider definition of its own")
        self.assertIn(SESSION, self.recorded()["argv"])

    def test_a_restore_runs_the_resume_without_the_shared_server(self):
        # The pane keeps its own app server, so the hooks of the resumed
        # thread report to the pane that resumed them.
        self.write_profile()
        result = self.run_launcher("resume", SESSION)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.recorded()["argv"]
        self.assertIn("--no-daemon", argv)
        self.assertEqual(argv[:3], ["resume", "--all", "--include-non-interactive"])
        self.assertIn(SESSION, argv)

    def test_an_unhealthy_stack_refuses_the_restore(self):
        result = self.run_launcher("resume", SESSION, env={"HEALTH_EXIT": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unhealthy", result.stderr)
        self.assertEqual(self.proxy_args(), [], "the refused restore reached the proxy gate")

    def test_a_missing_resume_command_is_reported(self):
        (self.local / "dotfiles-codex-resume").unlink()
        result = self.run_launcher("resume", SESSION)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dotfiles-codex-resume", result.stderr)
        self.assertEqual(self.proxy_args(), [], "the refused restore reached the proxy gate")


class HerdrHookCommandTests(unittest.TestCase):
    """The managed hook command is reconciled at command granularity."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-hook-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.hooks = self.home / ".codex/hooks.json"
        self.hooks.parent.mkdir(parents=True)
        self.hooks.write_text(json.dumps(MIXED_HOOKS, indent=2) + "\n", encoding="utf-8")
        self.env = dict(os.environ, HOME=str(self.home),
                        DOTFILES_CODEX_HOOKS=str(self.hooks))

    def command(self, action):
        return subprocess.run(["/bin/bash", str(HOOKS), action], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def session(self):
        data = json.loads(self.hooks.read_text(encoding="utf-8"))
        return data["hooks"]["SessionStart"], data

    def commands(self, session):
        return [hook["command"]
                for group in session
                for hook in group.get("hooks", [])]

    def test_install_keeps_the_device_commands_and_the_metadata_of_a_mixed_group(self):
        result = self.command("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        session, data = self.session()
        # The mixed group keeps its device command and its own metadata.
        self.assertEqual(session[0]["matcher"], "startup")
        self.assertEqual(session[0]["hooks"],
                         [{"type": "command", "command": "device-hook", "timeout": 30}])
        # Herdr owns its own entry, and it stays untouched.
        self.assertIn("herdr-agent-state.sh", session[1]["hooks"][0]["command"])
        # The managed entry is last, so its resume argv wins.
        self.assertEqual(len(session), 3)
        self.assertIn("herdr-codex-resume.sh", session[-1]["hooks"][0]["command"])
        # Another event keeps the device's own command.
        self.assertEqual(data["hooks"]["Stop"], MIXED_HOOKS["hooks"]["Stop"])

    def test_a_repeat_install_changes_nothing(self):
        first = self.command("install")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self.hooks.read_bytes()
        # A rewrite would carry a new modification time, so the stamp tells
        # a repeated registration from one that wrote the file again.
        stamp = 1000000000
        os.utime(self.hooks, (stamp, stamp))
        second = self.command("install")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.hooks.read_bytes(), before)
        self.assertEqual(self.hooks.stat().st_mtime, stamp)

    def test_removal_keeps_the_device_commands_and_the_metadata_of_a_mixed_group(self):
        installed = self.command("install")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        result = self.command("remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        session, data = self.session()
        self.assertEqual(session[0]["matcher"], "startup")
        self.assertEqual(session[0]["hooks"],
                         [{"type": "command", "command": "device-hook", "timeout": 30}])
        self.assertIn("herdr-agent-state.sh", session[1]["hooks"][0]["command"])
        self.assertEqual(len(session), 2)
        self.assertNotIn("herdr-codex-resume.sh", " ".join(self.commands(session)))
        self.assertEqual(data["hooks"]["Stop"], MIXED_HOOKS["hooks"]["Stop"])

    def test_a_group_that_held_only_the_managed_command_disappears(self):
        data = json.loads(self.hooks.read_text(encoding="utf-8"))
        data["hooks"]["SessionStart"].append(
            {"hooks": [{"type": "command", "command": MANAGED_COMMAND, "timeout": 5}]})
        self.hooks.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        result = self.command("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        session, _ = self.session()
        self.assertEqual(len(session), 3)
        for group in session:
            self.assertTrue(group.get("hooks"), "a group was left without a command")

    def test_a_command_that_only_mentions_the_managed_script_is_not_the_managed_command(self):
        # The managed command runs the managed script. A device command that
        # only mentions its name, and a device command that runs a file
        # beside it, are device commands: they stay.
        data = json.loads(self.hooks.read_text(encoding="utf-8"))
        group = data["hooks"]["SessionStart"][0]
        group["hooks"].append({"type": "command", "command": "echo herdr-codex-resume.sh",
                               "timeout": 30})
        group["hooks"].append({"type": "command",
                               "command": 'bash "$HOME/.codex/herdr-codex-resume.sh.backup"',
                               "timeout": 30})
        self.hooks.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        removed = self.command("remove")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        session, _ = self.session()
        commands = self.commands(session)
        self.assertIn("echo herdr-codex-resume.sh", commands)
        self.assertIn('bash "$HOME/.codex/herdr-codex-resume.sh.backup"', commands)
        self.assertNotIn(MANAGED_COMMAND, commands)
        # An install keeps them beside the managed command.
        installed = self.command("install")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        session, _ = self.session()
        commands = self.commands(session)
        self.assertIn("echo herdr-codex-resume.sh", commands)
        self.assertIn('bash "$HOME/.codex/herdr-codex-resume.sh.backup"', commands)
        self.assertEqual(commands[-1], MANAGED_COMMAND)

    def test_a_stored_path_of_the_managed_script_is_the_managed_command(self):
        # The device may store the same script as the expanded path of its
        # own home. That is the managed command, not a device command.
        expanded = 'bash "%s/.codex/herdr-codex-resume.sh"' % self.home
        data = json.loads(self.hooks.read_text(encoding="utf-8"))
        data["hooks"]["SessionStart"][0]["hooks"].append(
            {"type": "command", "command": expanded, "timeout": 5})
        self.hooks.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        status = self.command("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        removed = self.command("remove")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        session, _ = self.session()
        self.assertNotIn(expanded, self.commands(session))
        self.assertNotIn(MANAGED_COMMAND, self.commands(session))

    def test_status_reports_the_managed_registration(self):
        status = self.command("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("registered", status.stdout)
        removed = self.command("remove")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        status = self.command("status")
        self.assertEqual(status.returncode, 1)
        self.assertIn("not registered", status.stderr)

    def test_removal_without_the_managed_command_is_a_no_op(self):
        self.hooks.write_text(json.dumps({"hooks": {"SessionStart": []}}, indent=2) + "\n",
                              encoding="utf-8")
        before = self.hooks.read_bytes()
        result = self.command("remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hooks.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
