"""The Magpie catalogs and the apply engine, without a real gateway."""
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

SOURCE = Path(__file__).resolve().parents[1]
CATALOG = SOURCE / "deployment" / "magpie"
CATALOGS = ("providers.tsv", "models.tsv", "groups.tsv", "wiring.tsv")
ENGINE = SOURCE / "deployment" / "magpie.sh"

FAKE_MAGPIE = '''#!/usr/bin/env python3
"""A fake Magpie CLI that records its commands and serves canned answers."""
import json
import os
import pathlib
import sys

state = pathlib.Path(os.environ["FAKE_MAGPIE_STATE"])
state.mkdir(parents=True, exist_ok=True)
with (state / "argv.log").open("a") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")


def load(name, default):
    path = state / name
    return json.loads(path.read_text()) if path.exists() else default


def save(name, value):
    (state / name).write_text(json.dumps(value))


argv = sys.argv[1:]
if argv[:1] == ["status"]:
    print(json.dumps({"running": True, "gateway": os.environ["FAKE_MAGPIE_GATEWAY"]}))
elif argv[:2] == ["accounts", "codex"]:
    print(json.dumps([{"id": "chatgpt-account"}]))
elif argv[:2] == ["provider", "add"]:
    if os.environ.get("FAKE_MAGPIE_TOUCH_CODEX") == "1":
        codex = pathlib.Path(os.environ["HOME"]) / ".codex/config.toml"
        codex.write_text(codex.read_text() + "\\n# changed\\n")
    providers = load("providers.json", [])
    if argv[2] not in providers:
        providers.append(argv[2])
    save("providers.json", providers)
elif argv[:1] == ["provider"]:
    sys.exit(0 if argv[1] in load("providers.json", []) else 1)
elif argv[:2] == ["settings", "get"]:
    print(load("proxy.txt", ""))
elif argv[:2] == ["settings", "set"]:
    save("proxy.txt", argv[3])
elif argv[:2] == ["group", "add"] or argv[:2] == ["group", "set"]:
    groups = load("groups.json", {})
    fields = dict(item.split("=", 1) for item in argv[3:])
    groups[argv[2]] = fields.get("models", "")
    save("groups.json", groups)
elif argv[:1] == ["group"]:
    groups = load("groups.json", {})
    if argv[1] not in groups:
        sys.exit(1)
    print("group " + argv[1])
    print("models: " + groups[argv[1]])
else:
    print("ok")
'''

MODELS = ["codex/gpt-6.1-sol", "codex/gpt-6.1-terra", "kimi-code-cn/k3.1-pro",
          "opencode-go/deepseek-v4.1-flash", "minimax-cn/MiniMax-M3.1-Flash"]


