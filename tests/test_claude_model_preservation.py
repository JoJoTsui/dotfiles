"""Preserve the exact declared model through pinned-client initialization."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from pins import agent_pins, common_pin


SOURCE = Path(__file__).resolve().parents[1]


class ClaudeModelPreservationTests(unittest.TestCase):
    def setUp(self):
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-claude-model-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "device"
        tools = self.root / "tools"
        tools.mkdir()
        pins = agent_pins()
        cli = tools / "synthetic-claude.py"
        cli.write_text(
            "import json, os, pathlib, sys\n"
            "home = pathlib.Path(os.environ['HOME'])\n"
            "if sys.argv[1:] == ['--version']:\n"
            f"    print({pins['claude']['version']!r}); raise SystemExit\n"
            "settings_path = home / '.claude/settings.json'\n"
            "global_path = home / '.claude.json'\n"
            "settings = json.loads(settings_path.read_text())\n"
            "global_settings = json.loads(global_path.read_text())\n"
            "if global_settings.get('migrationVersion') == 13:\n"
            "    global_settings['migrationVersion'] = 14\n"
            "    for project in global_settings.get('projects', {}).values():\n"
            "        project.pop('projectOnboardingSeenCount', None)\n"
            "        project.pop('hasCompletedProjectOnboarding', None)\n"
            "    if settings.get('model') == 'opus':\n"
            "        settings['model'] = os.environ.get('TEST_CLAUDE_AFTER_MODEL', 'opus[1m]')\n"
            "    settings_path.write_text(json.dumps(settings))\n"
            "    global_path.write_text(json.dumps(global_settings))\n"
            "print('[]')\n")
        bun_helper = tools / "bun.py"
        bun_helper.write_text(
            "import json, os, pathlib, sys\n"
            f"pins = {pins!r}\n"
            "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            "pin = pins[project.name]\n"
            "for command in pin['commands'].split(','):\n"
            "    target = project / 'node_modules/.bin' / command\n"
            "    target.parent.mkdir(parents=True, exist_ok=True)\n"
            "    if project.name == 'claude':\n"
            f"        target.write_text('#!{sys.executable}\\n' + pathlib.Path({str(cli)!r}).read_text())\n"
            "    else:\n"
            "        target.write_text('#!/bin/sh\\necho ' + pin['version'] + '\\n')\n"
            "    target.chmod(0o755)\n"
            "if project.name == 'codegraph' and os.environ.get('TEST_CODEGRAPH_MODEL_CHANGE') == '1':\n"
            "    path = pathlib.Path(os.environ['HOME']) / '.claude/settings.json'\n"
            "    settings = json.loads(path.read_text()); settings['model'] = 'opus[1m]'\n"
            "    path.write_text(json.dumps(settings))\n")
        bun = tools / "bun"
        bun.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo ' + common_pin("bun") +
                       '; else exec "' + sys.executable + '" "' + str(bun_helper) + '" "$@"; fi\n')
        bun.chmod(0o755)
        node = tools / "node"
        node.write_text('#!/bin/sh\necho v' + common_pin("nodejs") + '\n')
        node.chmod(0o755)
        self.env = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1",
                    "DOTFILES_CHEZMOI_BIN": self.chezmoi, "DOTFILES_BUN_BIN": str(bun), "DOTFILES_NODE_BIN": str(node),
                    "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library")}

    def seed(self, model):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        # Existing JSONC must pass the real public parser before initialization.
        settings.write_text('// device settings\n' + json.dumps({"model": model, "env": {"DEVICE_TOKEN": "synthetic-retain"},
                                                               "devicePreference": {"enabled": False}}))
        (self.home / ".claude.json").write_text(json.dumps({
            "migrationVersion": 13, "oauthAccount": {"device": "retain"},
            "projects": {"synthetic-project": {"hasTrustDialogAccepted": True, "projectOnboardingSeenCount": 4,
                                                  "hasCompletedProjectOnboarding": True}}}))
        wt = self.home / ".pixi/bin/wt"
        wt.parent.mkdir(parents=True)
        wt.write_text('#!' + sys.executable + '\n'
                      'import json, os, pathlib, subprocess, sys\n'
                      'home = pathlib.Path(os.environ["HOME"])\n'
                      'if sys.argv[1:4] == ["config", "plugins", "claude"]:\n'
                      '    subprocess.run([str(home / ".local/bin/claude"), "plugin", "list", "--json"], check=True)\n'
                      '    path = home / ".claude/settings.json"\n'
                      '    settings = json.loads(path.read_text())\n'
                      '    settings["enabledPlugins"] = {"worktrunk@worktrunk": True}\n'
                      '    path.write_text(json.dumps(settings))\n')
        wt.chmod(0o755)

    def deploy(self, *, selection="claude", apply_only=False, overrides=None):
        arguments = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE), "--home", str(self.home),
                     "--platform", "macos", "--role", "workstation", "--agents", selection,
                     "--apply-only" if apply_only else "--agents-only"]
        result = subprocess.run(arguments, env=dict(self.env, **(overrides or {})), cwd=SOURCE,
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads((self.home / ".claude/settings.json").read_text())

    def assert_device_and_runtime_values(self, settings):
        self.assertEqual(settings["env"]["DEVICE_TOKEN"], "synthetic-retain")
        self.assertIs(settings["devicePreference"]["enabled"], False)
        self.assertTrue(settings["enabledPlugins"]["worktrunk@worktrunk"])
        global_settings = json.loads((self.home / ".claude.json").read_text())
        self.assertEqual(global_settings["migrationVersion"], 14)
        self.assertEqual(global_settings["oauthAccount"], {"device": "retain"})
        project = global_settings["projects"]["synthetic-project"]
        self.assertTrue(project["hasTrustDialogAccepted"])
        self.assertNotIn("projectOnboardingSeenCount", project)
        self.assertNotIn("hasCompletedProjectOnboarding", project)

    def test_selected_claude_preserves_declared_opus_and_stable_reapply(self):
        self.seed("opus")
        settings = self.deploy()
        self.assertEqual(settings["model"], "opus")
        self.assert_device_and_runtime_values(settings)
        snapshot = [(self.home / relative).read_bytes() for relative in (".claude/settings.json", ".claude.json")]
        self.assertEqual(self.deploy()["model"], "opus")
        self.assertEqual([(self.home / relative).read_bytes() for relative in (".claude/settings.json", ".claude.json")], snapshot)

    def test_existing_explicit_context_and_custom_models_are_preserved(self):
        for model in ("opus[1m]", "custom-provider-model"):
            with self.subTest(model=model):
                self.home = self.root / ("context" if model == "opus[1m]" else "custom")
                self.seed(model)
                settings = self.deploy()
                self.assertEqual(settings["model"], model)
                self.assert_device_and_runtime_values(settings)

    def test_unselected_claude_does_not_restore_another_clients_change(self):
        self.seed("opus")
        settings = self.deploy(selection="none", overrides={"TEST_CODEGRAPH_MODEL_CHANGE": "1"})
        self.assertEqual(settings["model"], "opus[1m]")
        self.assertEqual(json.loads((self.home / ".claude.json").read_text())["migrationVersion"], 13)

    def test_apply_only_ignores_an_inherited_internal_restoration_flag(self):
        self.seed("opus[1m]")
        settings = self.deploy(apply_only=True, overrides={"DOTFILES_SETTINGS_KEEP_PLAIN_OPUS": "1"})
        self.assertEqual(settings["model"], "opus[1m]")

    def test_restoration_does_not_revert_a_different_runtime_model_choice(self):
        self.seed("opus")
        settings = self.deploy(overrides={"TEST_CLAUDE_AFTER_MODEL": "different-runtime-model"})
        self.assertEqual(settings["model"], "different-runtime-model")
        self.assert_device_and_runtime_values(settings)


if __name__ == "__main__":
    unittest.main()
