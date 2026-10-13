"""CodeGraph access and client-state preservation through public deployment."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import queue
import threading
import time
import socket
import urllib.request
import urllib.error
import base64
import unittest
from fixtures.processes import stop_client
from fixtures.shell_env import managed_shell_environment
from pins import agent_pins

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

SOURCE = Path(__file__).resolve().parents[1]


class CodeGraphTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-codegraph-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual config apply requires chezmoi")
        self.env = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                    "DOTFILES_CHEZMOI_BIN": self.chezmoi}

    def deploy(self, *arguments):
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--source", str(SOURCE), "--home", str(self.home),
                               "--platform", os.environ.get("DOTFILES_TEST_PLATFORM", "linux"),
                               "--role", os.environ.get("DOTFILES_TEST_ROLE", "workstation"),
                               "--apply-only", *arguments],
                              cwd=SOURCE, env=self.env, capture_output=True,
                              text=True, timeout=60)

    def diagnostic_env(self):
        binary = os.environ.get("DOTFILES_TEST_CODEGRAPH", "")
        environment = {"HOME": str(self.home), "PATH": f"{Path(binary).parent}:/usr/bin:/bin",
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "XDG_DATA_HOME": str(self.home / ".local/share"),
                "XDG_STATE_HOME": str(self.home / ".local/state"),
                "XDG_CACHE_HOME": str(self.home / ".cache"),
                "CODEX_HOME": str(self.home / ".codex"),
                "KIMI_CODE_HOME": str(self.home / ".kimi-code"),
                "CODEGRAPH_NO_DOWNLOAD": "1", "DO_NOT_TRACK": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1"}
        return managed_shell_environment(self.home, environment)

    def test_fresh_home_configures_managed_codegraph_even_when_agents_are_disabled(self):
        result = self.deploy("--agents", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        claude = json.loads((self.home / ".claude.json").read_text())
        kimi = json.loads((self.home / ".kimi-code/mcp.json").read_text())
        for config in (claude, kimi):
            server = config["mcpServers"]["codegraph"]
            self.assertEqual(server["command"], "codegraph")
            self.assertEqual(server["args"], ["serve", "--mcp"])
            self.assertNotIn("env", server)
        opencode = json.loads("\n".join(line for line in (self.home / ".config/opencode/opencode.jsonc").read_text().splitlines()
                                      if not line.lstrip().startswith("//")))
        self.assertEqual(opencode["skills"], [str(self.home / ".agents/skills")])
        server = opencode["mcp"]["servers"]["codegraph"]
        self.assertEqual(server["command"], ["codegraph", "serve", "--mcp"])
        self.assertFalse(server["disabled"])
        self.assertFalse(server["codemode"])
        self.assertEqual(json.loads((self.home / ".pi/agent/settings.json").read_text())["skills"],
                         [str(self.home / ".agents/skills")])
        codex = (self.home / ".codex/config.toml").read_text()
        self.assertIn('[mcp_servers.codegraph]', codex)
        self.assertFalse((self.home / ".codegraph").exists())
        self.assertFalse((SOURCE / ".codegraph").exists())
        self.assertFalse((self.home / ".codex/auth.json").exists())

    def test_registration_preserves_existing_client_settings_and_authentication(self):
        if tomllib is None:
            self.skipTest("TOML preservation checks require Python 3.11+")
        original = {
            ".claude.json": '{"oauthAccount":{"emailAddress":"synthetic@example.invalid"},"mcpServers":{"device":{"command":"device-mcp"}}}',
            ".claude/settings.json": '{"model":"device-model","alwaysThinkingEnabled":false,"env":{"ANTHROPIC_AUTH_TOKEN":"synthetic-device-token","DEVICE_ENV":"keep"},"hooks":{"Stop":[]}}',
            ".codex/config.toml": 'model = "device-model"\n[projects."/synthetic/project"]\ntrust_level = "trusted"\n[mcp_servers.device]\ncommand = "device-mcp"\n',
            ".kimi-code/config.toml": 'default_model = "device/model"\n[providers."managed:kimi-code"]\napi_key = "synthetic-device-token"\n[models."device/model"]\nprovider = "device"\n',
            ".kimi-code/tui.toml": 'theme = "device-theme"\n[update]\nauto_install = true\n',
            ".kimi-code/mcp.json": '{"mcpServers":{"device":{"command":"device-mcp","env":{"SYNTHETIC_TOKEN":"keep"}}}}',
            ".config/opencode/opencode.jsonc": '{// a device comment\n"theme":"device-theme","skills":["./device-skills"],"providers":{"device":{"settings":{"apiKey":"synthetic-device-token"}}},"mcp":{"servers":{"device":{"type":"local","command":["device-mcp"]}}}}',
            ".pi/agent/settings.json": '{"theme":"device-theme","skills":["./device-skills"],"enableInstallTelemetry":false,"deviceSetting":false}',
            ".pi/agent/models-store.json": '{"device":{"models":[{"id":"custom-model"}]}}',
            ".codex/auth.json": '{"synthetic-only":"untouched"}\n',
            ".pi/agent/auth.json": '{"synthetic-only":"untouched"}\n',
        }
        for relative, content in original.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        claude = json.loads((self.home / ".claude.json").read_text())
        self.assertEqual(claude["oauthAccount"]["emailAddress"], "synthetic@example.invalid")
        self.assertEqual(claude["mcpServers"]["device"]["command"], "device-mcp")
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(settings["env"]["ANTHROPIC_AUTH_TOKEN"], "synthetic-device-token")
        self.assertEqual(settings["model"], "device-model")
        self.assertFalse(settings["alwaysThinkingEnabled"])
        self.assertEqual(settings["hooks"], {"Stop": []})
        codex = tomllib.loads((self.home / ".codex/config.toml").read_text())
        self.assertEqual(codex["model"], "device-model")
        self.assertEqual(codex["projects"]["/synthetic/project"]["trust_level"], "trusted")
        self.assertEqual(codex["mcp_servers"]["device"]["command"], "device-mcp")
        kimi = tomllib.loads((self.home / ".kimi-code/config.toml").read_text())
        self.assertEqual(kimi["default_model"], "device/model")
        self.assertEqual(kimi["providers"]["managed:kimi-code"]["api_key"], "synthetic-device-token")
        self.assertEqual(tomllib.loads((self.home / ".kimi-code/tui.toml").read_text())["theme"], "device-theme")
        self.assertEqual(json.loads((self.home / ".kimi-code/mcp.json").read_text())["mcpServers"]["device"]["env"], {"SYNTHETIC_TOKEN": "keep"})
        opencode = json.loads((self.home / ".config/opencode/opencode.jsonc").read_text())
        self.assertEqual(opencode["theme"], "device-theme")
        self.assertEqual(opencode["providers"]["device"]["settings"]["apiKey"], "synthetic-device-token")
        self.assertEqual(opencode["mcp"]["servers"]["device"]["command"], ["device-mcp"])
        self.assertEqual(opencode["skills"], ["./device-skills", str(self.home / ".agents/skills")])
        self.assertEqual(json.loads((self.home / ".pi/agent/settings.json").read_text())["theme"], "device-theme")
        self.assertEqual(json.loads((self.home / ".pi/agent/settings.json").read_text())["skills"],
                         ["./device-skills", str(self.home / ".agents/skills")])
        self.assertEqual(json.loads((self.home / ".pi/agent/models-store.json").read_text())["device"], {"models": [{"id": "custom-model"}]})
        for relative in (".codex/auth.json", ".pi/agent/auth.json"):
            self.assertEqual((self.home / relative).read_text(), original[relative])

    def test_role_changes_refresh_managed_defaults_and_keep_device_overrides(self):
        self.assertEqual(self.deploy("--role", "workstation").returncode, 0)
        path = self.home / ".config/opencode/opencode.jsonc"
        config = json.loads(path.read_text())
        self.assertEqual(config["watcher"]["ignore"], ["node_modules/**", "dist/**", ".git/**"])
        config["providers"]["device"] = {"settings": {"apiKey": "synthetic-device-token"}}
        path.write_text(json.dumps(config))
        result = self.deploy("--role", "remote-compute")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(path.read_text())
        self.assertEqual(config["watcher"]["ignore"], ["**"])
        self.assertEqual(config["providers"]["device"]["settings"]["apiKey"], "synthetic-device-token")
        config["watcher"]["ignore"] = ["device/**"]
        path.write_text(json.dumps(config))
        self.assertEqual(self.deploy("--role", "workstation").returncode, 0)
        self.assertEqual(json.loads(path.read_text())["watcher"]["ignore"], ["device/**"])
        before = path.read_bytes()
        self.assertEqual(self.deploy("--role", "workstation").returncode, 0)
        self.assertEqual(path.read_bytes(), before)

    def test_malformed_client_config_fails_without_overwriting_settings_or_printing_secrets(self):
        secret = "SYNTHETIC_SECRET_DO_NOT_PRINT"
        original = {".claude.json": '{"device":"keep"}',
                    ".codex/config.toml": f'[{secret}]\n[{secret}]\n'}
        for relative, content in original.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apply-source.client-settings", result.stderr)
        self.assertIn(".codex/config.toml", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        for relative, content in original.items():
            self.assertEqual((self.home / relative).read_text(), content)

    def test_managed_mcp_command_explores_only_an_explicitly_indexed_temporary_fixture(self):
        binary = os.environ.get("DOTFILES_TEST_CODEGRAPH")
        if not binary:
            self.skipTest("requires the actual pinned CodeGraph CLI")
        self.assertEqual(self.deploy().returncode, 0)
        project = self.root / "temporary-project"
        project.mkdir()
        (project / "counter.py").write_text("def increment(value: int) -> int:\n    return value + 1\n\ndef twice(value: int) -> int:\n    return increment(increment(value))\n")
        command = json.loads((self.home / ".kimi-code/mcp.json").read_text())["mcpServers"]["codegraph"]
        environment = self.diagnostic_env()
        with (self.root / "mcp.log").open("w") as log:
            process = subprocess.Popen([command["command"], *command["args"]], cwd=project,
                                       env=environment, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=log, text=True)
            inbox = queue.Queue()
            def collect():
                for line in process.stdout:
                    inbox.put(json.loads(line))
            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            def send(message):
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
            def request(identifier, method, params):
                send({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
                while True:
                    message = inbox.get(timeout=30)
                    if message.get("method") == "roots/list":
                        send({"jsonrpc": "2.0", "id": message["id"], "result": {"roots": [{"uri": project.as_uri(), "name": "temporary-fixture"}]}})
                    elif message.get("id") == identifier:
                        self.assertNotIn("error", message, message)
                        return message["result"]
            try:
                initialized = request(1, "initialize", {"protocolVersion": "2024-11-05",
                    "capabilities": {"roots": {"listChanged": False}},
                    "clientInfo": {"name": "dotfiles-fixture", "version": "1"}, "rootUri": project.as_uri()})
                self.assertEqual(initialized["serverInfo"]["version"], agent_pins()["codegraph"]["version"])
                self.assertIn("built-in tools", initialized["instructions"])
                send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                tools = request(2, "tools/list", {})["tools"]
                self.assertIn("codegraph_explore", {tool["name"] for tool in tools})
                missing = request(3, "tools/call", {"name": "codegraph_explore", "arguments": {"query": "increment", "projectPath": str(project)}})
                self.assertIn("isn't indexed", json.dumps(missing).lower())
                self.assertIn("built-in tools", json.dumps(missing))
                self.assertFalse((project / ".codegraph").exists())
                self.assertFalse((self.home / ".codegraph").exists())
                indexed = subprocess.run([binary, "init", "--yes", str(project)], cwd=project,
                                         env=environment, capture_output=True, text=True, timeout=90)
                self.assertEqual(indexed.returncode, 0, indexed.stdout + indexed.stderr)
                self.assertTrue((project / ".codegraph").is_dir())
                explored = request(4, "tools/call", {"name": "codegraph_explore", "arguments": {"query": "increment twice counter.py", "projectPath": str(project)}})
                text = "\n".join(item.get("text", "") for item in explored["content"])
                self.assertIn("return value + 1", text)
                self.assertIn("twice", text)
                cli = subprocess.run([binary, "explore", "increment twice counter.py"], cwd=project,
                                     env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
                self.assertIn("return value + 1", cli.stdout)
                self.assertFalse((SOURCE / ".codegraph").exists())
                self.assertFalse((self.home / ".codegraph").exists())
            finally:
                stop_client(process)
                process.stdin.close()
                reader.join(timeout=5)
                process.stdout.close()

    def test_pinned_clients_discover_and_connect_the_managed_mcp_without_model_requests(self):
        binaries = {name: os.environ.get("DOTFILES_TEST_" + name.upper())
                    for name in ("codegraph", "codex", "claude", "kimi", "opencode")}
        if not all(binaries.values()):
            self.skipTest("requires pinned CodeGraph and all four MCP clients")
        self.assertEqual(self.deploy().returncode, 0)
        project = self.root / "unindexed-client-project"
        project.mkdir()
        environment = self.diagnostic_env()
        codex = subprocess.run([binaries["codex"], "mcp", "get", "codegraph", "--json"],
                               cwd=project, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(codex.returncode, 0, codex.stderr)
        server = json.loads(codex.stdout)
        self.assertTrue(server["enabled"])
        self.assertEqual(server["transport"]["command"], "codegraph")
        self.assertEqual(server["transport"]["args"], ["serve", "--mcp"])
        claude = subprocess.run([binaries["claude"], "mcp", "get", "codegraph"],
                                cwd=project, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(claude.returncode, 0, claude.stderr)
        self.assertIn("Connected", claude.stdout)
        self.assertIn("User config", claude.stdout)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for client in ("kimi", "opencode"):
            with self.subTest(client=client):
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    port = listener.getsockname()[1]
                environment["OPENCODE_SERVER_PASSWORD"] = "synthetic-codegraph-test"
                command = ([binaries[client], "web", "--host", "127.0.0.1", "--port", str(port),
                            "--no-open", "--dangerous-bypass-auth"] if client == "kimi" else
                           [binaries[client], "serve", "--hostname", "127.0.0.1", "--port", str(port)])
                def api(path, data=None):
                    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                        data=None if data is None else json.dumps(data).encode(),
                        headers={"Content-Type": "application/json"})
                    if client == "opencode":
                        request.add_header("Authorization", "Basic " + base64.b64encode(b"opencode:synthetic-codegraph-test").decode())
                    return json.loads(opener.open(request, timeout=5).read())
                with (self.root / f"{client}-mcp.log").open("w") as log:
                    process = subprocess.Popen(command, cwd=project, env=environment, stdout=log, stderr=log)
                    try:
                        deadline = time.monotonic() + 30
                        server = None
                        while time.monotonic() < deadline:
                            try:
                                records = api("/api/v2/mcp/servers" if client == "kimi" else "/api/mcp")["data"]
                                server = next((item for item in records if item["name"] == "codegraph"), None)
                                if server and (client == "kimi" or server["status"]["status"] == "connected"):
                                    break
                            except OSError:
                                pass
                            time.sleep(0.1)
                        self.assertIsNotNone(server)
                        if client == "kimi":
                            self.assertEqual(server["source"], "global")
                            self.assertEqual(server["config"]["args"], ["serve", "--mcp"])
                            # Fastify's :: route escape matches a literal single colon.
                            checked = api("/api/v2/mcp/servers:test", {"name": "codegraph"})["data"]
                            self.assertTrue(checked["success"], checked)
                            self.assertIn("codegraph_explore", checked["output"])
                        else:
                            self.assertEqual(server["status"]["status"], "connected", server)
                    finally:
                        stop_client(process)
        self.assertFalse((project / ".codegraph").exists())
        self.assertFalse((self.home / ".codegraph").exists())
        self.assertFalse((SOURCE / ".codegraph").exists())
        self.assertFalse((self.home / ".codex/auth.json").exists())


if __name__ == "__main__":
    unittest.main()
