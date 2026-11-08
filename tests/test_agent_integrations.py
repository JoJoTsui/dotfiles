"""Reversible agent-policy migration in disposable legacy symlink homes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class AgentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agent-policy-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "repo"
        shutil.copytree(SOURCE / "deployment", self.source / "deployment")
        self.script = self.source / "deployment/legacy/agent-integrations.sh"
        self.home = self.root / "home"
        self.live = self.root / "live"
        self.home.mkdir()
        self.live.mkdir()
        for name in (".local", ".cache", ".agents", ".claude", ".codex", ".config", ".pi",
                     ".kimi-code", ".minimax", ".qoder", ".gemini"):
            (self.live / name).mkdir()
            (self.home / name).symlink_to(self.live / name)
        for name in (".minimax", ".qoder"):
            (self.live / name / "skills").symlink_to(self.live / ".agents/skills")
        for root in (".agents/skills", ".claude/skills"):
            p = self.live / root / "pubmed-database"
            p.mkdir(parents=True)
            (p / "SKILL.md").write_text("retained original bytes\n")
            (p / "helper.sh").write_text("#!/bin/sh\nexit 0\n")
            (p / "helper.sh").chmod(0o755)
        (self.live / ".codex/AGENTS.md").write_text(
            "personal rules\n<!-- CODEGRAPH_START -->\nold graph guidance\n<!-- CODEGRAPH_END -->\n")
        (self.live / ".kimi-code/AGENTS.md").write_text(
            "<!-- DOTFILES_AGENT_START -->\nretired Kimi block\n<!-- DOTFILES_AGENT_END -->\n")
        (self.live / ".codex/config.toml").write_text(
            '[mcp_servers.serena]\ncommand="uvx"\n[mcp_servers.keep]\ncommand="true"\n'
            '[model_providers.keep]\nenv_key="FIXTURE_KEY_NAME"\n')
        settings = self.live / ".claude/settings.json"
        settings.write_text(json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "fixture-preserved"},
                                       "enabledPlugins": {"serena@official": True, "keep@official": True}}))
        linked = self.live / ".claude.json"
        linked.write_text('{"mcpServers":{"serena":{"command":"uvx"},"keep":{"command":"true"}}}')
        linked.chmod(0o640)
        (self.home / ".claude.json").symlink_to(linked)
        config = self.live / ".config/opencode/opencode.jsonc"
        config.parent.mkdir(parents=True)
        (config.parent / "AGENTS.md").write_text(
            "personal OpenCode\n\n<!-- CODEGRAPH_START -->\nlegacy graph block\n<!-- CODEGRAPH_END -->\n\nworktree rules\n")
        config.write_text('// device config\n{"mcp":{"servers":{"serena":{"command":["uvx"]},'
                          '"keep":{"command":["true"]}},"serena":{"disabled":true}},"personal":42}')
        self.repo = self.root / "upstream"
        (self.repo / "graphify/skills/agents/references").mkdir(parents=True)
        (self.repo / "graphify/skill-agents.md").write_text("---\nname: graphify\ndescription: official fixture\n---\nBody.\n")
        (self.repo / "graphify/skills/agents/references/query.md").write_text("official reference\n")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "official fixture"], check=True)
        pin = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        (self.source / "deployment/skills.tsv").write_text(f"graphify|git|{self.repo}|main|graphify|auto\n")
        (self.source / "deployment/skills.lock.tsv").write_text(f"graphify|git|{self.repo}|{pin}|auto\n")
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("policy codec requires Chezmoi")
        self.env = dict(os.environ, HOME=str(self.home), DOTFILES_CHEZMOI_BIN=chezmoi)

    def run_policy(self, action):
        return subprocess.run(["bash", str(self.script), action, "--home", str(self.home),
                               "--live-root", str(self.live)], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def fetch(self):
        result = self.run_policy("--fetch")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_applies_preserves_and_is_idempotent(self):
        self.fetch()
        self.assertFalse((self.home / ".agents/skills/graphify").exists())
        result = self.run_policy("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        for root in (".agents/skills", ".claude/skills", ".minimax/skills", ".qoder/skills"):
            self.assertEqual((self.home / root / "graphify/SKILL.md").read_bytes(),
                             (self.repo / "graphify/skill-agents.md").read_bytes())
            self.assertEqual((self.home / root / "graphify/references/query.md").read_text(), "official reference\n")
            self.assertFalse((self.home / root / "pubmed-database").exists())
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(settings["env"]["ANTHROPIC_AUTH_TOKEN"], "fixture-preserved")
        self.assertEqual(settings["enabledPlugins"], {"serena@official": False, "keep@official": True,
                                                    "serena@claude-plugins-official": False})
        self.assertTrue((self.home / ".claude.json").is_symlink())
        linked = json.loads((self.home / ".claude.json").read_text())
        self.assertEqual(set(linked["mcpServers"]), {"keep"})
        config = json.loads((self.home / ".config/opencode/opencode.jsonc").read_text())
        self.assertEqual(config["personal"], 42)
        self.assertEqual(set(config["mcp"]["servers"]), {"keep"})
        self.assertNotIn("serena", config["mcp"])
        codex = (self.home / ".codex/config.toml").read_text()
        self.assertNotIn("mcp_servers.serena", codex)
        self.assertIn("FIXTURE_KEY_NAME", codex)
        self.assertFalse((self.home / ".kimi-code/AGENTS.md").exists())
        instructions = (self.home / ".codex/AGENTS.md").read_text()
        self.assertIn("personal rules", instructions)
        self.assertEqual(instructions.count("<!-- CODEGRAPH_START -->"), 1)
        self.assertIn("Disabled integrations", instructions)
        self.assertIn("personal OpenCode\n\n\n\nworktree rules",
                      (self.home / ".config/opencode/AGENTS.md").read_text())
        backups = self.live / ".local/state/dotfiles/disabled-integrations"
        journal = next(backups.glob("files.*/restore.tsv")).read_text()
        self.assertTrue(any(row.startswith(str(self.home / ".claude.json") + "|") and row.endswith("|640")
                            for row in journal.splitlines()))
        saved = list(backups.glob("skills.*/.agents/skills/pubmed-database/helper.sh"))
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].stat().st_mode & 0o111)
        self.assertEqual(saved[0].read_text(), "#!/bin/sh\nexit 0\n")
        restored = self.root / "restored-helper"
        shutil.copy2(saved[0], restored)
        self.assertEqual(restored.read_bytes(), saved[0].read_bytes())
        self.assertEqual(restored.stat().st_mode & 0o777, 0o755)
        before = sorted(str(p) for p in backups.rglob("*"))
        second = self.run_policy("--apply")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(before, sorted(str(p) for p in backups.rglob("*")))
        checked = self.run_policy("--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_bad_config_changes_nothing_and_keeps_disabled_resources(self):
        self.fetch()
        (self.live / ".claude/settings.json").write_text("invalid JSON")
        original = (self.live / ".codex/AGENTS.md").read_bytes()
        result = self.run_policy("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no settings have been written", result.stderr)
        self.assertEqual((self.live / ".codex/AGENTS.md").read_bytes(), original)
        self.assertTrue((self.live / ".agents/skills/pubmed-database").is_dir())
        self.assertFalse((self.live / ".agents/skills/graphify").exists())

    def test_escape_is_rejected_before_writes(self):
        self.fetch()
        target = self.live / ".codex/AGENTS.md"
        target.unlink()
        outside = self.root / "outside"
        outside.write_text("untouched")
        target.symlink_to(outside)
        result = self.run_policy("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes live tree", result.stderr)
        self.assertEqual(outside.read_text(), "untouched")

    def test_offline_apply_requires_prefetched_source(self):
        result = self.run_policy("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run --fetch once", result.stderr)
        self.assertTrue((self.home / ".agents/skills/pubmed-database").exists())

    def test_reintroduced_disabled_skill_is_quarantined_again(self):
        self.fetch()
        applied = self.run_policy("--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        path = self.home / ".pi/agent/skills/pubmed-database"
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text("reintroduced bytes")
        result = self.run_policy("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(path.exists())
        backups = list((self.live / ".local/state/dotfiles/disabled-integrations").glob(
            "skills.*/.pi/agent/skills/pubmed-database/SKILL.md"))
        self.assertEqual([p.read_text() for p in backups], ["reintroduced bytes"])

    def test_disabled_client_symlink_is_moved_without_following_it(self):
        self.fetch()
        alias = self.live / ".claude/skills/pubmed-database"
        shutil.rmtree(alias)
        original_target = self.live / ".agents/skills/pubmed-database"
        alias.symlink_to(original_target)
        result = self.run_policy("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Python 3.10's literal-ending glob omits dangling backup symlinks.
        backups = [batch / ".claude/skills/pubmed-database"
                   for batch in (self.live / ".local/state/dotfiles/disabled-integrations").glob("skills.*")
                   if (batch / ".claude/skills/pubmed-database").is_symlink()]
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].is_symlink())
        self.assertEqual(os.readlink(backups[0]), str(original_target))
        self.assertFalse(alias.is_symlink())


if __name__ == "__main__":
    unittest.main()
