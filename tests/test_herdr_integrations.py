"""Herdr's integrations are triggered by the deployment, never written by it."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from pins import agent_pins, common_pin, native_agent_pins

SOURCE = Path(__file__).resolve().parents[1]
HELPER = SOURCE / "dot_local/bin/executable_dotfiles-herdr-status"
HEALTH = SOURCE / "dot_local/bin/executable_dotfiles-agent-health"
AGENTS = SOURCE / "dot_local/bin/executable_dotfiles-agents.tmpl"
FAKE_HERDR = SOURCE / "tests/fixtures/fake-herdr"

FAKE_SKILL = """---
name: herdr
description: "Fake Herdr skill used by the deployment tests."
---

# Herdr

The fake Herdr prints this skill.
"""

BUN_HELPER = """import pathlib, sys
pins = {pins!r}
project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])
pin = pins[project.name]
for command in pin['commands'].split(','):
    launcher = project / 'node_modules/.bin' / command
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\\necho ' + pin['version'] + '\\n')
    launcher.chmod(0o755)
"""


class HerdrFixture:
    """A disposable home with a fake Herdr that logs every invocation."""

    def build(self, root):
        self.root = root
        self.home = root / "device"
        self.bin = root / "bin"
        self.bin.mkdir(parents=True)
        # The fake Herdr lives in its own directory, so a host without Herdr
        # is one PATH entry away.
        self.herdr_bin = root / "herdr-bin"
        self.herdr_bin.mkdir(parents=True)
        self.log = root / "herdr.log"
        self.state = root / "herdr.state"
        self.marker = root / "herdr-marker"
        self.skill = root / "herdr-skill.md"
        self.skill.write_text(FAKE_SKILL, encoding="utf-8")
        self.herdr = self.herdr_bin / "herdr"
        shutil.copyfile(FAKE_HERDR, self.herdr)
        self.herdr.chmod(0o755)
        # The managed hook installer runs Python; the test supplies the
        # interpreter it uses instead of the host's.
        interpreter = self.bin / "python3"
        interpreter.symlink_to(sys.executable)
        helper = root / "bun.py"
        helper.write_text(BUN_HELPER.format(pins=agent_pins()), encoding="utf-8")
        self.bun = self.bin / "bun"
        self.bun.write_text(
            '#!/bin/sh\nif [ "$1" = --version ]; then echo ' + common_pin("bun") +
            '; else exec "' + sys.executable + '" "' + str(helper) + '" "$@"; fi\n',
            encoding="utf-8")
        self.bun.chmod(0o755)
        self.node = self.bin / "node"
        self.node.write_text('#!/bin/sh\necho v' + common_pin("nodejs") + '\n', encoding="utf-8")
        self.node.chmod(0o755)
        # The verified native release is already in place, so the deployment
        # adopts it instead of fetching one.
        qoder = native_agent_pins()["qoder"]
        self.qoder_cli = self.home / ".qoder/bin/qodercli" / f"qodercli-{qoder['version']}"
        self.qoder_cli.parent.mkdir(parents=True)
        self.qoder_cli.write_text(
            '#!/bin/sh\nif [ "$1" = --version ]; then echo ' + qoder["version"] + '; fi\n',
            encoding="utf-8")
        self.qoder_cli.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "BUN_", "PIXI_", "UV_", "NPM_", "ATUIN_",
                                           "CARGO_", "RUSTUP_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                    "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}
        self.env.update(HOME=str(root / "original"), PATH=f"{self.bin}:/usr/bin:/bin",
                        XDG_STATE_HOME=str(self.home / ".local/state"),
                        DOTFILES_SKILLS_DIR=str(SOURCE / "tests/fixtures/skill-library"))

    def herdr_env(self, herdr=True):
        environment = dict(self.env)
        environment.update(HERDR_LOG=str(self.log), HERDR_STATE=str(self.state),
                           HERDR_MARKER=str(self.marker), HERDR_SKILL=str(self.skill))
        if herdr:
            environment["PATH"] = f"{self.herdr_bin}:{environment['PATH']}"
        return environment

    def write_state(self, rows):
        self.state.write_text("".join(f"{kind}|{value}\n" for kind, value in rows), encoding="utf-8")

    def invocations(self):
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").splitlines()

    def deploy(self, *arguments, herdr=True, env=None):
        environment = self.herdr_env(herdr)
        environment.update(DOTFILES_CHEZMOI_BIN=shutil.which("chezmoi") or "",
                           DOTFILES_BUN_BIN=str(self.bun), DOTFILES_NODE_BIN=str(self.node))
        if env:
            environment.update(env)
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--home", str(self.home), "--platform", "linux",
                               "--role", "workstation", *arguments],
                              cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=600)

    def state_rows(self, name):
        path = self.home / ".local/state/dotfiles" / name
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                rows.append(line)
        return rows


@unittest.skipUnless(shutil.which("chezmoi"), "the deployment boundary requires chezmoi")
class HerdrDeploymentTests(unittest.TestCase, HerdrFixture):
    """The deployment step triggers Herdr for the selected managed agents."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-step-")
        cls.fixture = HerdrFixture()
        cls.fixture.build(Path(cls.temporary.name))
        # pi and opencode are current, claude and qodercli are missing, and
        # codex and kimi are outdated.
        cls.fixture.write_state([
            ("pi", "current"),
            ("opencode", "current"),
            ("claude", "missing"),
            ("codex", "outdated"),
            ("kimi", "outdated"),
            ("qodercli", "missing"),
        ])
        cls.result = cls.fixture.deploy("--agents-only", "--agents", "all")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_the_deployment_succeeds_and_installs_only_the_drifted_integrations(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-4000:])
        invocations = self.fixture.invocations()
        self.assertIn("integration install claude", invocations)
        self.assertIn("integration install codex", invocations)
        self.assertIn("integration install kimi", invocations)
        self.assertIn("integration install qodercli", invocations)
        # A current integration is never installed again.
        self.assertNotIn("integration install pi", invocations)
        self.assertNotIn("integration install opencode", invocations)

    def test_an_agent_without_a_herdr_kind_is_never_passed_to_herdr(self):
        invocations = self.fixture.invocations()
        self.assertNotIn("integration install minimax", invocations)
        self.assertNotIn("integration status minimax", invocations)
        self.assertNotIn("minimax", " ".join(invocations))

    def test_the_deployment_writes_only_the_integrations_of_the_selected_agents(self):
        installed = sorted(path.name for path in self.fixture.marker.iterdir())
        self.assertEqual(installed, ["claude", "codex", "kimi", "qodercli"])

    def test_the_herdr_state_records_the_managed_agents_and_their_kinds(self):
        rows = self.fixture.state_rows("herdr.tsv")
        self.assertIn("codex|codex|current", rows)
        self.assertIn("qoder|qodercli|current", rows)
        self.assertIn("pi|pi|current", rows)
        self.assertNotIn("minimax", " ".join(rows))

    def test_a_codex_reinstall_registers_the_managed_resume_hook_last(self):
        hooks = json.loads((self.fixture.home / ".codex/hooks.json").read_text(encoding="utf-8"))
        commands = [hook["command"] for entry in hooks["hooks"]["SessionStart"] for hook in entry["hooks"]]
        self.assertEqual(len(commands), 2, commands)
        self.assertIn("herdr-agent-state.sh", commands[0])
        self.assertIn("herdr-codex-resume.sh", commands[1])

    def test_the_herdr_skill_is_generated_into_the_shared_tree(self):
        skill = self.fixture.home / ".agents/skills/herdr/SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertEqual(skill.read_text(encoding="utf-8"), FAKE_SKILL)
        rows = self.fixture.state_rows("generated-skills.tsv")
        self.assertIn("herdr|.agents/skills|herdr --skill", rows)

    def test_the_status_helper_is_managed_as_a_command(self):
        helper = self.fixture.home / ".local/bin/dotfiles-herdr-status"
        self.assertTrue(helper.is_file())
        self.assertTrue(os.access(helper, os.X_OK))


