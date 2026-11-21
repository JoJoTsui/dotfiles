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
            'check_for_update_on_startup=true\n[mcp_servers.serena]\ncommand="uvx"\n[mcp_servers.keep]\ncommand="true"\n'
            '[model_providers.keep]\nenv_key="FIXTURE_KEY_NAME"\n')
        (self.live / ".kimi-code/tui.toml").write_text('theme="personal"\n[upgrade]\nauto_install=true\n')
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
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.write_stat_shim()
        self.env = dict(os.environ, HOME=str(self.home), DOTFILES_CHEZMOI_BIN=chezmoi,
                        PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}")

    def write_stat_shim(self):
        """The adapter records modes with GNU `stat -c`; macOS has BSD stat.

        The shim answers the one format the adapter uses and passes every
        other invocation to the host's stat, so the fixture runs on both
        platforms.
        """
        real = shutil.which("stat")
        shim = self.bin / "stat"
        shim.write_text(
            "#!/bin/sh\n"
            f"real={real}\n"
            "if \"$real\" -c '%a' /dev/null >/dev/null 2>&1; then\n"
            "    exec \"$real\" \"$@\"\n"
            "fi\n"
            "if [ \"$1\" = '-c' ] && [ \"$2\" = '%a' ]; then\n"
            "    shift 2\n"
            "    for target in \"$@\"; do\n"
            "        \"$real\" -f '%Lp' \"$target\"\n"
            "    done\n"
            "    exit 0\n"
            "fi\n"
            "exec \"$real\" \"$@\"\n")
        shim.chmod(0o755)

    def write_failing_cp_shim(self):
        """Fail a copy of the staged skill tree, so a publish cannot land.

        The shim only refuses the copy of the tree the adapter staged, so
        every other copy of the apply still runs.
        """
        real = shutil.which("cp")
        shim = self.bin / "cp"
        shim.write_text(
            "#!/bin/sh\n"
            f"real={real}\n"
            "for arg in \"$@\"; do\n"
            "    case \"$arg\" in\n"
            "        *agent-integrations.*/skills/*)\n"
            "            echo 'cp: injected copy failure' >&2\n"
            "            exit 1\n"
            "            ;;\n"
            "    esac\n"
            "done\n"
            "exec \"$real\" \"$@\"\n")
        shim.chmod(0o755)

    def run_policy(self, action, *options):
        return subprocess.run(["bash", str(self.script), action, "--home", str(self.home),
                               "--live-root", str(self.live), *options], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def stage_t9k_sources(self):
        data = Path("dot_local/share/dotfiles/t9k-automation")
        shutil.copytree(SOURCE / data, self.source / data)
        runner = Path("dot_local/bin/executable_t9k-run-job")
        (self.source / runner.parent).mkdir(parents=True)
        shutil.copy2(SOURCE / runner, self.source / runner)
        self.env["DOTFILES_CHEZMOI_BIN"] = str(self.root / "missing-chezmoi")

    def test_t9k_jobs_apply_offline_and_preserve_global_policy(self):
        self.stage_t9k_sources()
        runner = self.live / ".local/bin/t9k-run-job"
        data = self.live / ".local/share/dotfiles/t9k-automation"
        state = self.live / ".local/state/dotfiles/t9k-automation"
        instructions = self.live / ".codex/AGENTS.md"
        personal = "personal\n<!-- DOTFILES_AGENT_START -->\nexisting policy\n<!-- DOTFILES_AGENT_END -->\n"
        instructions.write_text(personal)
        instructions.chmod(0o640)
        config = self.live / ".codex/config.toml"
        original_config = config.read_bytes()
        paths_before = set(self.live.rglob("*"))
        check = self.run_policy("--check", "--t9k-jobs")
        self.assertEqual(check.returncode, 1)
        self.assertIn("DRIFT .local/bin/t9k-run-job", check.stdout)
        preview = self.run_policy("--dry-run", "--t9k-jobs")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("WOULD WRITE .codex/AGENTS.md", preview.stdout)
        self.assertEqual(set(self.live.rglob("*")), paths_before)
        self.assertEqual(instructions.read_text(), personal)

        applied = self.run_policy("--apply", "--t9k-jobs")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(runner.is_file())
        self.assertEqual(runner.stat().st_mode & 0o777, 0o755)
        self.assertEqual({path.name for path in data.iterdir()}, {"README.md", "kubeconfig-incluster.yaml"})
        self.assertTrue(instructions.read_text().startswith(personal))
        self.assertEqual(instructions.read_text().count("<!-- DOTFILES_T9K_JOBS_START -->"), 1)
        self.assertIn("t9k-automation/README.md", instructions.read_text())
        self.assertEqual(instructions.stat().st_mode & 0o777, 0o640)
        self.assertEqual(config.read_bytes(), original_config)
        self.assertTrue((self.live / ".agents/skills/pubmed-database/SKILL.md").is_file())
        journal, = state.glob("files.*/restore.tsv")
        self.assertIn("t9k-run-job|NEW|-", journal.read_text())
        self.assertEqual((journal.parent / ".codex/AGENTS.md").read_text(), personal)

        clean = self.run_policy("--check", "--t9k-jobs")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        repeated = self.run_policy("--apply", "--t9k-jobs")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(list(state.glob("*/restore.tsv")), [journal])

        runner.chmod(0o644)
        drift = self.run_policy("--check", "--t9k-jobs")
        self.assertEqual(drift.returncode, 1)
        self.assertIn("DRIFT .local/bin/t9k-run-job", drift.stdout)
        repair = self.run_policy("--apply", "--t9k-jobs")
        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertEqual(runner.stat().st_mode & 0o777, 0o755)

    def test_t9k_jobs_refuse_escaped_instructions_before_writing_files(self):
        self.stage_t9k_sources()
        instructions = self.live / ".qoder/AGENTS.md"
        outside = self.root / "outside.md"
        outside.write_text("outside live tree\n")
        instructions.symlink_to(outside)
        refused = self.run_policy("--apply", "--t9k-jobs")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("destination escapes live tree", refused.stderr)
        self.assertEqual(outside.read_text(), "outside live tree\n")
        self.assertTrue(instructions.is_symlink())
        self.assertFalse((self.live / ".local/bin/t9k-run-job").exists())
        self.assertFalse((self.live / ".local/share/dotfiles/t9k-automation").exists())

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
        self.assertEqual(settings["env"]["DISABLE_AUTOUPDATER"], "1")
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
        self.assertIn("check_for_update_on_startup = false", codex)
        tui = (self.home / ".kimi-code/tui.toml").read_text()
        self.assertIn("auto_install = false", tui)
        self.assertIn('theme = "personal"', tui)
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

    def test_device_owned_graphify_entries_are_preserved(self):
        """A device skill with the selected name keeps its own bytes.

        The adapter copies a selected skill as a unit, so a device directory
        whose bytes differ is preserved and reported instead of being
        overlaid, and a device link is never followed. The unrelated actions
        of the same apply still land.
        """
        device = self.live / ".agents/skills/graphify"
        device.mkdir(parents=True)
        (device / "SKILL.md").write_text("---\nname: graphify\ndescription: device copy\n---\nDevice body.\n")
        (device / "references").mkdir()
        (device / "references" / "query.md").write_text("device reference\n")
        (device / "device-only.txt").write_text("device bytes\n")
        linked = self.live / ".device/graphify"
        linked.parent.mkdir(parents=True)
        linked.mkdir()
        (linked / "SKILL.md").write_text("device link bytes\n")
        (self.live / ".claude/skills/graphify").symlink_to(linked)

        self.fetch()
        result = self.run_policy("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)

        # The differing device directory survives as a unit.
        self.assertEqual((device / "SKILL.md").read_text(),
                         "---\nname: graphify\ndescription: device copy\n---\nDevice body.\n")
        self.assertEqual((device / "references" / "query.md").read_text(), "device reference\n")
        self.assertEqual((device / "device-only.txt").read_text(), "device bytes\n")
        self.assertNotIn("official fixture", (device / "SKILL.md").read_text())
        # The device link is preserved and never written through.
        alias = self.live / ".claude/skills/graphify"
        self.assertTrue(alias.is_symlink())
        self.assertEqual(os.readlink(alias), str(linked))
        self.assertEqual((linked / "SKILL.md").read_text(), "device link bytes\n")
        # The preservation is reported for the skill and its root.
        self.assertIn("preserved skill graphify in .agents/skills", result.stderr)
        self.assertIn("preserved skill graphify in .claude/skills", result.stderr)

        # The unrelated actions of the same apply still land.
        instructions = (self.home / ".codex/AGENTS.md").read_text()
        self.assertIn("personal rules", instructions)
        self.assertIn("Disabled integrations", instructions)
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(settings["env"]["DISABLE_AUTOUPDATER"], "1")
        self.assertEqual(settings["env"]["ANTHROPIC_AUTH_TOKEN"], "fixture-preserved")

        # A preserved device entry is reported, and it is not drift: the
        # deployment has nothing to change there.
        checked = self.run_policy("--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("preserved skill graphify in .agents/skills", checked.stderr)

    def test_owned_graphify_copy_is_refreshed_and_backed_up(self):
        """A skill the deployment wrote belongs to the deployment.

        A later apply refreshes the owned copy and keeps the replaced bytes
        in the recovery batch.
        """
        self.fetch()
        first = self.run_policy("--apply")
        self.assertEqual(first.returncode, 0, first.stderr)
        skill = self.live / ".agents/skills/graphify/SKILL.md"
        skill.write_text("---\nname: graphify\ndescription: edited\n---\nEdited.\n")
        second = self.run_policy("--apply")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(skill.read_bytes(), (self.repo / "graphify/skill-agents.md").read_bytes())
        backups = list((self.live / ".local/state/dotfiles/disabled-integrations").glob(
            "files.*/.agents/skills/graphify/SKILL.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "---\nname: graphify\ndescription: edited\n---\nEdited.\n")

    def test_outside_inventory_symlink_never_authorizes_an_overwrite(self):
        """An inventory outside the live tree cannot own a device directory.

        The inventory decides which skill directories the deployment owns, so
        its path is validated before that ownership is read: a symlink that
        leaves the live tree is refused, and the device directory keeps its
        own bytes.
        """
        device = self.live / ".agents/skills/graphify"
        device.mkdir(parents=True)
        (device / "SKILL.md").write_text("---\nname: graphify\ndescription: device copy\n---\nDevice body.\n")
        outside = self.root / "outside-inventory.tsv"
        outside.write_text("graphify|.agents/skills\n")
        state = self.live / ".local/state/dotfiles"
        state.mkdir(parents=True, exist_ok=True)
        (state / "managed-skills.tsv").symlink_to(outside)

        self.fetch()
        result = self.run_policy("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes live tree", result.stderr)
        # The device directory keeps its own bytes, and the outside record is
        # left untouched.
        self.assertIn("Device body.", (device / "SKILL.md").read_text())
        self.assertEqual(outside.read_text(), "graphify|.agents/skills\n")

    def test_failed_copy_keeps_the_active_owned_skill(self):
        """A failed publish leaves the bytes the deployment owns in place.

        The candidate is staged beside the canonical destination before the
        owned directory is touched, so a copy that fails never removes the
        active skill.
        """
        self.fetch()
        first = self.run_policy("--apply")
        self.assertEqual(first.returncode, 0, first.stderr)
        skill = self.live / ".agents/skills/graphify/SKILL.md"
        skill.write_text("---\nname: graphify\ndescription: edited\n---\nEdited.\n")

        self.write_failing_cp_shim()
        result = self.run_policy("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot copy the skill graphify", result.stderr)
        # The owned skill is still there with its own bytes.
        self.assertTrue((self.live / ".agents/skills/graphify").is_dir())
        self.assertEqual(skill.read_text(), "---\nname: graphify\ndescription: edited\n---\nEdited.\n")
        # The staging leaves no residue behind.
        self.assertEqual([p.name for p in (self.live / ".agents/skills").iterdir()
                          if p.name.startswith(".agent-policy")], [])

    def test_inventory_rollback_withdraws_the_managed_row(self):
        """The inventory is recoverable, so a rollback withdraws the row.

        The recovery journal covers the shared inventory, so a rollback of a
        new skill also withdraws the row that recorded it. A later apply then
        treats a new device directory as device content instead of
        overwriting it.
        """
        self.fetch()
        first = self.run_policy("--apply")
        self.assertEqual(first.returncode, 0, first.stderr)
        inventory = self.home / ".local/state/dotfiles/managed-skills.tsv"
        self.assertTrue(inventory.exists())
        self.assertIn("graphify|.agents/skills", inventory.read_text())

        batches = (self.live / ".local/state/dotfiles/disabled-integrations").glob("files.*")
        journal = next(batch / "restore.tsv" for batch in batches if (batch / "restore.tsv").exists())
        rows = [line.split("|") for line in journal.read_text().splitlines()]
        inventory_rows = [row for row in rows if row[0] == str(inventory)]
        self.assertEqual(len(inventory_rows), 1, journal.read_text())
        self.assertEqual(inventory_rows[0][1], "NEW")

        # The documented rollback: the new skill is withdrawn and the new
        # inventory is removed.
        shutil.rmtree(self.home / ".agents/skills/graphify")
        inventory.unlink()

        device = self.live / ".agents/skills/graphify"
        device.mkdir(parents=True)
        (device / "SKILL.md").write_text("---\nname: graphify\ndescription: device copy\n---\nDevice body.\n")

        result = self.run_policy("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        # The new device directory keeps its own bytes.
        self.assertIn("Device body.", (device / "SKILL.md").read_text())
        self.assertIn("preserved skill graphify in .agents/skills", result.stderr)

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
