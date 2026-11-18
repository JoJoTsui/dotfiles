"""Existing-device settings rehearsal: private, redacted, allow-listed projection.

The seam is the public rehearsal helper and the public bootstrap. Every
fixture is fabricated; no real device settings, credentials, or sessions are
read here.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from fixtures.skills import write_skill_library

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

SOURCE = Path(__file__).resolve().parents[1]
HELPER = SOURCE / "deployment/rehearse_settings.py"
MANIFEST = SOURCE / "deployment/rehearsal/existing-mac-inputs.tsv"

DEVICE_TOKEN = "synthetic-device-token"
DEVICE_API_KEY = "synthetic-device-api-key"

# A trust digest is an integrity value, not a credential: it carries no
# secret, and it has the credential shape of a long hexadecimal string.
SYNTHETIC_DIGEST = "sha256:" + "0123456789abcdef" * 4
SYNTHETIC_CONTENT_DIGEST = "sha256:" + "fedcba9876543210" * 4
SYNTHETIC_UNKNOWN_VALUE = "sk-syntheticunknownvalue123456"

# A fabricated Codex configuration that carries the device's hook trust
# digests next to ordinary settings.
DIGEST_CODEX_CONFIG = (
    'model = "device-model"\n'
    '[hooks.state."synthetic-hook"]\n'
    'trusted_hash = "%s"\n'
    'trusted_content_hash = "%s"\n'
    'state = "trusted"\n'
) % (SYNTHETIC_DIGEST, SYNTHETIC_CONTENT_DIGEST)

DEVICE_SETTINGS = {
    ".claude/settings.json": json.dumps({
        "model": "device-model",
        "alwaysThinkingEnabled": False,
        "env": {"ANTHROPIC_AUTH_TOKEN": DEVICE_TOKEN, "DEVICE_ENV": "keep"},
        "hooks": {"Stop": []},
    }),
    ".codex/config.toml": (
        'model = "device-model"\n'
        '[projects."/synthetic/project"]\n'
        'trust_level = "trusted"\n'
        '[mcp_servers.device]\n'
        'command = "device-mcp"\n'
        '[model_providers.device]\n'
        'name = "Device"\n'
        'base_url = "http://127.0.0.1:8787/chatgpt"\n'
        'env_key = "DEVICE_API_KEY"\n'
    ),
    ".config/opencode/opencode.jsonc": (
        '// a device comment\n'
        '{"theme":"device-theme","skills":["./device-skills"],'
        '"providers":{"device":{"settings":{"apiKey":"%s"}}},'
        '"mcp":{"servers":{"device":{"type":"local","command":["device-mcp"]}}}}\n' % DEVICE_API_KEY
    ),
    ".pi/agent/settings.json": json.dumps({
        "theme": "device-theme",
        "skills": ["./device-skills"],
        "deviceSetting": False,
    }),
    ".claude/CLAUDE.local.md": "# device instructions\n\nKeep the device preference.\n",
    ".config/ghostty/config.local.ghostty": "# device terminal preference\nfont-size = 15\n",
    ".codex/hooks.json": json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "Bash",
                                  "hooks": [{"type": "command", "command": "device-policy"}]}]},
    }),
}


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-rehearsal-")
        self.addCleanup(self.temporary.cleanup)
        # The scratch root must be canonical: macOS hands out an aliased
        # temporary path (/var/... -> /private/var/...) and the helper refuses
        # a linked output path on purpose.
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "device"
        self.projection = self.root / "projection"
        self.report = self.root / "report.json"
        self.manifest = self.root / "inputs.tsv"
        self.skills = write_skill_library(self.root / "skills-fixture")
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        for relative, content in DEVICE_SETTINGS.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def write_manifest(self, lines):
        self.manifest.write_text("\n".join(lines) + "\n")
        return self.manifest

    def project(self, *extra, projection=None, report=None):
        return subprocess.run(
            [sys.executable, str(HELPER),
             "--source-home", str(self.home),
             "--manifest", str(self.manifest),
             "--projection", str(projection if projection is not None else self.projection),
             "--report", str(report if report is not None else self.report), *extra],
            capture_output=True, text=True, timeout=60)

    def write_device_file(self, relative, content):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def source_fingerprints(self):
        fingerprints = {}
        for relative in DEVICE_SETTINGS:
            path = self.home / relative
            status = path.stat()
            fingerprints[relative] = (path.read_bytes(),
                                      status.st_mode & 0o7777,
                                      status.st_mtime_ns)
        return fingerprints

    def test_projection_redacts_credentials_and_keeps_unrelated_settings(self):
        self.write_manifest([
            ".claude/settings.json\tjson\trequired",
            ".codex/config.toml\ttoml\trequired",
            ".config/opencode/opencode.jsonc\tjsonc\toptional",
            ".pi/agent/settings.json\tjson\trequired",
        ])
        before = self.source_fingerprints()
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        claude = json.loads((self.projection / ".claude/settings.json").read_text())
        self.assertEqual(claude["env"]["ANTHROPIC_AUTH_TOKEN"], "<redacted>")
        self.assertEqual(claude["env"]["DEVICE_ENV"], "keep")
        self.assertEqual(claude["model"], "device-model")
        self.assertFalse(claude["alwaysThinkingEnabled"])
        self.assertEqual(claude["hooks"], {"Stop": []})

        codex = tomllib.loads((self.projection / ".codex/config.toml").read_text())
        self.assertEqual(codex["model"], "device-model")
        self.assertEqual(codex["projects"]["/synthetic/project"]["trust_level"], "trusted")
        self.assertEqual(codex["mcp_servers"]["device"]["command"], "device-mcp")
        self.assertEqual(codex["model_providers"]["device"]["base_url"],
                         "http://127.0.0.1:8787/chatgpt")
        # A provider's environment-variable name is not a credential value.
        self.assertEqual(codex["model_providers"]["device"]["env_key"], "DEVICE_API_KEY")

        opencode = json.loads((self.projection / ".config/opencode/opencode.jsonc").read_text())
        self.assertEqual(opencode["theme"], "device-theme")
        self.assertEqual(opencode["skills"], ["./device-skills"])
        self.assertEqual(opencode["providers"]["device"]["settings"]["apiKey"], "<redacted>")

        pi = json.loads((self.projection / ".pi/agent/settings.json").read_text())
        self.assertEqual(pi["theme"], "device-theme")
        self.assertEqual(pi["skills"], ["./device-skills"])
        self.assertFalse(pi["deviceSetting"])

        projected = b"".join(path.read_bytes() for path in sorted(self.projection.rglob("*"))
                             if path.is_file())
        self.assertNotIn(DEVICE_TOKEN.encode(), projected)
        self.assertNotIn(DEVICE_API_KEY.encode(), projected)

        # The device keeps its bytes, its mode, and its modification time.
        self.assertEqual(self.source_fingerprints(), before)

    def test_report_proves_completeness_without_any_value(self):
        self.write_manifest([
            ".claude/settings.json\tjson\trequired",
            ".codex/config.toml\ttoml\trequired",
            ".config/opencode/opencode.jsonc\tjsonc\toptional",
            ".pi/agent/settings.json\tjson\trequired",
        ])
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        report = json.loads(self.report.read_text())
        self.assertTrue(report["source_unchanged"])
        self.assertEqual(report["totals"]["files"], 4)
        self.assertEqual(len(report["files"]), 4)
        for entry in report["files"]:
            self.assertEqual(entry["status"], "projected")
            # Redaction replaces a value in place, so the projected document
            # keeps every record of the source document.
            self.assertEqual(entry["projected"]["records"], entry["source"]["records"])
            self.assertEqual(entry["source"]["sha256"], entry["source_after"]["sha256"])
            self.assertEqual(entry["source"]["mode"], entry["source_after"]["mode"])
            self.assertEqual(entry["source"]["mtime_ns"], entry["source_after"]["mtime_ns"])
            self.assertEqual(entry["projected"]["sha256"], self.sha256(
                self.projection / entry["path"]))
        self.assertEqual(report["totals"]["projected_records"],
                         report["totals"]["records"])
        self.assertEqual(report["totals"]["redacted_fields"], 2)

        text = self.report.read_text()
        self.assertNotIn(DEVICE_TOKEN, text)
        self.assertNotIn(DEVICE_API_KEY, text)
        self.assertNotIn("device-model", text)

        self.assertEqual(self.projection.stat().st_mode & 0o777, 0o700)
        for entry in report["files"]:
            mode = (self.projection / entry["path"]).stat().st_mode & 0o777
            self.assertEqual(mode, 0o600, entry["path"])

    def sha256(self, path):
        import hashlib
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_unknown_credential_shaped_value_fails_closed_without_artifacts(self):
        unknown_value = "sk-syntheticunknownvalue123456"
        path = self.home / ".pi/agent/settings.json"
        document = json.loads(path.read_text())
        document["deviceNote"] = unknown_value
        path.write_text(json.dumps(document))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        before = self.source_fingerprints()

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential-shaped", result.stderr)
        self.assertNotIn(unknown_value, result.stdout + result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())
        self.assertEqual(self.source_fingerprints(), before)

    def test_unknown_credential_shaped_value_is_omitted_with_a_count(self):
        unknown_value = "sk-syntheticunknownvalue123456"
        path = self.home / ".pi/agent/settings.json"
        document = json.loads(path.read_text())
        document["deviceNote"] = unknown_value
        path.write_text(json.dumps(document))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])

        result = self.project("--unknown-credential-policy", "omit")
        self.assertEqual(result.returncode, 0, result.stderr)
        projected = json.loads((self.projection / ".pi/agent/settings.json").read_text())
        self.assertNotIn("deviceNote", projected)
        self.assertEqual(projected["theme"], "device-theme")

        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["omitted_fields"], 1)
        self.assertEqual(report["totals"]["unknown_credential_fields"], 1)
        entry = report["files"][0]
        self.assertEqual(entry["projected"]["records"], entry["source"]["records"] - 1)
        self.assertNotIn(unknown_value, self.report.read_text())

    def test_linked_input_is_refused(self):
        target = self.home / ".pi/agent/real-settings.json"
        target.write_text(json.dumps({"theme": "device-theme"}))
        link = self.home / ".pi/agent/settings.json"
        link.unlink()
        link.symlink_to(target)
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_linked_parent_directory_is_refused(self):
        outside = self.root / "outside-kimi"
        outside.mkdir()
        (outside / "config.toml").write_text('default_model = "device/model"\n')
        link = self.home / ".kimi-code"
        link.symlink_to(outside)
        self.write_manifest([".kimi-code/config.toml\ttoml\toptional"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertEqual((outside / "config.toml").read_text(),
                         'default_model = "device/model"\n')

    def test_linked_projection_output_is_refused(self):
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        outside = self.root / "outside"
        outside.mkdir()
        self.projection.symlink_to(outside)

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_projection_and_report_inside_the_source_home_are_refused(self):
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        inside = self.home / "projection"
        result = subprocess.run(
            [sys.executable, str(HELPER),
             "--source-home", str(self.home),
             "--manifest", str(self.manifest),
             "--projection", str(inside),
             "--report", str(self.report)],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source home", result.stderr)
        self.assertFalse(inside.exists())

        result = subprocess.run(
            [sys.executable, str(HELPER),
             "--source-home", str(self.home),
             "--manifest", str(self.manifest),
             "--projection", str(self.projection),
             "--report", str(self.home / "report.json")],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source home", result.stderr)
        self.assertFalse((self.home / "report.json").exists())

    def test_missing_required_input_fails_without_artifacts(self):
        self.write_manifest([
            ".pi/agent/settings.json\tjson\trequired",
            ".qoder/settings.json\tjson\trequired",
        ])
        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".qoder/settings.json", result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_missing_optional_input_is_recorded_as_absent(self):
        self.write_manifest([
            ".pi/agent/settings.json\tjson\trequired",
            ".qoder/settings.json\tjson\toptional",
        ])
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["files"], 1)
        absent = [entry for entry in report["files"] if entry["status"] == "absent"]
        self.assertEqual(len(absent), 1)
        self.assertEqual(absent[0]["path"], ".qoder/settings.json")
        self.assertFalse((self.projection / ".qoder/settings.json").exists())

    def test_manifest_refuses_excluded_auth_session_and_history_inputs(self):
        for excluded in (".codex/auth.json", ".claude.json",
                         ".claude/sessions/one.json",
                         ".local/share/atuin/history.db", ".config/credentials",
                         ".config/dotfiles/magpie.env"):
            self.write_manifest(["%s\tjson\trequired" % excluded])
            result = self.project()
            self.assertNotEqual(result.returncode, 0, excluded)
            self.assertIn("excluded input", result.stderr)
            self.assertFalse(self.projection.exists())

    def test_reviewed_manifest_names_only_managed_settings(self):
        entries = [line for line in MANIFEST.read_text().splitlines()
                   if line.strip() and not line.startswith("#")]
        self.assertTrue(entries)
        for entry in entries:
            path = entry.split("\t")[0]
            self.assertFalse(path.startswith("/"))
            self.assertNotIn("auth", path)
            self.assertNotIn("session", path)
            self.assertNotIn("history", path)
            self.assertNotIn("atuin", path)

        # The reviewed manifest runs as it stands against a fabricated slice.
        result = subprocess.run(
            [sys.executable, str(HELPER),
             "--source-home", str(self.home),
             "--manifest", str(MANIFEST),
             "--projection", str(self.projection),
             "--report", str(self.report)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["projected_files"], 7)
        absent = sorted(entry["path"] for entry in report["files"]
                        if entry["status"] == "absent")
        self.assertIn(".qoder/settings.json", absent)

    def deploy(self):
        """Rehearse the public deployment against the projected home."""
        if not self.chezmoi:
            self.skipTest("the rehearsal apply requires chezmoi")
        platform_name = os.environ.get("DOTFILES_TEST_PLATFORM") or (
            "macos" if sys.platform == "darwin" else "linux")
        environment = {
            "HOME": str(self.projection),
            "PATH": "/usr/bin:/bin",
            "DOTFILES_CHEZMOI_BIN": self.chezmoi,
            "DOTFILES_SKILLS_DIR": str(self.skills),
        }
        return subprocess.run(
            ["/bin/bash", str(SOURCE / "bootstrap.sh"),
             "--source", str(SOURCE),
             "--home", str(self.projection),
             "--platform", platform_name,
             "--role", os.environ.get("DOTFILES_TEST_ROLE", "workstation"),
             "--apply-only"],
            cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)

    def test_rehearsed_projection_keeps_unrelated_settings_through_the_public_bootstrap(self):
        self.write_manifest([
            ".claude/settings.json\tjson\trequired",
            ".codex/config.toml\ttoml\trequired",
            ".config/opencode/opencode.jsonc\tjsonc\toptional",
            ".pi/agent/settings.json\tjson\trequired",
            ".claude/CLAUDE.local.md\ttext\toptional",
            ".config/ghostty/config.local.ghostty\ttext\toptional",
            ".codex/hooks.json\tjson\toptional",
        ])
        before = self.source_fingerprints()
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        applied = self.deploy()
        self.assertEqual(applied.returncode, 0, applied.stderr)

        claude = json.loads((self.projection / ".claude/settings.json").read_text())
        self.assertEqual(claude["model"], "device-model")
        self.assertEqual(claude["env"]["DEVICE_ENV"], "keep")
        self.assertEqual(claude["env"]["ANTHROPIC_AUTH_TOKEN"], "<redacted>")
        self.assertFalse(claude["alwaysThinkingEnabled"])

        codex = tomllib.loads((self.projection / ".codex/config.toml").read_text())
        self.assertEqual(codex["model"], "device-model")
        self.assertEqual(codex["projects"]["/synthetic/project"]["trust_level"], "trusted")
        self.assertEqual(codex["mcp_servers"]["device"]["command"], "device-mcp")
        self.assertEqual(codex["model_providers"]["device"]["base_url"],
                         "http://127.0.0.1:8787/chatgpt")
        self.assertEqual(codex["model_providers"]["device"]["env_key"], "DEVICE_API_KEY")
        # The managed integration arrives beside the device's own servers.
        self.assertEqual(codex["mcp_servers"]["codegraph"]["command"], "codegraph")

        opencode = json.loads((self.projection / ".config/opencode/opencode.jsonc").read_text())
        self.assertEqual(opencode["theme"], "device-theme")
        self.assertEqual(opencode["providers"]["device"]["settings"]["apiKey"], "<redacted>")
        self.assertIn("./device-skills", opencode["skills"])
        self.assertEqual(opencode["mcp"]["servers"]["device"]["command"], ["device-mcp"])

        pi = json.loads((self.projection / ".pi/agent/settings.json").read_text())
        self.assertEqual(pi["theme"], "device-theme")
        self.assertFalse(pi["deviceSetting"])

        merged = b"".join(path.read_bytes() for path in sorted(self.projection.rglob("*"))
                          if path.is_file())
        self.assertNotIn(DEVICE_TOKEN.encode(), merged)
        self.assertNotIn(DEVICE_API_KEY.encode(), merged)
        # The device's own instructions and terminal preference are untouched.
        self.assertEqual((self.projection / ".claude/CLAUDE.local.md").read_text(),
                         DEVICE_SETTINGS[".claude/CLAUDE.local.md"])
        self.assertEqual((self.projection / ".config/ghostty/config.local.ghostty").read_text(),
                         DEVICE_SETTINGS[".config/ghostty/config.local.ghostty"])

        # The device's own hook command and its trust identity survive.
        hooks = json.loads((self.projection / ".codex/hooks.json").read_text())
        self.assertEqual(hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
                         "device-policy")
        # The device itself keeps its bytes, its mode, and its modification time.
        self.assertEqual(self.source_fingerprints(), before)

    def test_public_bootstrap_still_refuses_a_linked_managed_target(self):
        self.write_manifest([".config/opencode/opencode.jsonc\tjsonc\toptional"])
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        outside = self.root / "outside.json"
        outside.write_text(json.dumps({"theme": "outside"}))
        target = self.projection / ".config/opencode/opencode.jsonc"
        target.unlink()
        target.symlink_to(outside)

        applied = self.deploy()
        self.assertNotEqual(applied.returncode, 0)
        self.assertIn("symlink", applied.stderr)
        self.assertEqual(json.loads(outside.read_text()), {"theme": "outside"})

    def test_text_input_is_copied_verbatim_and_credential_text_fails_closed(self):
        instructions = self.home / ".claude/CLAUDE.local.md"
        instructions.parent.mkdir(parents=True, exist_ok=True)
        instructions.write_text("# device notes\n\nKeep the device preference.\n")
        self.write_manifest([".claude/CLAUDE.local.md\ttext\toptional"])
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)
        projected = self.projection / ".claude/CLAUDE.local.md"
        self.assertEqual(projected.read_text(), instructions.read_text())
        report = json.loads(self.report.read_text())
        self.assertEqual(report["files"][0]["projected"]["records"], 2)

        instructions.write_text("# device notes\n\nsk-syntheticunknownvalue123456\n")
        self.report.unlink()
        # The helper now refuses a projection directory that already holds a
        # projection, so the second run takes a fresh output path.
        second = self.root / "projection-second"
        result = self.project(projection=second)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential-shaped", result.stderr)
        self.assertNotIn("sk-syntheticunknownvalue123456", result.stdout + result.stderr)
        self.assertFalse(second.exists())
        self.assertFalse(self.report.exists())

    def test_text_input_with_credential_shaped_content_is_omitted_with_a_count(self):
        instructions = self.home / ".claude/CLAUDE.local.md"
        instructions.parent.mkdir(parents=True, exist_ok=True)
        instructions.write_text("# device notes\n\nsk-syntheticunknownvalue123456\n")
        self.write_manifest([".claude/CLAUDE.local.md\ttext\toptional"])
        result = self.project("--unknown-credential-policy", "omit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.projection / ".claude/CLAUDE.local.md").exists())
        report = json.loads(self.report.read_text())
        self.assertEqual(report["files"][0]["status"], "omitted")
        self.assertEqual(report["totals"]["unknown_credential_fields"], 1)

    def test_conflicting_skill_symlink_in_the_projection_is_preserved(self):
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        outside = self.root / "outside-skill"
        outside.mkdir()
        (outside / "marker").write_text("keep")
        skills = self.projection / ".agents/skills"
        skills.mkdir(parents=True)
        (skills / "tdd").symlink_to(outside)

        applied = self.deploy()
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue((skills / "tdd").is_symlink())
        self.assertEqual(sorted(item.name for item in outside.iterdir()), ["marker"])

    def test_toml_multiline_credential_is_redacted_and_the_projection_stays_valid_toml(self):
        marker = "fixture-private-marker"
        self.write_device_file(".codex/config.toml",
                                'model = "safe"\napi_key = """\n%s\n"""\n' % marker)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = (self.projection / ".codex/config.toml").read_text()
        self.assertNotIn(marker, projected)
        document = tomllib.loads(projected)
        self.assertEqual(document["model"], "safe")
        self.assertEqual(document["api_key"], "<redacted>")

    def test_toml_inline_table_with_a_credential_key_is_redacted(self):
        marker = "fixture-private-marker"
        self.write_device_file(".codex/config.toml",
                                'model = "safe"\nheaders = { Authorization = "%s" }\n' % marker)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = (self.projection / ".codex/config.toml").read_text()
        self.assertNotIn(marker, projected)
        document = tomllib.loads(projected)
        self.assertEqual(document["model"], "safe")
        self.assertEqual(document["headers"]["Authorization"], "<redacted>")

    def test_toml_comment_with_credential_content_is_refused_without_artifacts(self):
        marker = "fixture-private-marker"
        self.write_device_file(".codex/config.toml",
                                "# api_key = %s\nmodel = \"safe\"\n" % marker)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr)
        self.assertNotIn(marker, result.stdout + result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_a_toml_multiline_value_that_holds_a_credential_assignment_is_refused(self):
        marker = "fixture-private-marker"
        self.write_device_file(".codex/config.toml",
                                'model = "safe"\nnotes = """\nANTHROPIC_AUTH_TOKEN=%s\n"""\n'
                                % marker)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr)
        self.assertNotIn(marker, result.stdout + result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_text_input_with_a_freeform_credential_assignment_is_refused(self):
        marker = "fixture-private-marker"
        self.write_device_file(".claude/CLAUDE.local.md",
                                "# device notes\nANTHROPIC_AUTH_TOKEN=%s\n" % marker)
        self.write_manifest([".claude/CLAUDE.local.md\ttext\toptional"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr)
        self.assertNotIn(marker, result.stdout + result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_an_existing_report_path_is_refused_and_the_source_file_is_untouched(self):
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        source = self.home / ".pi/agent/settings.json"
        linked = self.root / "linked-report.json"
        os.link(source, linked)
        before = (source.read_bytes(), source.stat().st_mtime_ns)

        result = self.project(report=linked)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("report", result.stderr)
        self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)
        self.assertEqual(linked.read_bytes(), source.read_bytes())

    def test_a_report_inside_the_projection_is_refused_before_any_write(self):
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])

        result = self.project(report=self.projection / "report.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("report", result.stderr)
        self.assertFalse(self.projection.exists())

    def test_a_json_string_with_a_quoted_credential_assignment_is_refused(self):
        marker = "fixture-private-marker"
        self.write_device_file(".pi/agent/settings.json", json.dumps({
            "theme": "device-theme",
            "command": '{"ANTHROPIC_AUTH_TOKEN":"%s"}' % marker,
        }))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        before = self.source_fingerprints()

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr)
        self.assertFalse(marker in result.stdout + result.stderr,
                         "the fabricated marker reached the diagnostics")
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())
        self.assertEqual(self.source_fingerprints(), before)

    def test_a_json_string_with_a_single_quoted_credential_key_is_refused(self):
        marker = "fixture-private-marker"
        self.write_device_file(".pi/agent/settings.json", json.dumps({
            "theme": "device-theme",
            "command": "{'ANTHROPIC_AUTH_TOKEN': '%s'}" % marker,
        }))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        before = self.source_fingerprints()

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr)
        self.assertFalse(marker in result.stdout + result.stderr,
                         "the fabricated marker reached the diagnostics")
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())
        self.assertEqual(self.source_fingerprints(), before)

    def test_a_quoted_credential_assignment_is_omitted_with_a_count(self):
        marker = "fixture-private-marker"
        self.write_device_file(".pi/agent/settings.json", json.dumps({
            "theme": "device-theme",
            "command": '{"ANTHROPIC_AUTH_TOKEN":"%s"}' % marker,
        }))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])

        result = self.project("--unknown-credential-policy", "omit")
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = json.loads((self.projection / ".pi/agent/settings.json").read_text())
        self.assertFalse("command" in projected,
                         "the credential-bearing field was not omitted")
        self.assertEqual(projected["theme"], "device-theme")
        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["omitted_fields"], 1)
        self.assertEqual(report["totals"]["unknown_credential_fields"], 1)
        written = (self.projection / ".pi/agent/settings.json").read_text() + self.report.read_text()
        self.assertFalse(marker in written,
                         "the fabricated marker reached an artifact")

    def test_a_url_with_userinfo_is_refused_before_artifacts(self):
        marker = "fixture-private-marker"
        self.write_device_file(".pi/agent/settings.json", json.dumps({
            "theme": "device-theme",
            "env": {"HTTPS_PROXY": "http://operator:%s@127.0.0.1:8000" % marker},
        }))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])
        before = self.source_fingerprints()

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr)
        self.assertFalse(marker in result.stdout + result.stderr,
                         "the fabricated marker reached the diagnostics")
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())
        self.assertEqual(self.source_fingerprints(), before)

    def test_a_url_with_userinfo_is_omitted_with_a_count(self):
        marker = "fixture-private-marker"
        self.write_device_file(".pi/agent/settings.json", json.dumps({
            "theme": "device-theme",
            "env": {"HTTPS_PROXY": "http://operator:%s@127.0.0.1:8000" % marker,
                    "DEVICE_ENV": "keep"},
        }))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])

        result = self.project("--unknown-credential-policy", "omit")
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = json.loads((self.projection / ".pi/agent/settings.json").read_text())
        self.assertFalse("HTTPS_PROXY" in projected["env"],
                         "the credential-bearing field was not omitted")
        self.assertEqual(projected["env"]["DEVICE_ENV"], "keep")
        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["omitted_fields"], 1)
        self.assertEqual(report["totals"]["unknown_credential_fields"], 1)
        written = (self.projection / ".pi/agent/settings.json").read_text() + self.report.read_text()
        self.assertFalse(marker in written,
                         "the fabricated marker reached an artifact")

    def test_a_toml_endpoint_with_userinfo_is_refused_before_artifacts(self):
        marker = "fixture-private-marker"
        self.write_device_file(".codex/config.toml",
                                'model = "safe"\nbase_url = "http://operator:%s@127.0.0.1:8000"\n'
                                % marker)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr)
        self.assertFalse(marker in result.stdout + result.stderr,
                         "the fabricated marker reached the diagnostics")
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_ordinary_urls_and_environment_variable_names_are_preserved(self):
        self.write_device_file(".pi/agent/settings.json", json.dumps({
            "theme": "device-theme",
            "endpoint": "http://127.0.0.1:8787/chatgpt",
            "env_key": "DEVICE_API_KEY",
        }))
        self.write_manifest([".pi/agent/settings.json\tjson\trequired"])

        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = json.loads((self.projection / ".pi/agent/settings.json").read_text())
        self.assertEqual(projected["endpoint"], "http://127.0.0.1:8787/chatgpt")
        self.assertEqual(projected["env_key"], "DEVICE_API_KEY")

    def test_malformed_toml_is_refused_before_any_artifact(self):
        self.write_device_file(".codex/config.toml", "model = \napi_key = 'unterminated\n")
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TOML", result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_a_digest_named_field_with_a_credential_shaped_value_is_projected(self):
        self.write_device_file(".codex/config.toml", DIGEST_CODEX_CONFIG)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = tomllib.loads((self.projection / ".codex/config.toml").read_text())
        state = projected["hooks"]["state"]["synthetic-hook"]
        # A trust digest is an integrity value: it is projected as it is.
        self.assertEqual(state["trusted_hash"], SYNTHETIC_DIGEST)
        self.assertEqual(state["trusted_content_hash"], SYNTHETIC_CONTENT_DIGEST)
        self.assertEqual(state["state"], "trusted")
        self.assertEqual(projected["model"], "device-model")

        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["integrity_fields"], 2)
        self.assertEqual(report["totals"]["unknown_credential_fields"], 0)
        self.assertEqual(report["totals"]["omitted_fields"], 0)
        self.assertEqual(report["totals"]["redacted_fields"], 0)
        self.assertTrue(report["source_unchanged"])

    def test_a_credential_named_field_is_redacted_even_when_it_is_hash_named(self):
        self.write_device_file(".codex/config.toml", (
            'model = "device-model"\n'
            'api_key_hash = "%s"\n'
            'token_hash = "%s"\n'
            'trusted_hash = "%s"\n'
        ) % (SYNTHETIC_DIGEST, SYNTHETIC_DIGEST, SYNTHETIC_DIGEST))
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = tomllib.loads((self.projection / ".codex/config.toml").read_text())
        # The credential-name rule wins over the integrity rule.
        self.assertEqual(projected["api_key_hash"], "<redacted>")
        self.assertEqual(projected["token_hash"], "<redacted>")
        self.assertEqual(projected["trusted_hash"], SYNTHETIC_DIGEST)

        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["redacted_fields"], 2)
        self.assertEqual(report["totals"]["integrity_fields"], 1)
        text = self.report.read_text()
        self.assertNotIn(SYNTHETIC_DIGEST, text)

    def test_an_unknown_credential_shaped_value_under_an_ordinary_name_still_fails_closed(self):
        self.write_device_file(".codex/config.toml", (
            'model = "device-model"\n'
            'device_note = "%s"\n'
            '[hooks.state."synthetic-hook"]\n'
            'trusted_hash = "%s"\n'
        ) % (SYNTHETIC_UNKNOWN_VALUE, SYNTHETIC_DIGEST))
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential-shaped", result.stderr)
        self.assertNotIn(SYNTHETIC_UNKNOWN_VALUE, result.stdout + result.stderr)
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.report.exists())

    def test_an_unknown_credential_shaped_value_is_omitted_with_a_count_beside_digests(self):
        self.write_device_file(".codex/config.toml", (
            'model = "device-model"\n'
            'device_note = "%s"\n'
            '[hooks.state."synthetic-hook"]\n'
            'trusted_hash = "%s"\n'
        ) % (SYNTHETIC_UNKNOWN_VALUE, SYNTHETIC_DIGEST))
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project("--unknown-credential-policy", "omit")
        self.assertEqual(result.returncode, 0, result.stderr)

        projected = tomllib.loads((self.projection / ".codex/config.toml").read_text())
        self.assertNotIn("device_note", projected)
        # The digest is not unknown data: it is projected even under the
        # alternative policy.
        self.assertEqual(projected["hooks"]["state"]["synthetic-hook"]["trusted_hash"],
                         SYNTHETIC_DIGEST)

        report = json.loads(self.report.read_text())
        self.assertEqual(report["totals"]["omitted_fields"], 1)
        self.assertEqual(report["totals"]["unknown_credential_fields"], 1)
        self.assertEqual(report["totals"]["integrity_fields"], 1)
        self.assertNotIn(SYNTHETIC_UNKNOWN_VALUE, self.report.read_text())

    def test_the_projected_record_count_of_a_file_with_digests_matches_the_source(self):
        self.write_device_file(".codex/config.toml", DIGEST_CODEX_CONFIG)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])

        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        report = json.loads(self.report.read_text())
        entry = report["files"][0]
        self.assertEqual(entry["status"], "projected")
        self.assertEqual(entry["projected"]["records"], entry["source"]["records"])
        self.assertEqual(entry["source"]["records"], 4)
        self.assertEqual(report["totals"]["projected_records"],
                         report["totals"]["records"])

    def test_the_hook_trust_digests_survive_the_public_bootstrap(self):
        self.write_device_file(".codex/config.toml", DIGEST_CODEX_CONFIG)
        self.write_manifest([".codex/config.toml\ttoml\trequired"])
        result = self.project()
        self.assertEqual(result.returncode, 0, result.stderr)

        applied = self.deploy()
        self.assertEqual(applied.returncode, 0, applied.stderr)

        merged = tomllib.loads((self.projection / ".codex/config.toml").read_text())
        state = merged["hooks"]["state"]["synthetic-hook"]
        self.assertEqual(state["trusted_hash"], SYNTHETIC_DIGEST)
        self.assertEqual(state["trusted_content_hash"], SYNTHETIC_CONTENT_DIGEST)
        self.assertEqual(state["state"], "trusted")


if __name__ == "__main__":
    unittest.main()