@unittest.skipUnless(shutil.which("chezmoi"), "the deployment boundary requires chezmoi")
class HerdrSelectionTests(unittest.TestCase, HerdrFixture):
    """An agent outside the selection is never passed to Herdr."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-selection-")
        cls.fixture = HerdrFixture()
        cls.fixture.build(Path(cls.temporary.name))
        cls.fixture.write_state([("pi", "missing"), ("claude", "missing"), ("codex", "missing"),
                                 ("kimi", "missing"), ("qodercli", "missing")])
        cls.result = cls.fixture.deploy("--agents-only", "--agents", "codex")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_only_the_selected_agent_reaches_herdr(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-4000:])
        installs = [line for line in self.fixture.invocations() if line.startswith("integration install")]
        self.assertEqual(installs, ["integration install codex"])
        installed = sorted(path.name for path in self.fixture.marker.iterdir())
        self.assertEqual(installed, ["codex"])


@unittest.skipUnless(shutil.which("chezmoi"), "the deployment boundary requires chezmoi")
class HerdrAbsentTests(unittest.TestCase, HerdrFixture):
    """A host without Herdr still completes the deployment."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-absent-")
        cls.fixture = HerdrFixture()
        cls.fixture.build(Path(cls.temporary.name))
        cls.result = cls.fixture.deploy("--agents-only", "--agents", "codex", herdr=False)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_the_step_succeeds_with_nothing_to_do(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-4000:])
        self.assertEqual(self.fixture.invocations(), [])
        self.assertFalse(self.fixture.marker.exists())

    def test_the_state_records_the_kinds_as_unavailable(self):
        rows = self.fixture.state_rows("herdr.tsv")
        self.assertIn("codex|codex|unavailable", rows)


