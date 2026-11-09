"""Portable payload behavior through bootstrap and offline client discovery."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import errno
from urllib.parse import unquote, urlparse
from fixtures.skill_discovery import codex_prompt, command_catalog, opencode_skills, pi_resources, resolve_skill_path
from fixtures.skills import write_skill_library
from fixtures.shell_env import managed_shell_environment

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]


class AgentPayloadTests(unittest.TestCase):
    def setUp(self):
        # Agent clients search ancestor directories for skills. Keep the fake
        # device outside the runner's HOME tree so its payload cannot shadow it.
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agent-payload-", dir="/tmp")
        self.addCleanup(self.cleanup_temporary_home)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual payload apply requires chezmoi")
        self.skills_fixture = write_skill_library(self.root / "skills-fixture")
        self.disabled_skills = {
            line.split("|")[0]
            for line in (SOURCE / "deployment/disabled-skills.tsv").read_text().splitlines()
            if line and not line.startswith("#")
        }
        self.expected_skills = {
            path.parent.name for path in self.skills_fixture.glob("*/SKILL.md")
        } - self.disabled_skills
        self.env = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                    "DOTFILES_CHEZMOI_BIN": self.chezmoi,
                    "DOTFILES_SKILLS_DIR": str(self.skills_fixture)}

    def cleanup_temporary_home(self):
        deadline = time.monotonic() + 5
        while True:
            try:
                self.temporary.cleanup()
                return
            except OSError as error:
                if error.errno not in (errno.ENOTEMPTY, errno.EBUSY) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    def deploy(self, *arguments, env=None, source=SOURCE):
        return subprocess.run(["/bin/bash", str(source / "bootstrap.sh"),
                               "--source", str(source), "--home", str(self.home),
                               "--platform", os.environ.get("DOTFILES_TEST_PLATFORM", "linux"),
                               "--role", os.environ.get("DOTFILES_TEST_ROLE", "workstation"),
                               "--apply-only", *arguments],
                              cwd=source, env=env or self.env, capture_output=True,
                              text=True, timeout=60)

    def diagnostic_env(self):
        codegraph = os.environ.get("DOTFILES_TEST_CODEGRAPH")
        node = os.environ.get("DOTFILES_TEST_NODE")
        # Bun launchers resolve `node` from PATH; keep the managed runtime
        # reachable without inheriting the host toolchain.
        extra = [Path(value).parent for value in (codegraph, node) if value]
        path = os.pathsep.join([*(str(item) for item in extra), os.defpath])
        environment = {"HOME": str(self.home), "PATH": path,
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "XDG_DATA_HOME": str(self.home / ".local/share"),
                "XDG_STATE_HOME": str(self.home / ".local/state"),
                "XDG_CACHE_HOME": str(self.home / ".cache"),
                "TMPDIR": str(self.home / ".cache/tmp"),
                "CODEX_HOME": str(self.home / ".codex"),
                "CLAUDE_CONFIG_DIR": str(self.home / ".claude"),
                "KIMI_CODE_HOME": str(self.home / ".kimi-code"),
                "PI_CODING_AGENT_DIR": str(self.home / ".pi/agent"),
                "DOTFILES_TEST_HOME": str(self.home),
                "DOTFILES_TEST_TEMP_ROOT": str(self.root),
                "DOTFILES_TEST_SOURCE": str(SOURCE),
                "DOTFILES_TEST_RUNNER_HOME": str(Path(os.environ.get("HOME", str(self.root))).resolve()),
                "CODEGRAPH_NO_DOWNLOAD": "1", "DO_NOT_TRACK": "1"}
        managed = managed_shell_environment(self.home, environment)
        self.assertEqual(managed.get("HOME"), str(self.home),
                         "shared shell initialization changed the isolated HOME")
        return managed

    def local_skill_path(self, value):
        return resolve_skill_path(value, self.home)

    def skill_path_is_in_home(self, value):
        path = self.local_skill_path(value)
        if path is None:
            return False
        try:
            path.relative_to(self.home.resolve())
            return True
        except ValueError:
            return False

    def skill_path_kind(self, value):
        raw_value = str(value)
        if Path(raw_value).is_absolute():
            return "absolute"
        parsed = urlparse(raw_value)
        if parsed.scheme not in ("", "file"):
            return "other-uri"
        if parsed.scheme == "file":
            host = unquote(parsed.netloc)
            if host == "~":
                return "file-home-uri"
            if host not in ("", "localhost"):
                return "file-other-host"
            raw = unquote(parsed.path)
        else:
            raw = str(value)
        if raw.startswith(("~/", "/~/")):
            return "home-relative"
        return "absolute" if Path(raw).is_absolute() else "relative"

    def skill_path_scope(self, value):
        path = self.local_skill_path(value)
        if path is None:
            return "remote"
        roots = (
            ("device-home", self.home.resolve()),
            ("test-temp", self.root.resolve()),
            ("source-tree", SOURCE.resolve()),
            ("runner-home", Path(os.environ.get("HOME", str(self.root))).resolve()),
        )
        for label, root in roots:
            try:
                path.relative_to(root)
                return label
            except ValueError:
                pass
        return "outside"

    def test_skill_path_membership_resolves_home_relative_paths(self):
        self.assertTrue(self.skill_path_is_in_home("~/.agents/skills/tdd/SKILL.md"))
        self.assertTrue(self.skill_path_is_in_home("file://~/.agents/skills/tdd/SKILL.md"))
        self.assertTrue(self.skill_path_is_in_home("file:///~/.agents/skills/tdd/SKILL.md"))
        self.assertFalse(self.skill_path_is_in_home("~/../outside/SKILL.md"))
        absolute = self.home / ".agents/skills/tdd/SKILL.md"
        self.assertTrue(self.skill_path_is_in_home(str(absolute)))
        self.assertEqual(self.skill_path_kind(str(absolute)), "absolute")

    def test_default_payload_is_usable_even_when_agent_installation_is_disabled(self):
        result = self.deploy("--agents", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        shared = self.home / ".agents/skills"
        claude = self.home / ".claude/skills"
        self.assertEqual({path.parent.name for path in shared.glob("*/SKILL.md")}, self.expected_skills)
        self.assertEqual(len([p for p in shared.rglob("*") if p.is_file()]),
                          len([p for p in self.skills_fixture.rglob("*") if p.is_file()
                               and p.relative_to(self.skills_fixture).parts[0] not in self.disabled_skills]))
        self.assertEqual((shared / "tdd/SKILL.md").read_bytes(), (claude / "tdd/SKILL.md").read_bytes())
        self.assertIn("disable-model-invocation: true", (shared / "implement-spec/SKILL.md").read_text())
        self.assertFalse((shared / "scienceskillscommon").exists())
        self.assertFalse((shared / "clinical-trials-database").exists())
        self.assertEqual((shared / "graphify/references/query.md").read_bytes(),
                         (claude / "graphify/references/query.md").read_bytes())
        self.assertFalse(any(p.is_symlink() for directory in (shared, claude) for p in directory.rglob("*")))
        self.assertFalse((self.home / ".kimi-code/AGENTS.md").exists(),
                         "the retired Kimi brand file must not be recreated")
        for relative in (".agents/AGENTS.md", ".codex/AGENTS.md", ".claude/CLAUDE.md",
                         ".pi/agent/AGENTS.md", ".config/opencode/AGENTS.md",
                         ".minimax/AGENTS.md", ".qoder/AGENTS.md"):
            instructions = (self.home / relative).read_text()
            self.assertIn("## Completion", instructions)
            self.assertIn("## CodeGraph", instructions)
            self.assertIn("~/.agents/RTK.md", instructions)
            self.assertNotIn("/t9k/", instructions)
            self.assertIn("Desired conflict policy", instructions)
            self.assertIn("Safety and authority", instructions)
            self.assertIn("Clean up only worktrees", instructions)
            self.assertIn("max(1, usable - 1)", instructions)
            self.assertNotIn("commit every change", instructions)
            self.assertNotIn("PIXI_JOBS", instructions)
        self.assertNotIn("/t9k/", (self.home / ".agents/RTK.md").read_text())
        self.assertFalse((self.home / ".codegraph").exists())
        self.assertFalse((self.home / ".codex/auth.json").exists())

    def test_disabled_skills_are_quarantined_and_not_restored_from_an_override(self):
        old = self.home / ".agents/skills/pubmed-database/SKILL.md"
        old.parent.mkdir(parents=True)
        old.write_text("preserve disabled device bytes\n")
        result = self.deploy("--agents", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(old.exists())
        backups = list((self.home / ".local/state/dotfiles/disabled-integrations").glob(
            "skills.*/.agents/skills/pubmed-database/SKILL.md"))
        self.assertEqual([p.read_text() for p in backups], ["preserve disabled device bytes\n"])
        self.assertTrue((self.home / ".agents/skills/graphify/SKILL.md").is_file())
        again = self.deploy("--agents", "none")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertFalse(old.exists())
        state = self.home / ".local/state/dotfiles/disabled-integrations"
        self.assertEqual(len(list(state.glob("skills.*"))), 1)

    def test_platform_overlay_replaces_only_the_managed_instruction_block(self):
        target = self.home / ".claude/CLAUDE.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Device prefix\n\nKeep this text.\n")
        with mock.patch.dict(os.environ, {"DOTFILES_TEST_PLATFORM": "macos"}):
            result = self.deploy("--agents", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        macos = target.read_text()
        self.assertIn("Keep this text.", macos)
        self.assertIn("## macOS specifics", macos)
        self.assertIn("gtimeout", macos)
        self.assertNotIn("## Linux specifics", macos)
        with mock.patch.dict(os.environ, {"DOTFILES_TEST_PLATFORM": "linux"}):
            result = self.deploy("--agents", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        linux = target.read_text()
        self.assertIn("Keep this text.", linux)
        self.assertIn("## Linux specifics", linux)
        self.assertIn("`sed -i`", linux)
        self.assertNotIn("## macOS specifics", linux)
        self.assertEqual(linux.count("<!-- DOTFILES_AGENT_START -->"), 1)
        self.assertEqual(linux.count("<!-- DOTFILES_AGENT_END -->"), 1)

    def test_repeat_deployment_preserves_unrelated_instructions_skills_and_local_state(self):
        instructions = self.home / ".claude/CLAUDE.md"
        instructions.parent.mkdir(parents=True)
        custom = "# Device rules\n\nKeep my existing instruction text.\n"
        instructions.write_text(custom)
        existing = {
            ".codex/skills/.system/skill-creator/SKILL.md": "builtin skill\n",
            ".agents/skills/device-skill/SKILL.md": "local skill\n",
            ".claude/skills/device-skill/SKILL.md": "local Claude skill\n",
            ".agents/skills/tdd/device-note.md": "my supplementary note\n",
            ".codex/auth.json": '{"synthetic-device-only":"untouched"}\n',
            ".pi/agent/trust.json": '{"synthetic-project":true}\n',
        }
        for relative, content in existing.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        first = self.deploy()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(instructions.read_text().startswith(custom))
        self.assertEqual(instructions.read_text().count("<!-- DOTFILES_AGENT_START -->"), 1)
        for relative, content in existing.items():
            self.assertEqual((self.home / relative).read_text(), content)
        before = {p.relative_to(self.home): (p.read_bytes(), p.stat().st_mode & 0o777)
                  for p in self.home.rglob("*") if p.is_file()}
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        after = {p.relative_to(self.home): (p.read_bytes(), p.stat().st_mode & 0o777)
                 for p in self.home.rglob("*") if p.is_file()}
        before.pop(Path(".config/chezmoi/chezmoistate.boltdb"), None)
        after.pop(Path(".config/chezmoi/chezmoistate.boltdb"), None)
        self.assertEqual(before, after)

    def test_retired_kimi_block_is_removed_preserving_device_text(self):
        path = self.home / ".kimi-code/AGENTS.md"
        path.parent.mkdir(parents=True)
        path.write_text("# Device Kimi rules\n\n"
                        "<!-- DOTFILES_AGENT_START -->\nold managed body\n"
                        "<!-- DOTFILES_AGENT_END -->\n\nkeep this device line\n")
        first = self.deploy()
        self.assertEqual(first.returncode, 0, first.stderr)
        text = path.read_text()
        self.assertNotIn("old managed body", text)
        self.assertNotIn("DOTFILES_AGENT_START", text)
        self.assertIn("# Device Kimi rules", text)
        self.assertIn("keep this device line", text)
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(path.read_text(), text)

        empty = self.home / ".kimi-code/AGENTS.md"
        empty.write_text("<!-- DOTFILES_AGENT_START -->\nonly ours\n<!-- DOTFILES_AGENT_END -->\n")
        third = self.deploy()
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertFalse(empty.exists(), "an empty retired file must be removed")

    def test_payload_refuses_nested_destination_symlinks_before_copying(self):
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "untouched"
        sentinel.write_text("another device\n")
        for relative in (".agents", ".agents/skills/tdd/resources",
                         ".claude/skills/tdd/SKILL.md", ".codex/AGENTS.md"):
            with self.subTest(relative=relative):
                self.home = self.root / relative.replace("/", "-").replace(".", "")
                escape = self.home / relative
                escape.parent.mkdir(parents=True, exist_ok=True)
                escape.symlink_to(outside, target_is_directory=True)
                result = self.deploy()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("symlink", result.stderr)
                self.assertEqual(list(outside.iterdir()), [sentinel])
                self.assertEqual(sentinel.read_text(), "another device\n")

    def test_rendered_agent_credentials_are_literal_data(self):
        if tomllib is None:
            self.skipTest("literal TOML verification needs Python 3.11+; the managed Python includes it")
        literal = 'synthetic "quote" \\ backslash\n$dollar `backtick` $(touch SHOULD_NOT_EXIST)\tend'
        environment = dict(self.env, GLM_API_TOKEN=literal, KIMI_API_KEY=literal,
                           GLM_BASE_URL=literal)
        result = self.deploy(env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        claude = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(claude["env"]["ANTHROPIC_AUTH_TOKEN"], literal)
        self.assertEqual(claude["env"]["ANTHROPIC_BASE_URL"], literal)
        kimi = tomllib.loads((self.home / ".kimi-code/config.toml").read_text())
        self.assertEqual(kimi["providers"]["managed:kimi-code"]["api_key"], literal)
        self.assertEqual(kimi["services"]["moonshot_search"]["api_key"], literal)
        self.assertEqual(kimi["services"]["moonshot_fetch"]["api_key"], literal)
        self.assertFalse((SOURCE / "SHOULD_NOT_EXIST").exists())
        self.assertFalse((self.home / "SHOULD_NOT_EXIST").exists())

    def test_pinned_opencode_discovers_skills_without_a_model_request(self):
        opencode = os.environ.get("DOTFILES_TEST_OPENCODE")
        if not opencode:
            self.skipTest("requires the pinned OpenCode CLI")
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.expected_skills
        data = opencode_skills(opencode, home=self.home, cwd=self.home,
                               env=dict(self.diagnostic_env(), OPENCODE_TEST_HOME=str(self.home)),
                               log=self.root / "opencode.log", expected=expected)
        skills = {item["id"]: item for item in data}
        self.assertIn("tdd", skills)
        self.assertIn("implement-spec", skills)
        self.assertFalse(skills["implement-spec"]["autoinvoke"])
        managed = [skill for skill in data if self.skill_path_is_in_home(skill["path"])]
        self.assertEqual({skill["id"] for skill in managed}, expected)
        self.assertTrue(self.skill_path_is_in_home(skills["tdd"]["path"]))

    def test_pinned_codex_reads_shared_instructions_and_automatic_skills(self):
        codex = os.environ.get("DOTFILES_TEST_CODEX")
        if not codex:
            self.skipTest("requires the pinned Codex CLI")
        self.assertEqual(self.deploy().returncode, 0)
        text = codex_prompt(codex, cwd=self.home, env=self.diagnostic_env(), log=self.root / "codex.log")
        self.assertIn("~/.agents/RTK.md", text)
        self.assertIn("<!-- DOTFILES_AGENT_START -->", text)
        self.assertIn("- tdd:", text)
        self.assertNotIn("- clinical-trials-database:", text)
        self.assertIn("are for explicit user requests", text)

    def test_pinned_pi_resource_loader_reads_the_full_library_and_global_instructions(self):
        module = os.environ.get("DOTFILES_TEST_PI_MODULE")
        node = os.environ.get("DOTFILES_TEST_NODE")
        if not module or not node:
            self.skipTest("requires the pinned Pi SDK module and managed Node")
        self.assertEqual(self.deploy().returncode, 0)
        data = pi_resources(node, module, cwd=self.home, env=self.diagnostic_env(), log=self.root / "pi.log")
        roots = [(self.home / relative).resolve() for relative in (".agents/skills", ".pi/agent/skills")]
        managed = [skill for skill in data["skills"]
                   if (path := self.local_skill_path(skill["filePath"])) is not None
                   and any(path.is_relative_to(root) for root in roots)]
        expected = self.expected_skills
        self.assertEqual((len(managed), sum(skill["disableModelInvocation"] for skill in managed)),
                         (len(expected), 1), data.get("diagnostics"))
        self.assertIn("<name>tdd</name>", data["prompt"])
        self.assertNotIn("<name>implement-spec</name>", data["prompt"])
        self.assertTrue(any("~/.agents/RTK.md" in item["content"] for item in data["instructions"]))

    def test_skill_resource_names_are_copied_verbatim_without_hook_execution(self):
        source = self.root / "source"
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        resources = self.skills_fixture / "tdd/resources"
        resources.mkdir(parents=True, exist_ok=True)
        hook = resources / "run_once_payload.sh"
        hook.write_text('#!/bin/sh\nprintf executed > "$HOME/PAYLOAD_EXECUTED"\n')
        hook.chmod(0o755)
        template = resources / "dot_literal.tmpl"
        template.write_text("{{ unclosed template is literal skill reference material\n")
        result = self.deploy(source=source)
        self.assertEqual(result.returncode, 0, result.stderr)
        for root in (".agents/skills", ".claude/skills"):
            copied = self.home / root / "tdd/resources"
            self.assertEqual((copied / hook.name).read_bytes(), hook.read_bytes())
            self.assertEqual((copied / template.name).read_bytes(), template.read_bytes())
            self.assertTrue((copied / hook.name).stat().st_mode & 0o111)
        self.assertFalse((self.home / "PAYLOAD_EXECUTED").exists())

    def test_pinned_claude_and_kimi_advertise_manual_and_automatic_skill_commands(self):
        for client in ("claude", "kimi"):
            if not os.environ.get("DOTFILES_TEST_" + client.upper()):
                self.skipTest("requires both pinned Claude and Kimi CLIs")
        self.assertEqual(self.deploy().returncode, 0)
        expected = self.expected_skills
        for client in ("claude", "kimi"):
            with self.subTest(client=client):
                names = command_catalog(client, os.environ["DOTFILES_TEST_" + client.upper()], cwd=self.home,
                                        env=self.diagnostic_env(), log=self.root / f"{client}.log")
                self.assertIn("tdd" if client == "claude" else "skill:tdd", names)
                self.assertIn("implement-spec" if client == "claude" else "skill:implement-spec", names)
                advertised = {name.removeprefix("skill:") for name in names}
                self.assertTrue(expected.issubset(advertised), expected - advertised)
                self.assertTrue(self.disabled_skills.isdisjoint(advertised),
                                self.disabled_skills & advertised)


if __name__ == "__main__":
    unittest.main()
