"""The installed-library check must reject missing real skills and bad metadata."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from urllib.parse import quote

from installed_skill_discovery import discover_installed, selected_inventory, verify_names, verify_records, private_client_environment
from fixtures.skill_discovery import opencode_skills, qoder_skill_records, resolve_skill_path
from docker_ubuntu import artifact_hashes


class InstalledSkillDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-installed-skills-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        (self.source / "deployment/agent-payload").mkdir(parents=True)
        (self.source / "deployment/skills.tsv").write_text(
            "catalog-entry|git|https://example.invalid/skills|main|skill|auto\n"
            "unselected|git|https://example.invalid/skills|main|other|optional\n")
        (self.source / "deployment/skills.lock.tsv").write_text(
            "catalog-entry|git|https://example.invalid/skills|" + "a" * 40 + "|auto\n"
            "unselected|git|https://example.invalid/skills|" + "a" * 40 + "|optional\n")
        (self.source / "deployment/agent-payload/targets.tsv").write_text(
            "tree|skills|.agents/skills\ntree|skills|.claude/skills\n")
        self.home = self.root / "device with spaces"
        state = self.home / ".local/state/dotfiles/skills.lock.tsv"
        state.parent.mkdir(parents=True)
        state.write_text("catalog-entry|git|https://example.invalid/skills|" + "a" * 40 + "\n")
        self.skill = self.home / ".agents/skills/catalog-entry/SKILL.md"
        self.adapter = self.home / ".claude/skills/catalog-entry/SKILL.md"
        for path in (self.skill, self.adapter):
            path.parent.mkdir(parents=True)
            path.write_text("---\nname: metadata-name\ndescription: A real selected skill.\n"
                            "disable-model-invocation: true\n---\nBody\n")

    @unittest.skipUnless(shutil.which("ruby"), "independent skill YAML oracle requires Ruby")
    def test_inventory_uses_selected_pins_and_metadata_name_and_manual_flag(self):
        inventory = selected_inventory(self.home, self.source)
        self.assertEqual(set(inventory), {"metadata-name"})
        self.assertEqual(inventory["metadata-name"]["catalog_name"], "catalog-entry")
        self.assertTrue(inventory["metadata-name"]["disable_model_invocation"])
        self.assertEqual(inventory["metadata-name"]["path"], str(self.skill.resolve()))

    def test_missing_selected_skill_and_different_adapter_are_not_silently_dropped(self):
        self.skill.unlink()
        with self.assertRaisesRegex(RuntimeError, "missing regular selected skill"):
            selected_inventory(self.home, self.source)
        self.skill.write_bytes(self.adapter.read_bytes())
        self.adapter.write_text("different metadata\n")
        with self.assertRaisesRegex(RuntimeError, "adapter differs"):
            selected_inventory(self.home, self.source)

    def test_discovery_of_fixture_names_cannot_substitute_for_selected_inventory(self):
        with self.assertRaisesRegex(RuntimeError, "real-second"):
            verify_names({"real-first", "real-second"}, {"real-first", "tdd", "implement-spec"})

    def test_discovery_name_must_point_at_the_installed_skill_file(self):
        inventory = {"metadata-name": {"path": str(self.skill.resolve())}}
        result = verify_records(inventory, [{"name": "metadata-name", "file": str(self.skill)}],
                                home=self.home, name_key="name", path_key="file")
        self.assertEqual(result["selected_count"], 1)
        with self.assertRaisesRegex(RuntimeError, "path does not match"):
            verify_records(inventory, [{"name": "metadata-name", "file": str(self.adapter)}],
                           home=self.home, name_key="name", path_key="file")

    def test_private_configuration_never_copies_auth_or_skill_bytes(self):
        config = self.home / ".codex"
        config.mkdir()
        (config / "config.toml").write_text('model = "fixture"\n')
        (config / "AGENTS.md").write_text("rendered instructions\n")
        (config / "auth.json").write_text('{"synthetic-credential":"excluded"}\n')
        env = private_client_environment("codex", self.home, self.root / "scratch", {})
        copied = Path(env["CODEX_HOME"])
        self.assertEqual({path.name for path in copied.iterdir()}, {"config.toml", "AGENTS.md"})
        self.assertEqual(env["HOME"], str(self.home))
        self.assertEqual((copied / "config.toml").read_bytes(), (config / "config.toml").read_bytes())

    def test_opencode_uses_private_copied_config_and_keeps_installed_skill_paths(self):
        config = self.home / ".config/opencode"
        config.mkdir(parents=True)
        (config / "opencode.jsonc").write_text(json.dumps({"skills": [str(self.skill.parent.parent)]}))
        (config / "AGENTS.md").write_text("rendered instructions\n")
        env = private_client_environment("opencode", self.home, self.root / "scratch", {})
        copied = Path(env["OPENCODE_CONFIG"])
        self.assertNotEqual(copied.parent, config)
        self.assertEqual(copied.parent, Path(env["OPENCODE_CONFIG_DIR"]))
        self.assertEqual(copied.read_bytes(), (config / "opencode.jsonc").read_bytes())
        with mock.patch("fixtures.skill_discovery.subprocess.Popen") as start, \
                mock.patch("fixtures.skill_discovery.socket.socket") as listener, \
                mock.patch("fixtures.skill_discovery.stop_client"):
            listener.return_value.__enter__.return_value.getsockname.return_value = ("127.0.0.1", 4567)
            start.return_value.poll.return_value = 0
            opencode_skills("unused", home=self.home, cwd=self.root, env=env,
                            log=self.root / "opencode.log", expected=set())
        self.assertEqual(start.call_args.kwargs["env"]["OPENCODE_CONFIG"], str(copied))
        self.assertEqual(start.call_args.kwargs["env"]["OPENCODE_CONFIG_DIR"], str(copied.parent))

    def test_native_file_and_home_uris_preserve_spaces_and_unicode(self):
        path = (self.skill.parent / "资源 with space.md").resolve()
        self.assertEqual(resolve_skill_path(path.as_uri(), self.home), path)
        suffix = "技能 with space/SKILL.md"
        for prefix in ("file://~/", "file:///~/"):
            self.assertEqual(resolve_skill_path(prefix + quote(suffix), self.home), (self.home / suffix).resolve())

    def test_runtime_symlinks_are_removed_before_artifact_hashing_even_on_client_failure(self):
        config = self.home / ".claude"
        (config / "settings.json").write_text("{}\n")
        (config / "CLAUDE.md").write_text("rendered instructions\n")
        inventory = {"metadata-name": {"path": str(self.skill.resolve()), "disable_model_invocation": True}}
        pi = {"skills": [{"name": "metadata-name", "filePath": str(self.skill), "disableModelInvocation": True}], "prompt": ""}
        opencode = [{"id": "metadata-name", "path": str(self.skill), "autoinvoke": False}]
        qoder = [{"name": "metadata-name", "path": str(self.skill)}]
        tools = dict.fromkeys(("pi_module", "node", "opencode", "codex", "claude", "kimi", "qoder"), "unused")
        for fail in (False, True):
            with self.subTest(client_failure=fail):
                runtime_links = []
                def environment(client, home, runtime, base):
                    return private_client_environment(client, home, runtime, base) if client == "claude" else {}
                def catalog(client, _binary, *, cwd, env, log):
                    Path(log).write_text("command catalog\n")
                    if client == "claude":
                        link = Path(env["CLAUDE_CONFIG_DIR"]) / "skills"
                        self.assertTrue(link.is_symlink())
                        runtime_links.append(link)
                        if fail:
                            raise RuntimeError("synthetic client failure")
                    return set(inventory)
                artifacts = self.root / ("failed-artifacts" if fail else "passed-artifacts")
                with mock.patch("installed_skill_discovery.selected_inventory", return_value=inventory), \
                        mock.patch("installed_skill_discovery.private_client_environment", side_effect=environment), \
                        mock.patch("installed_skill_discovery.pi_resources", return_value=pi), \
                        mock.patch("installed_skill_discovery.opencode_skills", return_value=opencode), \
                        mock.patch("installed_skill_discovery.codex_prompt", return_value=""), \
                        mock.patch("installed_skill_discovery.command_catalog", side_effect=catalog), \
                        mock.patch("installed_skill_discovery.qoder_skills", return_value=qoder):
                    result = discover_installed(self.home, artifacts, tools, {})
                self.assertEqual(result["status"], "failed" if fail else "passed", result["clients"])
                self.assertTrue(runtime_links)
                self.assertTrue(all(not link.is_symlink() and not link.exists() for link in runtime_links))
                (artifacts / "report.json").write_text(json.dumps(result))
                self.assertEqual(set(artifact_hashes(artifacts)), {"report.json", "claude.log", "kimi.log"})

    def test_each_client_must_discover_real_metadata_with_its_supported_projection(self):
        inventory = {
            name: {"path": str((self.home / ".agents/skills" / name / "SKILL.md").resolve()),
                   "disable_model_invocation": disabled}
            for name, disabled in (("real-auto", False), ("real-manual-one", True), ("real-manual-two", True))}
        pi = {"skills": [{"name": name, "filePath": item["path"],
                          "disableModelInvocation": item["disable_model_invocation"]}
                         for name, item in inventory.items()],
              "prompt": "<name>real-auto</name>"}
        opencode = [{"id": name, "path": item["path"],
                     **({"autoinvoke": False} if item["disable_model_invocation"] else {})}
                    for name, item in inventory.items()]
        qoder = [{"name": name, "path": item["path"]} for name, item in inventory.items()]
        tools = dict.fromkeys(("pi_module", "node", "opencode", "codex", "claude", "kimi", "qoder"), "unused")
        with mock.patch("installed_skill_discovery.selected_inventory", return_value=inventory), \
                mock.patch("installed_skill_discovery.private_client_environment", return_value={}), \
                mock.patch("installed_skill_discovery.pi_resources", return_value=pi), \
                mock.patch("installed_skill_discovery.opencode_skills", return_value=opencode), \
                mock.patch("installed_skill_discovery.codex_prompt", return_value="- real-auto: description"), \
                mock.patch("installed_skill_discovery.command_catalog", return_value=set(inventory)), \
                mock.patch("installed_skill_discovery.qoder_skills", return_value=qoder):
            result = discover_installed(self.home, self.root / "first", tools, {})
            self.assertEqual(result["status"], "passed", result["clients"])
            self.assertEqual(len(result["manual_only_names"]), 2)
            self.assertEqual(result["clients"]["codex"]["expected_names"], ["real-auto"])
            self.assertEqual(result["clients"]["qoder"]["selected_count"], 3)
            self.assertEqual(result["clients"]["opencode"]["automatic_flag_not_exposed_names"], ["real-auto"])
            opencode[1].pop("autoinvoke")
            result = discover_installed(self.home, self.root / "missing-manual-metadata", tools, {})
            self.assertEqual(result["status"], "failed")
            self.assertIn("manual invocation metadata is missing", result["clients"]["opencode"]["error"])
            opencode[1]["autoinvoke"] = False
            qoder.pop()
            result = discover_installed(self.home, self.root / "missing", tools, {})
            self.assertEqual(result["status"], "failed")
            self.assertIn("real-manual-two", result["clients"]["qoder"]["error"])

    def test_qoder_records_keep_names_and_locations_instead_of_description_mentions(self):
        records = qoder_skill_records("Discovered Agent Skills:\n\nmetadata-name [Enabled]\n"
                                      " Description: mentions another-name.\n"
                                      " Location: /path with spaces/SKILL.md\n")
        self.assertEqual(records, [{"name": "metadata-name", "enabled": True,
                                    "path": "/path with spaces/SKILL.md"}])
        with self.assertRaisesRegex(ValueError, "no location"):
            qoder_skill_records("metadata-name [Enabled]\nother [Enabled]\n Location: /other\n")
        with self.assertRaisesRegex(ValueError, "no name"):
            qoder_skill_records(" Location: /other\n")