class MagpieCatalogTests(unittest.TestCase):
    """The four catalogs are the deployment's model intent."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-catalog-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = self.root / "catalog"
        self.catalog.mkdir()

    def catalog_copy(self):
        """A writable copy of the shipped catalogs."""
        for name in CATALOGS:
            shutil.copy2(CATALOG / name, self.catalog / name)
        return self.catalog

    def write_catalog(self, name, text):
        (self.catalog / name).write_text(text, encoding="utf-8")

    def read_catalog(self, name):
        return (self.catalog / name).read_text(encoding="utf-8")

    def validate(self, catalog=None):
        """Run the catalog validator over a catalog directory."""
        script = self.root / "validate.sh"
        script.write_text(
            "DEPLOY_SOURCE=" + repr(str(SOURCE)) + "\n"
            "source " + repr(str(SOURCE / "deployment/magpie.sh")) + "\n"
            "magpie_catalog_validate " + repr(str(catalog or self.catalog)) + "\n",
            encoding="utf-8")
        return subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, timeout=60)

    def test_the_shipped_catalogs_validate(self):
        result = self.validate(CATALOG)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr.strip(), "")

    def test_every_catalog_declares_its_field_contract(self):
        for name in CATALOGS:
            with self.subTest(catalog=name):
                text = (CATALOG / name).read_text(encoding="utf-8")
                header = [line for line in text.splitlines() if line.startswith("#")]
                self.assertTrue(header)
                self.assertTrue(any("|" in line for line in header))

    def test_an_unknown_provider_preset_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("providers.tsv").replace("|kimi-code-cn|env:", "|kimi-code-cn-eu|env:")
        self.write_catalog("providers.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown Magpie provider preset", result.stderr)

    def test_a_duplicate_group_id_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("groups.tsv")
        self.write_catalog("groups.tsv", text + "workhorse|workhorse.minimax|drain|auto|yes|duplicate\n")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate group id: workhorse", result.stderr)

    def test_a_member_role_that_does_not_exist_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("groups.tsv").replace("conductor.kimi,", "conductor.kimi,conductor.absent,")
        self.write_catalog("groups.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("names an unknown model role: conductor.absent", result.stderr)

    def test_a_group_member_that_is_not_declared_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("groups.tsv").replace("group/chatgpt", "group/absent")
        self.write_catalog("groups.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("names an undeclared group: absent", result.stderr)

    def test_a_group_without_a_model_role_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("groups.tsv").replace(
            "chatgpt|chatgpt.sol,chatgpt.terra|drain|auto|no|", "chatgpt|group/conductor|drain|auto|no|")
        self.write_catalog("groups.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no model role", result.stderr)

    def test_a_value_that_looks_like_a_key_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("providers.tsv").replace(
            "env:KIMI_CODE_CN_API_KEY", "env:sk-0123456789abcdef0123456789abcdef")
        self.write_catalog("providers.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("looks like a credential", result.stderr)

    def test_a_row_with_the_wrong_field_count_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("providers.tsv").replace("chatgpt|codex|codex-account|yes", "chatgpt|codex|codex-account")
        self.write_catalog("providers.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provider row needs 4 fields", result.stderr)

    def test_a_wired_group_that_is_not_declared_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("wiring.tsv").replace("group/workhorse", "group/absent")
        self.write_catalog("wiring.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("names an undeclared group: absent", result.stderr)

    def test_a_model_candidate_with_an_undeclared_provider_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("models.tsv").replace("kimi-code-cn/k3.1-pro", "kimi-eu/k3.1-pro")
        self.write_catalog("models.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("names an undeclared provider: kimi-eu", result.stderr)

    def test_a_missing_catalog_is_rejected(self):
        self.catalog_copy()
        (self.catalog / "wiring.tsv").unlink()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("catalog is missing: wiring.tsv", result.stderr)


if __name__ == "__main__":
    unittest.main()


class MagpieApplyTests(unittest.TestCase):
    """The apply engine drives the gateway through a fake Magpie CLI."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-apply-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.fake = self.tools / "magpie"
        self.fake.write_text(FAKE_MAGPIE, encoding="utf-8")
        self.fake.chmod(0o755)
        self.catalog = self.root / "catalog"
        self.catalog.mkdir()
        for name in CATALOGS:
            shutil.copy2(CATALOG / name, self.catalog / name)
        self.state = self.home / ".fake-magpie"
        self.server = self.gateway()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def gateway(self):
        """A gateway that serves the canned model list on loopback."""

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"object": "list",
                                   "data": [{"id": model} for model in MODELS]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *arguments):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def seed_home(self, credentials=True):
        """A device with the client files Magpie may touch."""
        (self.home / ".codex").mkdir(parents=True, exist_ok=True)
        (self.home / ".codex/config.toml").write_text('model = "gpt-6-luna"\n', encoding="utf-8")
        (self.home / ".claude").mkdir(parents=True, exist_ok=True)
        (self.home / ".claude/settings.json").write_text('{"model":"opus"}\n', encoding="utf-8")
        (self.home / ".pi/agent").mkdir(parents=True, exist_ok=True)
        (self.home / ".pi/agent/settings.json").write_text('{"defaultProvider":"x"}\n', encoding="utf-8")
        (self.home / ".dsh/profiles/default").mkdir(parents=True, exist_ok=True)
        (self.home / ".dsh/profiles/default/cordis.patch.yml").write_text(
            '- id: llm-deepseek\n  name: "official"\n', encoding="utf-8")
        if not credentials:
            return
        store = self.home / ".config/dotfiles"
        store.mkdir(parents=True, exist_ok=True)
        (store / "magpie.env").write_text("KIMI_CODE_CN_API_KEY=sk-fixture-kimi\n", encoding="utf-8")
        (store / "magpie.env").chmod(0o600)
        (self.home / ".local/share/opencode").mkdir(parents=True, exist_ok=True)
        (self.home / ".local/share/opencode/auth.json").write_text(
            json.dumps({"opencode-go": {"key": "sk-fixture-opencode"}}), encoding="utf-8")
        (self.home / ".pi/agent/auth.json").write_text(
            json.dumps({"minimax-cn": {"key": "sk-fixture-minimax"}}), encoding="utf-8")

    def apply(self, *, credentials=True, environment=None):
        """Run the apply engine against the fake gateway."""
        self.seed_home(credentials)
        script = self.root / "apply.sh"
        script.write_text(
            "export HOME=" + repr(str(self.home)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_apply\n",
            encoding="utf-8")
        environment = {
            "HOME": str(self.home),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_CATALOG_DIR": str(self.catalog),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "DEPLOY_PLATFORM": "macos",
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        environment.update(environment or {})
        return subprocess.run(["/bin/bash", str(script)], env=environment,
                              capture_output=True, text=True, timeout=120)

    def commands(self):
        """Every command the fake Magpie recorded."""
        log = self.state / "argv.log"
        if not log.exists():
            return []
        return [line for line in log.read_text(encoding="utf-8").splitlines() if line]

    def state_file(self):
        return self.home / ".local/state/dotfiles/magpie/state.tsv"

    def test_the_apply_creates_the_providers_groups_and_wiring(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertIn("provider add codex", commands)
        self.assertIn("provider add kimi-code-cn sk-fixture-kimi", commands)
        self.assertIn("provider add opencode-go sk-fixture-opencode", commands)
        self.assertIn("provider add minimax-cn sk-fixture-minimax", commands)
        self.assertTrue(any(command.startswith("group add conductor models=") for command in commands))
        self.assertIn("pi group/workhorse", commands)
        self.assertIn("dsh group/workhorse", commands)
        self.assertTrue(self.state_file().is_file())

    def test_the_apply_never_writes_codex_claude_or_accounts(self):
        self.apply()
        commands = self.commands()
        for forbidden in ("codex", "claude"):
            self.assertFalse(any(command.split(" ")[0] == forbidden for command in commands), commands)
        self.assertFalse(any(command.startswith("accounts add") for command in commands))
        self.assertFalse(any(command.startswith("accounts import") for command in commands))
        self.assertEqual([command for command in commands if command.startswith("accounts")],
                         ["accounts codex --json"])

    def test_the_apply_sets_the_proxy_once(self):
        self.apply()
        settings = [command for command in self.commands() if command.startswith("settings set")]
        self.assertEqual(settings, ["settings set proxy http://127.0.0.1:7897"])

    def test_a_missing_required_credential_fails_and_names_the_variable(self):
        result = self.apply(credentials=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KIMI_CODE_CN_API_KEY", result.stderr)
        self.assertIn("opencode-go.key", result.stderr)

    def test_a_second_apply_writes_nothing(self):
        self.assertEqual(self.apply().returncode, 0)
        state = self.state_file()
        before = state.stat().st_mtime_ns
        files = sorted(str(path) for path in (self.home / ".local/state/dotfiles/magpie").rglob("*"))
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state.stat().st_mtime_ns, before)
        self.assertEqual(sorted(str(path) for path in (self.home / ".local/state/dotfiles/magpie").rglob("*")),
                         files)

    def test_a_changed_codex_configuration_aborts_the_apply_and_keeps_the_backup(self):
        script = self.root / "apply.sh"
        self.seed_home()
        script.write_text(
            "export HOME=" + repr(str(self.home)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_apply\n",
            encoding="utf-8")
        environment = {
            "HOME": str(self.home),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_CATALOG_DIR": str(self.catalog),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "FAKE_MAGPIE_TOUCH_CODEX": "1",
            "DEPLOY_PLATFORM": "macos",
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        result = subprocess.run(["/bin/bash", str(script)], env=environment,
                                capture_output=True, text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the Codex configuration changed during the apply", result.stderr)
        backups = list((self.home / ".local/state/dotfiles/magpie/backups").iterdir())
        self.assertTrue(backups)
        self.assertTrue((backups[0] / "config.toml").is_file())

    def test_the_apply_keeps_the_codex_configuration_untouched(self):
        codex = self.home / ".codex/config.toml"
        self.apply()
        self.assertEqual(codex.read_text(encoding="utf-8"), 'model = "gpt-6-luna"\n')


class MagpieSwitchTests(unittest.TestCase):
    """The bootstrap switch decides whether the gateway is wired."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-switch-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "UV_",
                                           "NPM_", "ATUIN_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                    "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}
        self.env.update(HOME=str(self.root / "original"), PATH="/usr/bin:/bin",
                        DOTFILES_SKILLS_DIR=str(SOURCE / "tests/fixtures/skill-library"))

    def plan(self, *arguments, environment=None):
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(self.home),
                                 "--plan", *arguments], cwd=SOURCE, env=environment or self.env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_the_macos_plan_wires_the_gateway(self):
        plan = self.plan("--platform", "macos")
        self.assertTrue(plan["magpie"])
        self.assertIn("magpie-apply", plan["actions"])
        self.assertLess(plan["actions"].index("magpie-apply"), plan["actions"].index("prepare-shell"))

    def test_the_switch_removes_the_step_and_says_why(self):
        for arguments, environment in ((["--no-magpie"], None), ([], dict(DOTFILES_MAGPIE="false"))):
            with self.subTest(arguments=arguments):
                plan = self.plan("--platform", "macos", *arguments,
                                 environment=dict(self.env, **(environment or {})))
                self.assertFalse(plan["magpie"])
                self.assertNotIn("magpie-apply", plan["actions"])

    def test_the_linux_plan_reports_no_gateway_and_fails_nothing(self):
        plan = self.plan("--platform", "linux")
        self.assertFalse(plan["magpie"])
        self.assertNotIn("magpie-apply", plan["actions"])

    def test_a_restricted_apply_says_why_the_gateway_is_skipped(self):
        if not self.chezmoi:
            self.skipTest("actual apply requires chezmoi")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi)
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "linux", "--apply-only"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dotfiles: magpie: skipped;", result.stdout)


class MagpieCommandTests(MagpieApplyTests):
    """The managed command runs the same engine the deployment step runs."""

    def setUp(self):
        super().setUp()
        self.command = self.home / ".local/bin/dotfiles-magpie"
        self.command.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_dotfiles-magpie", self.command)
        self.command.chmod(0o755)
        engine = self.home / ".local/share/dotfiles/magpie/engine.sh"
        engine.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ENGINE, engine)
        catalogs = self.home / ".config/dotfiles/magpie"
        catalogs.mkdir(parents=True, exist_ok=True)
        for name in CATALOGS:
            shutil.copy2(CATALOG / name, catalogs / name)

    def run_command(self, *arguments, environment=None):
        environ = {
            "HOME": str(self.home),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "DEPLOY_PLATFORM": "macos",
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        environ.update(environment or {})
        return subprocess.run([str(self.command), *arguments], env=environ,
                              capture_output=True, text=True, timeout=120)

    def healthy_gateway(self):
        """A gateway that answers with every provider and group in place."""
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "providers.json").write_text(
            json.dumps(["codex", "opencode-go", "kimi-code-cn", "minimax-cn"]), encoding="utf-8")
        (self.state / "groups.json").write_text(json.dumps({
            "chatgpt": "codex/gpt-6.1-sol,codex/gpt-6.1-terra",
            "conductor": "kimi-code-cn/k3.1-pro,opencode-go/deepseek-v4.1-flash,codex/gpt-6.1-sol,codex/gpt-6.1-terra",
            "workhorse": "minimax-cn/MiniMax-M3.1-Flash,opencode-go/deepseek-v4.1-flash",
        }), encoding="utf-8")
        (self.state / "proxy.txt").write_text(json.dumps("http://127.0.0.1:7897"), encoding="utf-8")

    def test_the_command_applies_the_same_engine(self):
        self.seed_home()
        result = self.run_command("apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("provider add kimi-code-cn sk-fixture-kimi", self.commands())
        self.assertTrue(self.state_file().is_file())

    def test_the_status_exits_zero_on_a_healthy_gateway(self):
        self.seed_home()
        self.healthy_gateway()
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("gateway|", result.stdout)
        self.assertIn("group|workhorse|", result.stdout)
        self.assertIn("wiring|pi|group/workhorse", result.stdout)

    def test_the_status_names_a_missing_piece_and_fails(self):
        self.seed_home()
        self.healthy_gateway()
        (self.state / "providers.json").write_text(json.dumps(["codex"]), encoding="utf-8")
        result = self.run_command("status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing:", result.stderr)
        self.assertIn("kimi-code-cn", result.stderr)

    def test_no_subcommand_prints_a_credential(self):
        self.seed_home()
        self.healthy_gateway()
        for arguments in (("providers",), ("status",)):
            with self.subTest(arguments=arguments):
                result = self.run_command(*arguments)
                self.assertNotIn("sk-fixture", result.stdout)
                self.assertNotIn("sk-fixture", result.stderr)

    def test_the_providers_report_names_the_source_and_never_the_value(self):
        self.seed_home(credentials=False)
        result = self.run_command("providers")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("env:KIMI_CODE_CN_API_KEY", result.stdout)
        self.assertIn("missing", result.stdout)
        self.assertNotIn("sk-fixture", result.stdout)

    def test_the_command_refuses_a_host_that_cannot_run_magpie(self):
        self.seed_home()
        result = self.run_command("status", environment={"DEPLOY_PLATFORM": "linux"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Magpie is not available on this platform", result.stderr)

    def test_the_launcher_reports_the_missing_app_with_the_cask_command(self):
        launcher = self.home / ".local/bin/magpie"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_magpie", launcher)
        launcher.chmod(0o755)
        result = subprocess.run([str(launcher), "--version"], env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"},
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("brew install --cask magpie", result.stderr)

    def test_the_launcher_runs_the_app_binary(self):
        launcher = self.home / ".local/bin/magpie"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_magpie", launcher)
        launcher.chmod(0o755)
        app = self.root / "magpie.app/Contents/MacOS/magpie"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text("#!/bin/sh\necho \"magpie 0.1.0\"\n", encoding="utf-8")
        app.chmod(0o755)
        result = subprocess.run([str(launcher), "--version"],
                                env={"HOME": str(self.home), "PATH": "/usr/bin:/bin", "MAGPIE_APP": str(app)},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("magpie 0.1.0", result.stdout)


class MagpieClientSettingsTests(unittest.TestCase):
    """The client settings point at the Magpie gateway."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-settings-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "UV_",
                                           "NPM_", "ATUIN_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                    "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}
        self.env.update(HOME=str(self.root / "original"), PATH="/usr/bin:/bin",
                        DOTFILES_SKILLS_DIR=str(SOURCE / "tests/fixtures/skill-library"))

    def test_the_claude_template_carries_the_magpie_wiring(self):
        template = json.loads((SOURCE / "deployment/client-settings/claude-settings.json.tmpl").read_text())
        self.assertEqual(template["env"]["ANTHROPIC_BASE_URL"], "http://127.0.0.1:3425")
        self.assertEqual(template["env"]["ANTHROPIC_AUTH_TOKEN"], "magpie")
        self.assertEqual(template["model"], "group/conductor")
        for absent in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                       "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"):
            self.assertNotIn(absent, template["env"])
        self.assertNotIn("glm", json.dumps(template))
        self.assertTrue(template["alwaysThinkingEnabled"])
        self.assertTrue(template["ignorePatterns"])
        self.assertFalse(template["enabledPlugins"]["serena@claude-plugins-official"])

    def test_the_client_settings_policy_keeps_its_two_paths(self):
        policies = json.loads((SOURCE / "deployment/client-settings/policies.json").read_text())
        self.assertEqual(policies["claude-settings"],
                         [["env", "DISABLE_AUTOUPDATER"], ["enabledPlugins", "serena@claude-plugins-official"]])

    def test_no_template_carries_the_glm_data_anymore(self):
        config = (SOURCE / ".chezmoi.toml.tmpl").read_text()
        self.assertNotIn("glmBaseUrl", config)
        self.assertNotIn("glmToken", config)
        for path in (SOURCE / "deployment/client-settings").iterdir():
            if path.is_file():
                self.assertNotIn("glmBaseUrl", path.read_text(), path.name)
                self.assertNotIn("glmToken", path.read_text(), path.name)

    def test_the_rendered_settings_use_the_gateway(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi)
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "macos", "--apply-only"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(settings["env"]["ANTHROPIC_BASE_URL"], "http://127.0.0.1:3425")
        self.assertEqual(settings["env"]["ANTHROPIC_AUTH_TOKEN"], "magpie")
        self.assertEqual(settings["model"], "group/conductor")
        self.assertNotIn("glm", json.dumps(settings))