@unittest.skipUnless(shutil.which("chezmoi"), "the deployment boundary requires chezmoi")
class HerdrApplyOnlyTests(unittest.TestCase, HerdrFixture):
    """An apply-only deployment runs no agent or Herdr command."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-apply-only-")
        cls.fixture = HerdrFixture()
        cls.fixture.build(Path(cls.temporary.name))
        cls.fixture.write_state([("codex", "missing")])
        cls.result = cls.fixture.deploy("--apply-only")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_no_herdr_command_runs(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-4000:])
        self.assertEqual(self.fixture.invocations(), [])
        self.assertFalse(self.fixture.marker.exists())


@unittest.skipUnless(shutil.which("chezmoi"), "the deployment boundary requires chezmoi")
class HerdrSkillRefreshTests(unittest.TestCase, HerdrFixture):
    """The generated skill is refreshed from the installed binary."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-skill-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = HerdrFixture()
        self.fixture.build(Path(self.temporary.name))
        self.fixture.write_state([("codex", "current")])

    def test_the_skill_is_refreshed_and_unchanged_bytes_are_not_rewritten(self):
        first = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertEqual(first.returncode, 0, first.stderr[-4000:])
        skill = self.fixture.home / ".agents/skills/herdr/SKILL.md"
        self.assertEqual(skill.read_text(encoding="utf-8"), FAKE_SKILL)
        # A reapply with the same binary leaves the file untouched.
        stamp = 1000000000
        os.utime(skill, (stamp, stamp))
        second = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertEqual(second.returncode, 0, second.stderr[-4000:])
        self.assertEqual(skill.stat().st_mtime, stamp)
        # A new binary refreshes the bytes.
        self.fixture.skill.write_text(FAKE_SKILL + "\nrefreshed\n", encoding="utf-8")
        third = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertEqual(third.returncode, 0, third.stderr[-4000:])
        self.assertEqual(skill.read_text(encoding="utf-8"), FAKE_SKILL + "\nrefreshed\n")

    def test_herdr_without_skill_bytes_still_skips_the_write(self):
        empty = Path(self.temporary.name) / "empty-skill.md"
        empty.write_text("", encoding="utf-8")
        result = self.fixture.deploy("--agents-only", "--agents", "codex",
                                     env={"HERDR_SKILL": str(empty)})
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        self.assertFalse((self.fixture.home / ".agents/skills/herdr/SKILL.md").exists())

    def test_the_generated_skill_does_not_depend_on_the_agent_selection(self):
        result = self.fixture.deploy("--agents-only", "--agents", "none")
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        skill = self.fixture.home / ".agents/skills/herdr/SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertEqual(skill.read_text(encoding="utf-8"), FAKE_SKILL)
        # No agent is selected, so Herdr is never asked for an integration.
        self.assertNotIn("integration install codex", self.fixture.invocations())

    def test_the_generated_skill_stays_recorded_without_herdr(self):
        first = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertEqual(first.returncode, 0, first.stderr[-4000:])
        self.assertIn("herdr|.agents/skills|herdr --skill",
                      self.fixture.state_rows("generated-skills.tsv"))
        # A host that no longer provides Herdr keeps the generated skill and
        # its record, so the pruning step leaves it alone.
        second = self.fixture.deploy("--agents-only", "--agents", "codex", herdr=False)
        self.assertEqual(second.returncode, 0, second.stderr[-4000:])
        self.assertTrue((self.fixture.home / ".agents/skills/herdr/SKILL.md").is_file())
        self.assertIn("herdr|.agents/skills|herdr --skill",
                      self.fixture.state_rows("generated-skills.tsv"))


