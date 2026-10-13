"""Portable payload behavior through bootstrap and offline client discovery."""
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import base64
import errno
from collections import Counter
from urllib.parse import unquote, urlparse
from fixtures.processes import stop_client
from fixtures.shell_env import managed_shell_environment

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class AgentPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agent-payload-")
        self.addCleanup(self.cleanup_temporary_home)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual payload apply requires chezmoi")
        self.env = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                    "DOTFILES_CHEZMOI_BIN": self.chezmoi}

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
        path = f"{Path(codegraph).parent}{os.pathsep}{os.defpath}" if codegraph else os.defpath
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
        parsed = urlparse(str(value))
        if parsed.scheme not in ("", "file"):
            return None
        if parsed.scheme == "file":
            if unquote(parsed.netloc) == "~":
                raw = "~" + unquote(parsed.path)
            elif parsed.netloc in ("", "localhost"):
                raw = unquote(parsed.path)
            else:
                return None
        else:
            raw = str(value)
        if raw.startswith("/~/"):
            raw = raw[1:]
        if raw == "~":
            return self.home.resolve()
        path = self.home / raw[2:] if raw.startswith("~/") else Path(raw)
        if not path.is_absolute():
            path = self.home / path
        return path.resolve()

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
        parsed = urlparse(str(value))
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

    def test_default_payload_is_usable_even_when_agent_installation_is_disabled(self):
        result = self.deploy("--agents", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        shared = self.home / ".agents/skills"
        claude = self.home / ".claude/skills"
        self.assertEqual(len(list(shared.glob("*/SKILL.md"))), 105)
        self.assertEqual(len([p for p in shared.rglob("*") if p.is_file()]), 847)
        self.assertEqual(len([p for p in shared.rglob("*") if p.is_file() and p.stat().st_mode & 0o111]), 9)
        self.assertEqual((shared / "tdd/SKILL.md").read_bytes(), (claude / "tdd/SKILL.md").read_bytes())
        self.assertIn("disable-model-invocation: true", (shared / "implement-spec/SKILL.md").read_text())
        self.assertTrue((shared / "scienceskillscommon/pyproject.toml").is_file())
        self.assertTrue((shared / "clinical-trials-database/scripts/clinical_trials_api.py").stat().st_mode & 0o111)
        self.assertFalse(any(p.is_symlink() for directory in (shared, claude) for p in directory.rglob("*")))
        for relative in (".agents/AGENTS.md", ".codex/AGENTS.md", ".claude/CLAUDE.md",
                         ".kimi-code/AGENTS.md", ".pi/agent/AGENTS.md", ".config/opencode/AGENTS.md"):
            instructions = (self.home / relative).read_text()
            self.assertIn("## Completion", instructions)
            self.assertIn("## CodeGraph", instructions)
            self.assertIn("~/.agents/RTK.md", instructions)
            self.assertNotIn("/t9k/", instructions)
        self.assertNotIn("/t9k/", (self.home / ".agents/RTK.md").read_text())
        self.assertFalse((self.home / ".codegraph").exists())
        self.assertFalse((self.home / ".codex/auth.json").exists())

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

    def test_payload_refuses_nested_destination_symlinks_before_copying(self):
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "untouched"
        sentinel.write_text("another device\n")
        for relative in (".agents", ".agents/skills/interpro-database/scripts",
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
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = dict(self.diagnostic_env(),
                           OPENCODE_CONFIG_DIR=str(self.home / ".config/opencode"),
                           OPENCODE_CONFIG=str(self.home / ".config/opencode/opencode.jsonc"),
                           OPENCODE_SERVER_PASSWORD="synthetic-payload-test")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/skill")
        request.add_header("Authorization", "Basic " + base64.b64encode(b"opencode:synthetic-payload-test").decode())
        with (self.root / "opencode.log").open("w") as log:
            process = subprocess.Popen([opencode, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
                                       cwd=self.home, env=environment, stdout=log, stderr=log,
                                       start_new_session=os.name != "nt")
            try:
                deadline = time.monotonic() + 12
                data = []
                while time.monotonic() < deadline:
                    try:
                        data = json.loads(opener.open(request, timeout=2).read())["data"]
                        if any(item["id"] == "tdd" for item in data):
                            break
                    except OSError:
                        pass
                    time.sleep(0.1)
                skills = {item["id"]: item for item in data}
                self.assertIn("tdd", skills)
                self.assertIn("implement-spec", skills)
                self.assertFalse(skills["implement-spec"]["autoinvoke"])
                managed = [skill for skill in data if self.skill_path_is_in_home(skill["path"])]
                expected = {path.parent.name for path in (SOURCE / "deployment/agent-payload/skills").glob("*/SKILL.md")}
                path_kinds = Counter(self.skill_path_kind(skill["path"]) for skill in data)
                path_scopes = Counter(self.skill_path_scope(skill["path"]) for skill in data)
                self.assertEqual({skill["id"] for skill in managed}, expected,
                                 f"managed={len(managed)}; home_matches={environment.get('HOME') == str(self.home)}; "
                                 f"path_kinds={dict(path_kinds)}; path_scopes={dict(path_scopes)}")
                self.assertTrue(self.skill_path_is_in_home(skills["tdd"]["path"]))
            finally:
                stop_client(process)

    def test_pinned_codex_reads_shared_instructions_and_automatic_skills(self):
        codex = os.environ.get("DOTFILES_TEST_CODEX")
        if not codex:
            self.skipTest("requires the pinned Codex CLI")
        self.assertEqual(self.deploy().returncode, 0)
        with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
            process = subprocess.Popen([codex, "debug", "prompt-input"], cwd=self.home,
                                       env=self.diagnostic_env(), stdout=stdout, stderr=stderr,
                                       start_new_session=os.name != "nt")
            try:
                process.wait(timeout=30)
            finally:
                stop_client(process)
            stdout.seek(0)
            stderr.seek(0)
            diagnostic_stdout = stdout.read().decode("utf-8", errors="replace")
            diagnostic_stderr = stderr.read().decode("utf-8", errors="replace")
        self.assertEqual(process.returncode, 0, diagnostic_stderr)
        messages = json.loads(diagnostic_stdout)
        text = "\n".join(part.get("text", "") for message in messages for part in message.get("content", []))
        self.assertIn("~/.agents/RTK.md", text)
        self.assertIn("<!-- DOTFILES_AGENT_START -->", text)
        self.assertIn("- tdd:", text)
        self.assertIn("- clinical-trials-database:", text)
        self.assertNotIn("- implement-spec:", text)

    def test_pinned_pi_resource_loader_reads_the_full_library_and_global_instructions(self):
        module = os.environ.get("DOTFILES_TEST_PI_MODULE")
        node = os.environ.get("DOTFILES_TEST_NODE")
        if not module or not node:
            self.skipTest("requires the pinned Pi SDK module and managed Node")
        self.assertEqual(self.deploy().returncode, 0)
        script = """
const {DefaultResourceLoader,SettingsManager,formatSkillsForPrompt} = await import(process.argv[1]);
import {existsSync,realpathSync} from "node:fs";
import {fileURLToPath} from "node:url";
import path from "node:path";
const settingsManager = SettingsManager.create(process.cwd(),process.env.PI_CODING_AGENT_DIR);
const loader = new DefaultResourceLoader({cwd:process.cwd(),agentDir:process.env.PI_CODING_AGENT_DIR,settingsManager,
  noExtensions:true,noThemes:true,noPromptTemplates:true});
await loader.reload();
const skills=loader.getSkills().skills;
const roots=[path.join(process.env.PI_CODING_AGENT_DIR,"skills"),path.join(process.env.HOME,".agents/skills")]
  .filter(root=>existsSync(root)).map(root=>realpathSync(root));
const scopeRoots=[
  ["device-home",process.env.DOTFILES_TEST_HOME],
  ["test-temp",process.env.DOTFILES_TEST_TEMP_ROOT],
  ["source-tree",process.env.DOTFILES_TEST_SOURCE],
  ["runner-home",process.env.DOTFILES_TEST_RUNNER_HOME]
].filter(([,root])=>root&&existsSync(root)).map(([name,root])=>[name,realpathSync(root)]);
function resolveSkillFile(value) {
  let raw=String(value);
  if (raw.startsWith("file://~/")) raw=path.join(process.env.HOME,decodeURIComponent(raw.slice("file://~/".length)));
  else if (raw.startsWith("file:///~/")) raw=path.join(process.env.HOME,decodeURIComponent(raw.slice("file:///~/".length)));
  else if (raw.startsWith("~/")) raw=path.join(process.env.HOME,raw.slice(2));
  else if (raw.startsWith("file:")) raw=fileURLToPath(new URL(raw));
  return realpathSync(raw);
}
const pathKind=value=>{
  const raw=String(value);
  if (raw.startsWith("file://~/") || raw.startsWith("file:///~/")) return "file-home-uri";
  if (raw.startsWith("~/")) return "home-relative";
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(raw)) return raw.startsWith("file:") ? "file-uri" : "other-uri";
  return path.isAbsolute(raw) ? "absolute" : "relative";
};
const managed=skills.filter(skill=>{
  try {
    const file=resolveSkillFile(skill.filePath);
    return roots.some(root=>file.startsWith(root+path.sep));
  }
  catch { return false; }
});
const pathKinds=skills.reduce((counts,skill)=>{const kind=pathKind(skill.filePath); counts[kind]=(counts[kind]||0)+1; return counts;},{});
const pathScopes=skills.reduce((counts,skill)=>{
  let scope="unresolved";
  try {
    const file=resolveSkillFile(skill.filePath);
    scope=scopeRoots.find(([,root])=>file===root||file.startsWith(root+path.sep))?.[0]||"outside";
  } catch {}
  counts[scope]=(counts[scope]||0)+1; return counts;
},{});
console.log(JSON.stringify({count:managed.length,explicit:managed.filter(s=>s.disableModelInvocation).length,
  pathKinds,pathScopes,rootCount:roots.length,homeMatches:process.env.HOME===process.env.DOTFILES_TEST_HOME,
  prompt:formatSkillsForPrompt(skills),instructions:loader.getAgentsFiles().agentsFiles}));
"""
        diagnostic = subprocess.run([node, "--input-type=module", "-e", script, Path(module).as_uri()],
                                    cwd=self.home, env=self.diagnostic_env(), capture_output=True,
                                    text=True, timeout=30)
        self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
        data = json.loads(diagnostic.stdout)
        expected = {path.parent.name for path in (SOURCE / "deployment/agent-payload/skills").glob("*/SKILL.md")}
        self.assertEqual((data["count"], data["explicit"]), (len(expected), 24),
                         f"root_count={data['rootCount']}; home_matches={data['homeMatches']}; "
                         f"path_kinds={data['pathKinds']}; path_scopes={data['pathScopes']}")
        self.assertIn("<name>tdd</name>", data["prompt"])
        self.assertNotIn("<name>implement-spec</name>", data["prompt"])
        self.assertTrue(any("~/.agents/RTK.md" in item["content"] for item in data["instructions"]))

    def test_skill_resource_names_are_copied_verbatim_without_hook_execution(self):
        source = self.root / "source"
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        resources = source / "deployment/agent-payload/skills/tdd/resources"
        resources.mkdir()
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
            binary = os.environ.get("DOTFILES_TEST_" + client.upper())
            if not binary:
                self.skipTest("requires both pinned Claude and Kimi CLIs")
        self.assertEqual(self.deploy().returncode, 0)
        for client in ("claude", "kimi"):
            with self.subTest(client=client):
                binary = os.environ["DOTFILES_TEST_" + client.upper()]
                if client == "claude":
                    environment = dict(self.diagnostic_env(), CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                                       DISABLE_TELEMETRY="1", DISABLE_AUTOUPDATER="1")
                    command = [binary, "--print", "--input-format", "stream-json", "--output-format", "stream-json",
                               "--verbose", "--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                               "--settings", '{"env":{"ANTHROPIC_BASE_URL":"http://127.0.0.1:9","ANTHROPIC_AUTH_TOKEN":"synthetic"}}']
                else:
                    environment = self.diagnostic_env()
                    command = [binary, "acp"]
                with (self.root / f"{client}.log").open("w") as log:
                    process = subprocess.Popen(command, cwd=self.home, env=environment, stdin=subprocess.PIPE,
                                               stdout=subprocess.PIPE, stderr=log, text=True,
                                               start_new_session=os.name != "nt")
                    inbox = queue.Queue()
                    def collect():
                        for line in process.stdout:
                            inbox.put(json.loads(line))
                    reader = threading.Thread(target=collect, daemon=True)
                    reader.start()
                    def send(message):
                        process.stdin.write(json.dumps(message) + "\n")
                        process.stdin.flush()
                    try:
                        if client == "claude":
                            send({"type": "control_request", "request_id": "discovery", "request": {"subtype": "initialize"}})
                            message = inbox.get(timeout=30)
                            self.assertEqual(message["type"], "control_response", message)
                            names = {item["name"] for item in message["response"]["response"]["commands"]}
                            self.assertIn("tdd", names)
                            self.assertIn("implement-spec", names)
                        else:
                            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": 1, "clientCapabilities": {}}})
                            self.assertIn("result", inbox.get(timeout=30))
                            send({"jsonrpc": "2.0", "id": 2, "method": "session/new",
                                  "params": {"cwd": str(self.home), "mcpServers": []}})
                            deadline = time.monotonic() + 30
                            names = set()
                            while time.monotonic() < deadline:
                                message = inbox.get(timeout=max(0.1, deadline-time.monotonic()))
                                update = message.get("params", {}).get("update", {})
                                if update.get("sessionUpdate") == "available_commands_update":
                                    names = {item["name"] for item in update["availableCommands"]}
                                    break
                            self.assertIn("skill:tdd", names)
                            self.assertIn("skill:implement-spec", names)
                        expected = {path.parent.name for path in (SOURCE / "deployment/agent-payload/skills").glob("*/SKILL.md")}
                        advertised = {name.removeprefix("skill:") for name in names}
                        self.assertTrue(expected.issubset(advertised), expected - advertised)
                    finally:
                        stop_client(process)
                        process.stdin.close()
                        reader.join(timeout=5)
                        process.stdout.close()


if __name__ == "__main__":
    unittest.main()