@unittest.skipUnless(shutil.which("chezmoi"), "the deployment boundary requires chezmoi")
class HerdrSkillSymlinkTests(unittest.TestCase, HerdrFixture):
    """The generated skill never writes through a symlink."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-symlink-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = HerdrFixture()
        self.fixture.build(Path(self.temporary.name))
        self.fixture.write_state([("codex", "current")])
        self.skills = self.fixture.home / ".agents/skills"

    def test_a_symlinked_skill_directory_is_refused(self):
        outside = Path(self.temporary.name) / "outside-skill"
        outside.mkdir()
        self.skills.mkdir(parents=True)
        (self.skills / "herdr").symlink_to(outside)
        result = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(self.skills / "herdr"), result.stderr)
        # The write never crossed the link.
        self.assertFalse((outside / "SKILL.md").exists())

    def test_a_symlinked_skill_file_is_refused(self):
        outside = Path(self.temporary.name) / "outside-skill.md"
        outside.write_text("device bytes\n", encoding="utf-8")
        (self.skills / "herdr").mkdir(parents=True)
        (self.skills / "herdr/SKILL.md").symlink_to(outside)
        result = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(self.skills / "herdr/SKILL.md"), result.stderr)
        # The device bytes outside the managed tree are untouched.
        self.assertEqual(outside.read_text(encoding="utf-8"), "device bytes\n")

    def test_a_normal_refresh_still_writes_the_skill(self):
        result = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        skill = self.skills / "herdr/SKILL.md"
        self.assertEqual(skill.read_text(encoding="utf-8"), FAKE_SKILL)
        self.assertIn("herdr|.agents/skills|herdr --skill",
                      self.fixture.state_rows("generated-skills.tsv"))


@unittest.skipUnless(shutil.which("chezmoi"), "the deployment boundary requires chezmoi")
class HerdrCodexHookTests(unittest.TestCase, HerdrFixture):
    """The managed resume hook stays last and keeps the device hooks."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-hook-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = HerdrFixture()
        self.fixture.build(Path(self.temporary.name))
        self.fixture.write_state([("codex", "missing")])

    def test_the_managed_hook_stays_last_and_the_device_hooks_survive(self):
        first = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertEqual(first.returncode, 0, first.stderr[-4000:])
        hooks = self.fixture.home / ".codex/hooks.json"
        data = json.loads(hooks.read_text(encoding="utf-8"))
        commands = [hook["command"] for entry in data["hooks"]["SessionStart"] for hook in entry["hooks"]]
        self.assertIn("herdr-codex-resume.sh", commands[-1])
        # A device hook is preserved by the next apply.
        data["hooks"]["SessionStart"].insert(0, {"hooks": [{"type": "command", "command": "device-hook"}]})
        data["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "device-stop"}]}]
        hooks.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        device_hooks = hooks.read_bytes()
        second = self.fixture.deploy("--agents-only", "--agents", "codex")
        self.assertEqual(second.returncode, 0, second.stderr[-4000:])
        self.assertEqual(hooks.read_bytes(), device_hooks)
        data = json.loads(hooks.read_text(encoding="utf-8"))
        commands = [hook["command"] for entry in data["hooks"]["SessionStart"] for hook in entry["hooks"]]
        self.assertIn("device-hook", commands)
        self.assertIn("herdr-codex-resume.sh", commands[-1])
        self.assertEqual(data["hooks"]["Stop"][0]["hooks"][0]["command"], "device-stop")
        # A current integration is not installed again.
        self.assertEqual(self.fixture.invocations().count("integration install codex"), 1)


class HerdrStatusHelperTests(unittest.TestCase):
    """The helper owns Herdr's status vocabulary."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-helper-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state = self.root / "state"
        self.log = self.root / "log"
        self.herdr = self.bin / "herdr"
        shutil.copyfile(FAKE_HERDR, self.herdr)
        self.herdr.chmod(0o755)
        self.skill = self.root / "skill.md"
        self.skill.write_text(FAKE_SKILL, encoding="utf-8")
        self.env = dict(os.environ, HOME=str(self.root / "home"),
                        PATH=f"{self.bin}:/usr/bin:/bin",
                        HERDR_LOG=str(self.log), HERDR_STATE=str(self.state),
                        HERDR_MARKER=str(self.root / "marker"), HERDR_SKILL=str(self.skill))

    def status(self, *kinds):
        result = subprocess.run(["/bin/bash", str(HELPER), *kinds], env=self.env,
                                capture_output=True, text=True, timeout=30)
        return result

    def test_each_state_is_normalized(self):
        self.state.write_text("pi|current\nclaude|missing\ncodex|outdated\n", encoding="utf-8")
        result = self.status("pi", "claude", "codex", "kimi")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ["pi|current", "claude|missing", "codex|outdated", "kimi|unsupported"])

    def test_an_absent_herdr_reports_unavailable(self):
        env = dict(self.env, PATH="/usr/bin:/bin")
        result = subprocess.run(["/bin/bash", str(HELPER), "pi"], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["pi|unavailable"])

    def test_an_unknown_kind_is_rejected(self):
        result = self.status("pi|codex")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid kind", result.stderr)


class HerdrStatusColumnTests(unittest.TestCase):
    """The agent status reports the Herdr state of every selected agent."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-status-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        (self.home / ".local/bin").mkdir(parents=True)
        shutil.copyfile(HELPER, self.home / ".local/bin/dotfiles-herdr-status")
        (self.home / ".local/bin/dotfiles-herdr-status").chmod(0o755)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.herdr_bin = self.root / "herdr-bin"
        self.herdr_bin.mkdir()
        self.state = self.root / "state"
        self.log = self.root / "log"
        self.herdr = self.herdr_bin / "herdr"
        shutil.copyfile(FAKE_HERDR, self.herdr)
        self.herdr.chmod(0o755)
        self.skill = self.root / "skill.md"
        self.skill.write_text(FAKE_SKILL, encoding="utf-8")
        self.script = self.root / "dotfiles-agents"
        self.script.write_text(AGENTS.read_text(encoding="utf-8").replace(
            "{{ .chezmoi.sourceDir }}", str(SOURCE)), encoding="utf-8")
        self.script.chmod(0o755)

    def status(self, selection="all", herdr=True):
        path = f"{self.herdr_bin}:/usr/bin:/bin" if herdr else "/usr/bin:/bin"
        env = dict(os.environ, HOME=str(self.home), PATH=path,
                   XDG_STATE_HOME=str(self.home / ".local/state"),
                   HERDR_LOG=str(self.log), HERDR_STATE=str(self.state),
                   HERDR_MARKER=str(self.root / "marker"), HERDR_SKILL=str(self.skill),
                   DOTFILES_SOURCE=str(SOURCE))
        return subprocess.run(["/bin/bash", str(self.script), "status", selection], env=env,
                              cwd=SOURCE, capture_output=True, text=True, timeout=120)

    def test_the_herdr_column_reports_the_state_of_every_selected_agent(self):
        self.state.write_text("pi|current\nclaude|missing\ncodex|outdated\n", encoding="utf-8")
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {line.split()[0]: line.split() for line in result.stdout.splitlines()[1:] if line.split()}
        self.assertIn("HERDR", result.stdout.splitlines()[0])
        self.assertEqual(rows["codex"][4], "outdated")
        self.assertEqual(rows["claude"][4], "missing")
        self.assertEqual(rows["pi"][4], "current")
        # An agent Herdr does not integrate has no kind at all.
        self.assertEqual(rows["minimax"][4], "unsupported")

    def test_the_column_reports_unavailable_without_herdr(self):
        result = self.status(herdr=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {line.split()[0]: line.split() for line in result.stdout.splitlines()[1:] if line.split()}
        self.assertEqual(rows["codex"][4], "unavailable")
        self.assertEqual(rows["minimax"][4], "unsupported")


class HerdrHealthTests(unittest.TestCase):
    """The health check reports the Herdr drift without failing."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-herdr-health-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        (self.home / ".local/bin").mkdir(parents=True)
        (self.home / ".local/state/dotfiles").mkdir(parents=True)
        shutil.copyfile(HELPER, self.home / ".local/bin/dotfiles-herdr-status")
        (self.home / ".local/bin/dotfiles-herdr-status").chmod(0o755)
        (self.home / ".local/state/dotfiles/herdr.tsv").write_text(
            "# agent|kind|state\ncodex|codex|outdated\nqoder|qodercli|missing\n", encoding="utf-8")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.herdr_bin = self.root / "herdr-bin"
        self.herdr_bin.mkdir()
        self.state = self.root / "state"
        self.log = self.root / "log"
        self.herdr = self.herdr_bin / "herdr"
        shutil.copyfile(FAKE_HERDR, self.herdr)
        self.herdr.chmod(0o755)
        self.skill = self.root / "skill.md"
        self.skill.write_text(FAKE_SKILL, encoding="utf-8")
        for command in ("codex", "codegraph", "graphify"):
            executable = self.bin / command
            executable.write_text('#!/bin/sh\nexit 0\n', encoding="utf-8")
            executable.chmod(0o755)

    def health(self):
        env = dict(os.environ, HOME=str(self.home), PATH=f"{self.herdr_bin}:{self.bin}:/usr/bin:/bin",
                   XDG_STATE_HOME=str(self.home / ".local/state"),
                   DOTFILES_PLATFORM="macos", HERDR_LOG=str(self.log), HERDR_STATE=str(self.state),
                   HERDR_MARKER=str(self.root / "marker"), HERDR_SKILL=str(self.skill))
        return subprocess.run(["/bin/bash", str(HEALTH), "--clients"], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_the_drift_is_reported_and_does_not_fail_the_check(self):
        self.state.write_text("codex|current\nqodercli|missing\n", encoding="utf-8")
        result = self.health()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("herdr integration codex (current)", result.stdout)
        self.assertIn("herdr integration qodercli (missing)", result.stderr)


if __name__ == "__main__":
    unittest.main()
