"""The Magpie catalogs and the apply engine, without a real gateway."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

if __package__:
    from .fixtures.magpie_engine import install_engine_shim
else:
    from fixtures.magpie_engine import install_engine_shim

SOURCE = Path(__file__).resolve().parents[1]
CATALOG = SOURCE / "deployment" / "magpie"
CATALOGS = ("providers.tsv", "models.tsv", "groups.tsv", "wiring.tsv", "visible.tsv", "plugins.tsv", "picked.tsv")
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
if argv[:1] == ["--version"]:
    print("magpie 0.1.4404")
elif argv[:1] == ["status"]:
    if os.environ.get("FAKE_MAGPIE_FAIL_STATUS") == "1":
        sys.exit(1)
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
elif argv[:2] == ["plugin", "list"]:
    if os.environ.get("FAKE_MAGPIE_FAIL_PLUGIN_LIST") == "1":
        sys.exit(1)
    default = [] if os.environ.get("FAKE_MAGPIE_EMPTY_PLUGIN_LIST") == "1" else {"loaded": [], "plugins": []}
    print(json.dumps(load("plugins.json", default)))
elif argv[:2] == ["plugin", "add"]:
    plugins = load("plugins.json", {"loaded": [], "plugins": []})
    spec = argv[2][len("npm:"):] if argv[2].startswith("npm:") else argv[2]
    for key in ("loaded", "plugins"):
        entries = plugins.setdefault(key, [])
        if not any(entry.get("spec") == spec for entry in entries):
            entries.append({"spec": spec})
    save("plugins.json", plugins)
elif argv[:2] == ["plugin", "on"]:
    plugins = load("plugins.json", {"loaded": [], "plugins": []})
    loaded = {entry.get("spec") for entry in plugins.get("loaded", [])}
    for entry in plugins.get("plugins", []):
        if entry.get("spec") not in loaded:
            plugins.setdefault("loaded", []).append(entry)
    save("plugins.json", plugins)
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
elif argv[:1] == ["visible"]:
    visible = load("visible.json", {})
    if len(argv) == 1:
        for agent in sorted(visible):
            print("  " + agent + "  " + visible[agent].replace(",", ", ") + "  1 shown, 2 not")
    elif len(argv) == 2:
        print("  Routing groups")
        if argv[1] in visible:
            print("  " + argv[1] + " is shown " + visible[argv[1]].replace(",", ", "))
    else:
        if os.environ.get("FAKE_MAGPIE_FAIL_VISIBLE") == "1":
            sys.exit(1)
        visible[argv[1]] = argv[2]
        save("visible.json", visible)
        print("saved")
elif argv[:2] == ["dsh", "compact_model"]:
    # The pinned CLI's compact_model field: the getter prints "<Name>
    # compaction model <magpie/<id>|default>", the setter takes an id or a
    # group and stores it without touching dsh's own profile.
    if len(argv) == 2 and os.environ.get("FAKE_MAGPIE_FAIL_DSH_COMPACT_GET") == "1":
        sys.exit(1)
    if len(argv) == 3 and os.environ.get("FAKE_MAGPIE_FAIL_DSH_COMPACT_SET") == "1":
        sys.exit(1)
    current = load("dsh-compact.json", {"value": ""})["value"]
    if len(argv) == 2:
        override = os.environ.get("FAKE_MAGPIE_DSH_COMPACT_GET_OUTPUT")
        if override is not None:
            # A malformed successful answer enters through the same process
            # boundary as a real CLI, so the engine must fail closed on it.
            print(override)
        else:
            print("DeepSeek Harness compaction model " + (("magpie/" + current) if current else "default"))
    else:
        if os.environ.get("FAKE_MAGPIE_TOUCH_CODEX_ON_COMPACT") == "1":
            codex = pathlib.Path(os.environ["HOME"]) / ".codex/config.toml"
            codex.write_text(codex.read_text() + "\\n# changed\\n")
        value = argv[2]
        if value.startswith("magpie/"):
            value = value[len("magpie/"):]
        if not value or "/" not in value:
            sys.exit(2)
        save("dsh-compact.json", {"value": value})
        print("✓ DeepSeek Harness compaction model magpie/" + value)
elif argv[:1] == ["dsh"]:
    if os.environ.get("FAKE_MAGPIE_TOUCH_DSH") == "1":
        patch = pathlib.Path(os.environ["HOME"]) / ".dsh/profiles/default/cordis.patch.yml"
        patch.write_text(patch.read_text().replace('name: "official"', 'name: "changed"'))
    print("ok")
elif argv[:1] == ["pi"] and len(argv) == 2:
    # Magpie generates the Pi model file when it wires the agent.
    models = pathlib.Path(os.environ["HOME"]) / ".pi/agent/models.json"
    models.parent.mkdir(parents=True, exist_ok=True)
    models.write_text(json.dumps({"providers": [{"id": "magpie", "name": "Magpie"}]}))
    print("ok")
elif argv[:1] == ["group"]:
    groups = load("groups.json", {})
    if argv[1] not in groups:
        sys.exit(1)
    print("  " + argv[1] + "  group/" + argv[1])
    print("  routing   drain")
    print("  models")
    for index, model in enumerate(groups[argv[1]].split(","), 1):
        print("            " + str(index) + " " + model + "  name")
else:
    print("ok")
'''

MODELS = ["codex/gpt-6.2-sol", "codex/gpt-6.1-sol", "codex/gpt-6.1-terra", "codex/gpt-6-luna", "codex/gpt-6.2-astra",
          "openai/gpt-6.2-sol", "openai/gpt-6.1-sol", "openai/gpt-6.1-terra", "openai/gpt-6-luna", "openai/gpt-6.2-astra",
          "zed/gpt-6.1-sol", "zed/gpt-6-luna",
          "kimi-code-cn/k3.1-pro", "opencode-go/deepseek-v4.1-flash", "opencode-go/gpt-6-luna",
          "minimax-cn/MiniMax-M3.1-Flash"]


class MagpieCatalogTests(unittest.TestCase):
    """The catalogs are the deployment's model intent."""

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
        text = self.read_catalog("groups.tsv").replace("openai.terra:high,", "openai.terra:high,conductor.absent,")
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

    def test_a_group_without_a_reachable_model_role_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("groups.tsv").replace(
            "chatgpt|chatgpt.sol:medium,chatgpt.terra:high|drain|auto|yes|weekly ChatGPT quota",
            "chatgpt|group/workhorse|drain|auto|no|nothing")
        text = text.replace(
            "workhorse|workhorse.minimax:max,conductor.deepseek:max|drain|auto|yes|Pi and dsh, both at max",
            "workhorse|group/chatgpt|drain|auto|yes|nothing")
        self.write_catalog("groups.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no model role", result.stderr)

    def test_the_openai_stack_and_the_pinned_effort_are_declared(self):
        providers = (CATALOG / "providers.tsv").read_text(encoding="utf-8").splitlines()
        self.assertIn("openai|openai|env:OPENAI_API_KEY|yes", providers)
        models = (CATALOG / "models.tsv").read_text(encoding="utf-8").splitlines()
        self.assertIn("openai.sol|openai/gpt-6.1-sol|yes", models)
        self.assertIn("openai.terra|openai/gpt-6.1-terra|yes", models)
        groups = [line for line in (CATALOG / "groups.tsv").read_text(encoding="utf-8").splitlines()
                  if line and not line.startswith("#")]
        self.assertEqual([line.split("|")[0] for line in groups],
                         ["chatgpt", "openai-stack", "conductor", "workhorse",
                          "auto-gpt-6-1-sol", "auto-gpt-6-1-terra", "auto-gpt-6-luna", "auto-gpt-6-astra"])
        self.assertEqual(groups[1].split("|")[1],
                         "group/chatgpt,openai.sol:medium,openai.terra:high,conductor.kimi:max")
        self.assertEqual(groups[2].split("|")[1],
                         "conductor.codex-sol:medium,conductor.openai-sol:medium,conductor.kimi:max")
        self.assertEqual(groups[3].split("|")[1],
                         "workhorse.minimax:max,conductor.deepseek:max")

    def test_an_unknown_reasoning_effort_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("groups.tsv").replace("conductor.kimi:max", "conductor.kimi:turbo")
        self.write_catalog("groups.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown reasoning effort in group member: conductor.kimi:turbo", result.stderr)

    def test_a_group_reference_cannot_carry_a_reasoning_effort(self):
        self.catalog_copy()
        text = self.read_catalog("groups.tsv").replace("group/chatgpt", "group/chatgpt:max")
        self.write_catalog("groups.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("a group member cannot carry a reasoning effort: group/chatgpt:max", result.stderr)

    def test_a_value_that_looks_like_a_key_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("providers.tsv").replace(
            "env:KIMI_CODE_CN_API_KEY", "env:sk-fixture-catalog-key")
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

    def test_an_unknown_visible_agent_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("visible.tsv").replace("claude|chatgpt", "claudex|chatgpt")
        self.write_catalog("visible.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("visible names an unknown agent: claudex", result.stderr)

    def test_an_unknown_visible_group_or_provider_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("visible.tsv").replace("pi|chatgpt,", "pi|workhors,")
        self.write_catalog("visible.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("visible agent pi names an unknown group or provider: workhors", result.stderr)

    def test_a_picked_model_with_an_undeclared_provider_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("picked.tsv").replace(
            "opencode-go/deepseek-v4.1-flash", "kimi-eu/deepseek-v4.1-flash")
        self.write_catalog("picked.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("picked model names an undeclared provider: kimi-eu/deepseek-v4.1-flash", result.stderr)

    def test_a_picked_group_that_is_not_declared_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("picked.tsv").replace("group/workhorse", "group/absent")
        self.write_catalog("picked.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("picked group is not declared: group/absent", result.stderr)

    def test_a_picked_provider_outside_the_visible_row_is_rejected(self):
        self.catalog_copy()
        visible = self.read_catalog("visible.tsv").replace(
            "pi|chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,",
            "pi|chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,")
        self.write_catalog("visible.tsv", visible)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("picked provider is not visible to pi: zed/gpt-6.1-sol", result.stderr)

    def test_a_plugin_source_that_looks_like_a_credential_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("plugins.tsv").replace(
            "@magpie-community/opencode-zed-auth", "sk-fixture-plugin-key")
        self.write_catalog("plugins.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("looks like a credential", result.stderr)

    def test_a_plugin_without_an_exact_version_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("plugins.tsv").replace("|0.1.19|yes", "|latest|yes")
        self.write_catalog("plugins.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid plugin version: latest", result.stderr)

    def test_a_duplicate_plugin_name_is_rejected(self):
        self.catalog_copy()
        text = self.read_catalog("plugins.tsv") + "zed|@magpie-community/other|1.0.0|yes\n"
        self.write_catalog("plugins.tsv", text)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate plugin name: zed", result.stderr)

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
        curl = self.tools / "curl"
        curl.write_text(
            "#!/bin/sh\nallowed=0\n"
            "for arg do\n"
            "  case \"$arg\" in\n"
            "    \"${FAKE_MAGPIE_GATEWAY:-not-set}\"/*) allowed=1 ;;\n"
            "    http://*|https://*) printf 'unexpected URL in synthetic test\\n' >&2; exit 98 ;;\n"
            "  esac\n"
            "done\n"
            "[ \"$allowed\" = 1 ] || exit 98\n"
            "exec /usr/bin/curl \"$@\"\n", encoding="utf-8")
        curl.chmod(0o755)
        self.catalog = self.root / "catalog"
        self.catalog.mkdir()
        for name in CATALOGS:
            shutil.copy2(CATALOG / name, self.catalog / name)
        self.state = self.home / ".fake-magpie"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        self.native_cli = self.tools / "magpie-native"
        self.native_cli.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  --version) echo 'magpie 0.1.4404' ;;\n"
            "  *) exit 0 ;;\n"
            "esac\n", encoding="utf-8")
        self.native_cli.chmod(0o755)
        # The installer verifies cached CLI bytes against the release catalog
        # before it executes them, so the fixture's release catalog carries the
        # synthetic CLI's own digest for both native Linux targets. This keeps
        # the fake apply paths off the network without weakening that check.
        digest = hashlib.sha256(self.native_cli.read_bytes()).hexdigest()
        self.native_release_catalog = self.root / "native-releases.tsv"
        self.native_release_catalog.write_text(
            "magpie|0.1.4404|linux-amd64|https://example.invalid/magpie-cli-linux-amd64|"
            + digest + "\n"
            "magpie|0.1.4404|linux-arm64|https://example.invalid/magpie-cli-linux-arm64|"
            + digest + "\n"
            "magpie|0.1.4404|macos-amd64|https://example.invalid/magpie-cli-darwin-amd64|"
            + digest + "\n"
            "magpie|0.1.4404|macos-arm64|https://example.invalid/magpie-cli-darwin-arm64|"
            + digest + "\n",
            encoding="utf-8")
        self.server = self.gateway()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def gateway(self):
        """A gateway that serves the canned model list on loopback."""

        class Handler(http.server.BaseHTTPRequestHandler):
            def reply(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.reply(200, {"object": "list",
                                 "data": [{"id": model} for model in MODELS]})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(length) or b"{}")
                self.server.completions.append(request.get("model"))
                if self.server.reject_completions:
                    self.reply(500, {"error": {"message": "the provider refused the turn"}})
                    return
                self.reply(200, {"choices": [{"message": {"role": "assistant",
                                                          "content": "pong"}}]})

            def log_message(self, *arguments):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.completions = []
        server.reject_completions = False
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def seed_home(self, credentials=True):
        """A device with the client files Magpie may touch."""
        # Key-based providers are already provisioned in Magpie; codex uses
        # the credential-free account path and can still be added by apply.
        self.state.mkdir(parents=True, exist_ok=True)
        providers = self.state / "providers.json"
        if not providers.exists():
            providers.write_text(json.dumps(["zed", "opencode-go", "kimi-code-cn", "minimax-cn", "openai"]), encoding="utf-8")
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
        (store / "magpie.env").write_text(
            "KIMI_CODE_CN_API_KEY=sk-fixture-kimi\nOPENAI_API_KEY=sk-fixture-openai\n", encoding="utf-8")
        (store / "magpie.env").chmod(0o600)
        (self.home / ".local/share/opencode").mkdir(parents=True, exist_ok=True)
        (self.home / ".local/share/opencode/auth.json").write_text(
            json.dumps({"opencode-go": {"key": "sk-fixture-opencode"}}), encoding="utf-8")
        (self.home / ".pi/agent/auth.json").write_text(
            json.dumps({"minimax-cn": {"key": "sk-fixture-minimax"}}), encoding="utf-8")

    def provision(self, presets):
        """Record the providers Magpie already knows on a headless host."""
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "providers.json").write_text(json.dumps(list(presets)), encoding="utf-8")

    def healthy_client_wiring(self):
        """The client files a device carries once the gateway wired them.

        The status reads the live files, so a healthy fixture has to hold the
        real wiring: Claude's gateway endpoint, the conductor work tiers, the
        Terra background aliases and classifier, Pi's default provider, model
        and thinking level, and the model file Magpie generates for Pi. DSH's
        live compaction field holds the workhorse route. The subagent model is
        absent: subagents inherit their parent natively and a device-owned
        override is not deployment drift.
        """
        claude = self.home / ".claude/settings.json"
        claude.parent.mkdir(parents=True, exist_ok=True)
        claude.write_text(json.dumps({
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "magpie",
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:3425",
                "ANTHROPIC_DEFAULT_FABLE_MODEL": "group/conductor",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": "codex/gpt-6.1-terra",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "group/conductor",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "group/conductor",
                "ANTHROPIC_SMALL_FAST_MODEL": "codex/gpt-6.1-terra",
                "CLAUDE_CODE_AUTO_MODE_MODEL": "codex/gpt-6.1-terra",
            },
            "model": "opus",
        }, indent=2) + "\n", encoding="utf-8")
        pi = self.home / ".pi/agent/settings.json"
        pi.parent.mkdir(parents=True, exist_ok=True)
        pi.write_text(json.dumps({
            "defaultProvider": "magpie",
            "defaultModel": "group/workhorse",
            "modelThinkingLevels": {"magpie/group/workhorse": "high"},
        }, indent=2) + "\n", encoding="utf-8")
        models = self.home / ".pi/agent/models.json"
        models.write_text(json.dumps({"providers": [{"id": "magpie", "name": "Magpie"}]}),
                          encoding="utf-8")

    def apply(self, *, credentials=True, environment=None, setup=None, merger=False, premerge=False,
              platform="macos", shell=None):
        """Run the apply engine against the fake gateway.

        The merger flag adds the deployment's client-settings merger, so the
        engine migrates the repo-owned client files the way the deployment
        step does. The platform flag selects the macOS application or the
        native CLI a headless host runs. The shell flag injects lines before
        the engine is sourced, so a test can declare the bootstrap's agent
        selection the way agents.sh does.
        """
        self.seed_home(credentials)
        if setup:
            setup()
        lines = ["export HOME=" + repr(str(self.home))]
        lines += list(shell or [])
        environ = {
            "HOME": str(self.home),
            "PATH": f"{self.tools}:/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_CATALOG_DIR": str(self.catalog),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "MAGPIE_APP": str(self.fake),
            "DEPLOY_PLATFORM": platform,
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        if platform in ("linux", "wsl"):
            # A headless host runs the native CLI. The fixture stands in for
            # the pinned release, so the tests never reach the network. Point
            # at the fixture catalog, whose digest matches the fake CLI bytes;
            # the source catalog assertions below keep reading the real one.
            environ["MAGPIE_CLI_BIN"] = str(self.native_cli)
            environ["MAGPIE_RELEASE_CATALOG"] = str(self.native_release_catalog)
        if merger:
            self.write_chezmoi_config()
            lines += [
                "export DEPLOY_SOURCE=" + repr(str(SOURCE)),
                "export DEPLOY_HOME=$HOME",
                "export DEPLOY_CHEZMOI=" + repr(str(self.chezmoi)),
                "export TMPDIR=" + repr(str(self.home / ".cache/tmp")),
                'fail() { printf \'dotfiles: %s\\n\' "$*" >&2; exit 1; }',
                'source "$DEPLOY_SOURCE/deployment/payload.sh"',
                'source "$DEPLOY_SOURCE/deployment/client-settings.sh"',
            ]
        lines.append("source " + repr(str(ENGINE)))
        if premerge:
            lines += [
                'DEPLOY_MAGPIE_BACKUP_SOURCE=$(magpie_snapshot_clients)',
                'deploy_client_settings',
            ]
        lines.append("magpie_apply")
        script = self.root / "apply.sh"
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        environ.update(environment or {})
        return subprocess.run(["/bin/bash", str(script)], env=environ,
                              capture_output=True, text=True, timeout=120)

    def write_chezmoi_config(self):
        """The device's chezmoi config, with the platform the merge reads."""
        config = self.home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[data]\n    platform = "macos"\n    role = "workstation"\n'
                          '    arch = "aarch64"\n    kimiApiKey = "REPLACE_ME"\n', encoding="utf-8")
        cache = self.home / ".cache/tmp"
        cache.mkdir(parents=True, exist_ok=True)

    def commands(self):
        """Every command the fake Magpie recorded."""
        log = self.state / "argv.log"
        if not log.exists():
            return []
        return [line for line in log.read_text(encoding="utf-8").splitlines() if line]

    def state_file(self):
        return self.home / ".local/state/dotfiles/magpie/state.tsv"

    def dsh_compact_value(self):
        """The compaction id the fake gateway holds, empty when unset."""
        path = self.state / "dsh-compact.json"
        return json.loads(path.read_text())["value"] if path.exists() else ""

    def dsh_compact_commands(self):
        return [command for command in self.commands()
                if command.startswith("dsh compact_model")]

    def test_the_apply_preserves_existing_providers_and_wires_clients(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertIn("provider add codex", commands)
        self.assertEqual([command for command in commands if command.startswith("provider add")],
                         ["provider add codex"])
        self.assertFalse(any("sk-fixture" in command for command in commands))
        self.assertTrue(any(command.startswith("group add conductor models=") for command in commands))
        self.assertEqual([command for command in commands if command == "pi group/workhorse"],
                         ["pi group/workhorse"])
        self.assertEqual([command for command in commands if command == "dsh group/workhorse"],
                         ["dsh group/workhorse"])
        self.assertTrue(self.state_file().is_file())

    def test_the_apply_runs_its_commands_in_the_declared_order(self):
        self.assertEqual(self.apply().returncode, 0)
        commands = self.commands()
        order = ["settings set proxy", "plugin add npm:@magpie-community/opencode-zed-auth@0.1.19",
                 "provider add codex",
                 "group add chatgpt", "group add openai-stack", "group add conductor", "group add workhorse",
                 "visible claude chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn", "visible pi chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn", "visible dsh chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn",
                 "pi group/workhorse", "dsh group/workhorse"]
        positions = []
        for command in order:
            matches = [index for index, recorded in enumerate(commands) if recorded.startswith(command)]
            self.assertEqual(len(matches), 1, command)
            positions.append(matches[0])
        self.assertEqual(positions, sorted(positions))

    def test_the_visible_catalog_narrows_each_agent_after_the_groups(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        narrowing = [command for command in self.commands() if len(command.split()) == 3
                     and command.startswith("visible ")]
        self.assertEqual(narrowing, ["visible claude chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn",
                                     "visible pi chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn", "visible dsh chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn"])

    def test_the_apply_writes_the_picked_models_and_is_idempotent(self):
        self.assertEqual(self.apply().returncode, 0)
        settings = self.home / ".config/magpie/settings.json"
        expected = {}
        for line in (CATALOG / "picked.tsv").read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            agent, entries = line.split("|", 1)
            expected[agent] = entries.split(",")
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["pickedModels"], expected)
        self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
        before = settings.read_text(encoding="utf-8")
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(settings.read_text(encoding="utf-8"), before)

    def test_the_picked_write_preserves_other_settings_and_picks(self):
        def setup():
            settings = self.home / ".config/magpie/settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({
                "theme": "dark",
                "proxy": "direct",
                "pickedModels": {"other": ["other/model"]},
            }), encoding="utf-8")

        self.assertEqual(self.apply(setup=setup).returncode, 0)
        data = json.loads((self.home / ".config/magpie/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(data["proxy"], "direct")
        self.assertEqual(data["pickedModels"]["other"], ["other/model"])
        self.assertIn("claude", data["pickedModels"])
        self.assertIn("group/conductor", data["pickedModels"]["claude"])

    def test_a_failing_visible_aborts_the_apply(self):
        result = self.apply(environment={"FAKE_MAGPIE_FAIL_VISIBLE": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot narrow the agent claude to chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn", result.stderr)

    def test_a_visibility_only_run_rewires_and_backs_up_the_client_lists(self):
        self.assertEqual(self.apply().returncode, 0)
        backups = self.home / ".local/state/dotfiles/magpie/backups"
        before = sorted(path.name for path in backups.iterdir())
        state = self.state_file()
        state_mtime = state.stat().st_mtime_ns
        # The gateway forgets the narrowing; every other piece still matches.
        (self.state / "visible.json").unlink()
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = sorted(path.name for path in backups.iterdir())
        # The forced rewire rewrites Pi/DSH model lists, so it backs them up;
        # the recorded provider/group/wiring state itself is unchanged.
        self.assertEqual(len(after), len(before) + 1, after)
        self.assertEqual(state.stat().st_mtime_ns, state_mtime)
        self.assertEqual([command for command in self.commands() if len(command.split()) == 3
                          and command.startswith("visible ")][-3:],
                         ["visible claude chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn",
                          "visible pi chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn", "visible dsh chatgpt,openai-stack,conductor,workhorse,auto-gpt-6-1-sol,auto-gpt-6-1-terra,auto-gpt-6-luna,auto-gpt-6-astra,codex,openai,zed,kimi-code-cn,opencode-go,minimax-cn"])

    def test_the_apply_installs_the_pinned_plugin_before_the_providers(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        installs = [command for command in commands
                    if command == "plugin add npm:@magpie-community/opencode-zed-auth@0.1.19"]
        self.assertEqual(len(installs), 1, commands)
        self.assertLess(commands.index(installs[0]), commands.index("provider add codex"))
        self.assertNotIn("plugin on zed", commands)

    def test_a_fresh_homes_empty_plugin_array_installs_the_pin_once(self):
        environment = {"FAKE_MAGPIE_EMPTY_PLUGIN_LIST": "1"}
        first = self.apply(environment=environment)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = self.apply(environment=environment)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual([command for command in self.commands() if command.startswith("plugin add")],
                         ["plugin add npm:@magpie-community/opencode-zed-auth@0.1.19"])

    def test_a_present_plugin_is_not_installed_or_turned_on_again(self):
        spec = "@magpie-community/opencode-zed-auth@0.1.19"

        def seed_plugin():
            self.state.mkdir(parents=True, exist_ok=True)
            (self.state / "plugins.json").write_text(
                json.dumps({"loaded": [{"spec": spec}], "plugins": [{"spec": spec}]}), encoding="utf-8")

        result = self.apply(setup=seed_plugin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertEqual([command for command in commands if command.startswith("plugin add")], [])
        self.assertEqual([command for command in commands if command.startswith("plugin on")], [])

    def test_a_plugin_that_is_installed_but_off_is_turned_on(self):
        spec = "@magpie-community/opencode-zed-auth@0.1.19"

        def seed_plugin():
            self.state.mkdir(parents=True, exist_ok=True)
            (self.state / "plugins.json").write_text(
                json.dumps({"loaded": [], "plugins": [{"spec": spec}]}), encoding="utf-8")

        result = self.apply(setup=seed_plugin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertEqual([command for command in commands if command == "plugin on zed"], ["plugin on zed"])
        self.assertEqual([command for command in commands if command.startswith("plugin add")], [])

    def test_an_unreadable_plugin_list_never_installs_on_a_guess(self):
        script = self.root / "apply.sh"
        self.seed_home()
        script.write_text(
            "export HOME=" + repr(str(self.home)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_apply\n",
            encoding="utf-8")
        environment = {
            "HOME": str(self.home),
            "PATH": f"{self.tools}:/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_CATALOG_DIR": str(self.catalog),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "FAKE_MAGPIE_FAIL_PLUGIN_LIST": "1",
            "MAGPIE_APP": str(self.fake),
            "DEPLOY_PLATFORM": "macos",
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        result = subprocess.run(["/bin/bash", str(script)], env=environment,
                                capture_output=True, text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read the Magpie plugin list", result.stderr)
        self.assertEqual([command for command in self.commands() if command.startswith("plugin add")], [])

    def test_the_openai_stack_drains_the_plan_then_the_api_then_kimi_max(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        stack = [command for command in commands if command.startswith("group add openai-stack")]
        self.assertEqual(stack, [
            "group add openai-stack models=group/chatgpt,openai/gpt-6.1-sol:medium,openai/gpt-6.1-terra:high,"
            "kimi-code-cn/k3.1-pro:max routing=drain stays=auto listed=yes"], commands)
        conductor = [command for command in commands if command.startswith("group add conductor")]
        self.assertEqual(conductor, [
            "group add conductor models=codex/gpt-6.2-sol:medium,openai/gpt-6.2-sol:medium,"
            "kimi-code-cn/k3.1-pro:max routing=drain stays=auto listed=yes"], commands)
        self.assertNotIn("gpt-6.1-terra", conductor[0])

    def write_catalog(self, name, text):
        (self.catalog / name).write_text(text, encoding="utf-8")

    def read_catalog(self, name):
        return (self.catalog / name).read_text(encoding="utf-8")

    def test_a_local_proxy_is_resolved_at_call_time(self):
        self.seed_home()
        config = self.home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[data]\n    proxyUrl = "http://127.0.0.1:7890"\n', encoding="utf-8")
        helper = self.tools / "with-proxy"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text('#!/bin/sh\n[ "$1" = --print-url-if-available ] && echo http://127.0.0.1:7897\n', encoding="utf-8")
        helper.chmod(0o755)
        environment = {"MAGPIE_PROXY_URL": "", "PATH": f"{self.tools}:/usr/bin:/bin"}
        result = self.apply(environment=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settings set proxy http://127.0.0.1:7897", self.commands())

    def test_an_unavailable_default_proxy_preserves_the_gateway_setting(self):
        self.seed_home()
        config = self.home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[data]\n    proxyUrl = "http://127.0.0.1:7890"\n', encoding="utf-8")
        shutil.copy2(SOURCE / "dot_local/bin/executable_with-proxy", self.tools / "with-proxy")
        (self.tools / "with-proxy").chmod(0o755)
        nc = self.tools / "nc"
        nc.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        nc.chmod(0o755)
        (self.state / "proxy.txt").write_text(json.dumps("http://proxy.example.invalid:8080"))
        result = self.apply(environment={"MAGPIE_PROXY_URL": ""})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(command.startswith("settings set proxy") for command in self.commands()))
        self.assertEqual(json.loads((self.state / "proxy.txt").read_text()),
                         "http://proxy.example.invalid:8080")
        self.assertIn("no proxy endpoint available", result.stdout)

    def test_a_custom_local_template_proxy_is_used_as_it_is(self):
        self.seed_home()
        config = self.home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[data]\n    proxyUrl = "http://127.0.0.1:1234"\n', encoding="utf-8")
        result = self.apply(environment={"MAGPIE_PROXY_URL": ""})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settings set proxy http://127.0.0.1:1234", self.commands())

    def test_an_explicit_template_environment_overrides_the_default_probe(self):
        result = self.apply(environment={"MAGPIE_PROXY_URL": "",
                                         "HTTP_PROXY_URL": "http://127.0.0.1:7890"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settings set proxy http://127.0.0.1:7890", self.commands())

    def test_a_remote_proxy_from_the_template_is_used_as_it_is(self):
        self.seed_home()
        config = self.home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[data]\n    proxyUrl = "http://proxy.example.invalid:8080"\n', encoding="utf-8")
        result = self.apply(environment={"MAGPIE_PROXY_URL": ""})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settings set proxy http://proxy.example.invalid:8080", self.commands())

    def test_the_missing_cask_is_reported_with_the_install_command(self):
        result = self.apply(environment={"MAGPIE_APP_ROOT": str(self.root / "no-apps")})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("brew install --cask magpie", result.stderr)

    def test_macos_never_passes_a_missing_provider_key_in_arguments(self):
        result = self.apply(setup=lambda: self.provision(["zed"]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("magpie tui", result.stderr)
        self.assertNotIn("sk-fixture", result.stdout + result.stderr)
        self.assertFalse(any(command.startswith("provider add") for command in self.commands()))
        self.assertFalse(any("sk-fixture" in command for command in self.commands()))

    def test_a_missing_optional_provider_warns_and_the_apply_continues(self):
        text = self.read_catalog("providers.tsv").replace(
            "minimax-cn|minimax-cn|json:~/.pi/agent/auth.json:minimax-cn.key|yes",
            "minimax-cn|minimax-cn|json:~/.pi/agent/auth.json:minimax-cn.key|no")
        self.write_catalog("providers.tsv", text)

        # Keep the optional key in the fixture store, but omit its provider.
        result = self.apply(setup=lambda: self.provision(
            ["opencode-go", "kimi-code-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the provider minimax-cn needs its key provisioned interactively", result.stderr)
        self.assertFalse(any("sk-fixture" in command for command in self.commands()))

    def test_an_absent_plugin_account_is_not_reported_as_a_tui_key(self):
        result = self.apply(setup=lambda: self.provision(
            ["opencode-go", "kimi-code-cn", "minimax-cn", "openai"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the provider zed has no credential", result.stdout)
        self.assertNotIn("zed preset", result.stderr)

    def test_an_absent_optional_key_provider_is_reported_on_native_hosts(self):
        # A key-requiring provider that is optional and absent must be reported
        # without putting a key in argv on either native platform. The available
        # providers and groups still apply.
        text = self.read_catalog("providers.tsv").replace(
            "minimax-cn|minimax-cn|json:~/.pi/agent/auth.json:minimax-cn.key|yes",
            "minimax-cn|minimax-cn|json:~/.pi/agent/auth.json:minimax-cn.key|no")
        self.write_catalog("providers.tsv", text)
        for platform in ("linux", "wsl"):
            with self.subTest(platform=platform):
                def setup():
                    # A fresh fake state per platform keeps each subtest a
                    # standalone apply. Every key provider but minimax-cn is
                    # present; the absent provider's fixture credential stays
                    # in the store so passing it to the CLI would be detectable.
                    shutil.rmtree(self.state, ignore_errors=True)
                    shutil.rmtree(self.home / ".local/state/dotfiles/magpie", ignore_errors=True)
                    self.provision(["opencode-go", "kimi-code-cn", "openai", "zed"])

                result = self.apply(platform=platform, setup=setup)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("the provider minimax-cn needs its key provisioned interactively",
                              result.stderr)
                # No provider add for the absent provider, and no key in argv.
                self.assertNotIn("provider add minimax-cn", self.commands())
                self.assertFalse(any("sk-fixture" in command for command in self.commands()),
                                 self.commands())
                # The apply proceeds through the available providers and groups.
                self.assertIn("provider add codex", self.commands())
                self.assertTrue(self.state_file().is_file())

    def test_a_required_model_without_a_live_match_fails_with_the_model_list(self):
        self.seed_home()
        text = self.read_catalog("models.tsv").replace(
            "conductor.kimi|kimi-code-cn/k3.1-pro|yes", "conductor.kimi|kimi-code-cn/k3.9-absent|yes")
        self.write_catalog("models.tsv", text)
        result = self.apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the model role conductor.kimi has no model the gateway serves", result.stderr)
        self.assertIn("kimi-code-cn/k3.1-pro", result.stderr)

    def test_an_optional_candidate_is_reported_and_skipped(self):
        self.seed_home()
        text = self.read_catalog("models.tsv").replace(
            "conductor.kimi|kimi-code-cn/k3.1-pro|yes", "conductor.kimi|kimi-code-cn/k3.1-pro,kimi-code-cn/k3.9-absent?|yes")
        self.write_catalog("models.tsv", text)
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the optional model kimi-code-cn/k3.9-absent is not served; skipped", result.stdout)

    def test_an_apply_without_a_gateway_fails_with_the_open_command(self):
        self.seed_home()
        silent = self.tools / "silent-magpie"
        silent.parent.mkdir(parents=True, exist_ok=True)
        silent.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        silent.chmod(0o755)
        result = self.apply(environment={"MAGPIE_BIN": str(silent)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the gateway does not answer", result.stderr)
        self.assertIn("open the Magpie app", result.stderr)
        self.assertFalse(self.state_file().exists())

    def test_an_apply_on_a_platform_without_magpie_reports_the_skip(self):
        self.seed_home()
        script = self.root / "apply.sh"
        script.write_text(
            "export HOME=" + repr(str(self.home)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_apply\n",
            encoding="utf-8")
        environment = {
            "HOME": str(self.home),
            "PATH": f"{self.tools}:/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_CATALOG_DIR": str(self.catalog),
            "DEPLOY_PLATFORM": "windows",
        }
        result = subprocess.run(["/bin/bash", str(script)], env=environment,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Magpie is not available on this platform; skipped", result.stdout)
        self.assertEqual(self.commands(), [])

    def test_the_release_catalog_owns_the_pinned_linux_digests(self):
        rows = (CATALOG / "releases.tsv").read_text(encoding="utf-8").splitlines()
        self.assertIn("magpie|0.1.4404|linux-amd64|https://github.com/yetone/magpie/releases/download/"
                      "v0.1.4404/magpie-cli-linux-amd64|"
                      "8d22941cff747677d09dce8131e74d76f06f0acfc1af249f942cbbbec058dfba", rows)
        self.assertIn("magpie|0.1.4404|linux-arm64|https://github.com/yetone/magpie/releases/download/"
                      "v0.1.4404/magpie-cli-linux-arm64|"
                      "0ff5d9a9baedde4b8038a8ab8b08cfe3ad859afc721186da17b45386f94f763c", rows)
        # The catalog also pins the macOS CLI assets used when the app is absent.
        self.assertIn("magpie|0.1.4404|macos-amd64|https://github.com/yetone/magpie/releases/download/"
                      "v0.1.4404/magpie-cli-darwin-amd64|"
                      "d939a17e93956a50bc433d1a5356a3da0d7fc960c1988c7fa2890416ba11bfaa", rows)
        self.assertIn("magpie|0.1.4404|macos-arm64|https://github.com/yetone/magpie/releases/download/"
                      "v0.1.4404/magpie-cli-darwin-arm64|"
                      "2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132", rows)
        # The catalog carries the Windows targets too, so the version and the
        # digests of the release live in one place for the later adapter.
        self.assertTrue(any(row.startswith("magpie|0.1.4404|windows-amd64|") for row in rows))
        self.assertTrue(any(row.startswith("magpie|0.1.4404|windows-arm64|") for row in rows))

    def test_the_release_catalog_validates(self):
        script = self.root / "release.sh"
        script.write_text(
            "DEPLOY_SOURCE=" + repr(str(SOURCE)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_release_validate " + repr(str(CATALOG / "releases.tsv")) + "\n",
            encoding="utf-8")
        result = subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr.strip(), "")

    def test_release_target_resolves_both_macos_architectures(self):
        for arch, expected in (("x86_64", "macos-amd64"), ("aarch64", "macos-arm64")):
            with self.subTest(arch=arch):
                result = subprocess.run(
                    ["/bin/bash", "-c", 'source "$1"; magpie_release_target', "fixture", str(ENGINE)],
                    env={"HOME": str(self.root), "PATH": "/usr/bin:/bin", "DEPLOY_PLATFORM": "macos",
                         "DEPLOY_ARCH": arch}, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_a_release_row_without_a_digest_is_rejected(self):
        catalog = self.root / "releases.tsv"
        catalog.write_text(
            "magpie|0.1.4404|linux-amd64|https://example.invalid/magpie-cli-linux-amd64|short\n",
            encoding="utf-8")
        script = self.root / "release.sh"
        script.write_text(
            "DEPLOY_SOURCE=" + repr(str(SOURCE)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_release_validate " + repr(str(catalog)) + "\n",
            encoding="utf-8")
        result = subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the Magpie release digest must be a lowercase SHA-256", result.stderr)

    def test_a_release_row_without_https_is_rejected(self):
        catalog = self.root / "releases.tsv"
        catalog.write_text(
            "magpie|0.1.4404|linux-amd64|http://example.invalid/magpie|"
            "8d22941cff747677d09dce8131e74d76f06f0acfc1af249f942cbbbec058dfba\n",
            encoding="utf-8")
        script = self.root / "release.sh"
        script.write_text(
            "DEPLOY_SOURCE=" + repr(str(SOURCE)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_release_validate " + repr(str(catalog)) + "\n",
            encoding="utf-8")
        result = subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the Magpie release URL must use HTTPS", result.stderr)

    def test_macos_apply_uses_the_verified_cli_when_the_app_is_missing(self):
        # The installed fixture is also the gateway CLI: leave MAGPIE_BIN
        # unset so the engine must select the verified native executable.
        self.native_cli.write_text(FAKE_MAGPIE, encoding="utf-8")
        digest = hashlib.sha256(self.native_cli.read_bytes()).hexdigest()
        self.native_release_catalog.write_text(
            "magpie|0.1.4404|macos-amd64|https://example.invalid/asset|" + digest + "\n"
            "magpie|0.1.4404|macos-arm64|https://example.invalid/asset|" + digest + "\n",
            encoding="utf-8")
        result = self.apply(environment={
            "MAGPIE_BIN": "",
            "MAGPIE_APP": str(self.root / "missing-app"),
            "MAGPIE_CLI_BIN": str(self.native_cli),
            "MAGPIE_RELEASE_CATALOG": str(self.native_release_catalog),
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the CLI 0.1.4404 is installed", result.stdout)
        self.assertIn("status --json", self.commands())

    def test_the_native_apply_wires_the_clients_only_after_the_gateway_answers(self):
        def provision_existing():
            # Every key-requiring provider is already provisioned; only the
            # credential-free Codex account is added by this apply.
            self.provision(["opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"])

        result = self.apply(platform="linux", setup=provision_existing)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertEqual(commands[0], "status --json")
        self.assertLess(commands.index("status --json"), commands.index("provider add codex"))
        self.assertIn("the CLI 0.1.4404 is installed", result.stdout)
        self.assertTrue(self.state_file().is_file())

    def test_the_native_apply_fails_with_the_start_command_when_the_gateway_is_down(self):
        result = self.apply(platform="linux", environment={"FAKE_MAGPIE_FAIL_STATUS": "1",
                                                           "MAGPIE_START_ATTEMPTS": "2"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the gateway does not answer", result.stderr)
        self.assertIn("dotfiles-magpie start", result.stderr)
        # A headless host owns no service registration: the deployment never
        # writes a systemd unit, a login item, or a registry key.
        self.assertFalse((self.home / ".config/systemd").exists())
        self.assertFalse((self.home / ".local/share/systemd").exists())
        self.assertFalse((self.home / ".config/systemd/user").exists())
        # No client is wired to a gateway that is not there.
        self.assertEqual([command for command in self.commands() if command.startswith("provider add")], [])
        self.assertFalse(self.state_file().exists())

    def test_the_temporary_deployment_proxy_is_not_written_into_the_gateway(self):
        # The deployment started this proxy: its URL matches DEPLOY_PROXY_URL
        # and it recorded a PID, so it owns the endpoint even on port 7890.
        url = "http://127.0.0.1:7890"
        result = self.apply(platform="linux", environment={
            "MAGPIE_PROXY_URL": url,
            "DEPLOY_PROXY_URL": url,
            "DEPLOY_PROXY_PID": "4242",
        }, setup=lambda: self.provision(
            ["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("settings set proxy", self.commands())
        self.assertIn("the deployment proxy is temporary", result.stdout)

    def test_macos_app_does_not_persist_the_temporary_proxy(self):
        url = "http://127.0.0.1:7890"
        result = self.apply(credentials=False, environment={
            "MAGPIE_PROXY_URL": url,
            "DEPLOY_PROXY_URL": url,
            "DEPLOY_PROXY_PID": "4242",
        }, setup=lambda: self.provision(
            ["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(command.startswith("settings set proxy") for command in self.commands()))
        self.assertIn("deployment proxy is temporary", result.stdout)

    def test_macos_cli_fallback_does_not_persist_the_temporary_proxy(self):
        url = "http://127.0.0.1:7890"
        result = self.apply(credentials=False, environment={
            "MAGPIE_APP": str(self.root / "missing-app"),
            "MAGPIE_CLI_BIN": str(self.native_cli),
            "MAGPIE_RELEASE_CATALOG": str(self.native_release_catalog),
            "MAGPIE_PROXY_URL": url,
            "DEPLOY_PROXY_URL": url,
            "DEPLOY_PROXY_PID": "4242",
        }, setup=lambda: self.provision(
            ["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(command.startswith("settings set proxy") for command in self.commands()))
        self.assertIn("deployment proxy is temporary", result.stdout)

    def test_a_device_proxy_on_a_deployment_port_is_written_into_the_gateway(self):
        # Same port, no ownership: the deployment reuses a proxy already on
        # 7890, so DEPLOY_PROXY_URL names it but no PID is recorded. It belongs
        # to the device and must be preserved, not treated as temporary.
        url = "http://127.0.0.1:7890"
        result = self.apply(platform="linux", environment={
            "MAGPIE_PROXY_URL": url,
            "DEPLOY_PROXY_URL": url,
        }, setup=lambda: self.provision(
            ["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settings set proxy " + url, self.commands())
        self.assertNotIn("the deployment proxy is temporary", result.stdout)

    def test_a_proxy_at_a_different_url_is_not_the_deployment_proxy(self):
        # A recorded PID and URL are not enough: the proxy the gateway resolves
        # must be the exact URL the deployment started to be owned.
        result = self.apply(platform="linux", environment={
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7890",
            "DEPLOY_PROXY_URL": "http://127.0.0.1:7891",
            "DEPLOY_PROXY_PID": "4242",
        }, setup=lambda: self.provision(
            ["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settings set proxy http://127.0.0.1:7890", self.commands())
        self.assertNotIn("the deployment proxy is temporary", result.stdout)

    def test_a_device_proxy_is_written_into_the_gateway(self):
        result = self.apply(platform="linux", setup=lambda: self.provision(
            ["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("settings set proxy http://127.0.0.1:7897", self.commands())

    def test_the_launcher_runs_the_native_cli_on_a_headless_host(self):
        launcher = self.home / ".local/bin/magpie"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_magpie", launcher)
        launcher.chmod(0o755)
        cli = self.root / "magpie-native-cli"
        cli.write_text("#!/bin/sh\necho 'magpie 0.1.4404'\n", encoding="utf-8")
        cli.chmod(0o755)
        result = subprocess.run([str(launcher), "--version"],
                                env={"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                                     "DEPLOY_PLATFORM": "linux", "MAGPIE_CLI": str(cli)},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("magpie 0.1.4404", result.stdout)

    def test_the_launcher_names_the_install_command_when_the_native_cli_is_missing(self):
        launcher = self.home / ".local/bin/magpie"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_magpie", launcher)
        launcher.chmod(0o755)
        result = subprocess.run([str(launcher), "--version"],
                                env={"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                                     "DEPLOY_PLATFORM": "linux"},
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dotfiles-magpie install", result.stderr)

    def test_the_backups_are_private_and_only_ten_are_kept(self):
        self.seed_home()
        backups = self.home / ".local/state/dotfiles/magpie/backups"
        for index in range(10):
            stale = backups / ("20200101T0000%02dZ" % index)
            stale.mkdir(parents=True)
            (stale / "settings.json").write_text("{}", encoding="utf-8")
            (stale / "settings.json").chmod(0o600)
        self.assertEqual(self.apply().returncode, 0)
        kept = sorted(path.name for path in backups.iterdir())
        self.assertEqual(len(kept), 10)
        self.assertNotIn("20200101T000000Z", kept)
        latest = backups / kept[-1]
        # Claude's and Pi's settings.json share a basename; both survive.
        self.assertTrue((latest / ".claude/settings.json").is_file())
        self.assertTrue((latest / ".pi/agent/settings.json").is_file())
        self.assertTrue((latest / "dsh-default/cordis.patch.yml").is_file())
        for path in backups.rglob("*"):
            if path.is_file():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600, path)

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

    def test_a_missing_required_provider_fails_with_provisioning_guidance(self):
        result = self.apply(credentials=False, setup=lambda: self.provision(["zed"]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kimi-code-cn preset", result.stderr)
        self.assertIn("opencode-go preset", result.stderr)
        self.assertIn("magpie tui", result.stderr)

    def test_a_linux_apply_fails_closed_before_passing_a_provider_key_in_argv(self):
        result = self.apply(platform="linux", setup=lambda: self.provision(["zed"]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provisioned interactively", result.stderr)
        self.assertIn("apply again", result.stderr)
        # The CLI takes the key in argv and does not prompt; the TUI is the
        # masked entry point. The old text wrongly sent the operator to
        # `magpie provider add <preset>` to paste a key at a prompt.
        self.assertIn("magpie tui", result.stderr)
        self.assertIn("kimi-code-cn preset", result.stderr)
        self.assertNotIn("run: magpie provider add", result.stderr)
        self.assertNotIn("paste the key at the prompt", result.stderr)
        # A key passed to `provider add` would be readable from another
        # process's argv, so no provider is added and no fixture key appears.
        self.assertFalse(any("sk-fixture" in command for command in self.commands()),
                         self.commands())
        self.assertEqual([command for command in self.commands()
                          if command.startswith("provider add")], [])

    def test_a_required_key_provider_stops_the_wsl_apply_before_mutations(self):
        result = self.apply(platform="wsl", setup=lambda: self.provision(["zed"]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provisioned interactively", result.stderr)
        self.assertIn("magpie tui", result.stderr)
        # A required, used key provider still stops the apply before any
        # mutation: no provider is added, no key reaches argv, no state written.
        self.assertEqual([command for command in self.commands()
                          if command.startswith("provider add")], [])
        self.assertFalse(any("sk-fixture" in command for command in self.commands()),
                         self.commands())
        self.assertFalse(self.state_file().exists())

    def test_a_linux_apply_keeps_an_already_provisioned_provider_working(self):
        result = self.apply(platform="linux", setup=lambda: self.provision(
            ["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([command for command in self.commands()
                          if command.startswith("provider add")], [])

    def test_a_linux_apply_still_adds_the_credential_free_codex_account(self):
        result = self.apply(platform="linux", setup=lambda: self.provision(
            ["opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([command for command in self.commands()
                          if command.startswith("provider add")], ["provider add codex"])

    def test_gateway_backup_preserves_settings_before_the_initial_merge(self):
        if not self.chezmoi:
            self.skipTest("client settings merge requires chezmoi")
        result = self.apply(merger=True, premerge=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = list((self.home / ".local/state/dotfiles/magpie/backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / ".claude/settings.json").read_text(), '{"model":"opus"}\n')
        self.assertEqual((backups[0] / ".pi/agent/settings.json").read_text(), '{"defaultProvider":"x"}\n')
        claude = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(claude["env"]["ANTHROPIC_BASE_URL"], "http://127.0.0.1:3425")

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
            "PATH": f"{self.tools}:/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_CATALOG_DIR": str(self.catalog),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "FAKE_MAGPIE_TOUCH_CODEX": "1",
            "MAGPIE_APP": str(self.fake),
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
        self.assertTrue((backups[0] / ".codex/config.toml").is_file())

    def test_the_apply_leaves_the_dsh_profile_alone(self):
        self.seed_home()
        patch = self.home / ".dsh/profiles/default/cordis.patch.yml"
        before = patch.read_bytes()
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(patch.read_bytes(), before)
        self.assertNotIn("codex", [command.split(" ")[0] for command in self.commands()])

    def test_a_changed_official_deepseek_row_aborts_the_apply(self):
        self.seed_home()
        script = self.root / "apply.sh"
        script.write_text(
            "export HOME=" + repr(str(self.home)) + "\n"
            "source " + repr(str(ENGINE)) + "\n"
            "magpie_apply\n",
            encoding="utf-8")
        environment = {
            "HOME": str(self.home),
            "PATH": f"{self.tools}:/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_CATALOG_DIR": str(self.catalog),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "FAKE_MAGPIE_TOUCH_DSH": "1",
            "MAGPIE_APP": str(self.fake),
            "DEPLOY_PLATFORM": "macos",
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        result = subprocess.run(["/bin/bash", str(script)], env=environment,
                                capture_output=True, text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the official DeepSeek row of the DSH profile default changed", result.stderr)

    def test_the_apply_keeps_the_codex_configuration_untouched(self):
        codex = self.home / ".codex/config.toml"
        self.apply()
        self.assertEqual(codex.read_text(encoding="utf-8"), 'model = "gpt-6-luna"\n')

    def test_the_reapply_repairs_a_missing_pi_model_file(self):
        self.assertEqual(self.apply().returncode, 0)
        models = self.home / ".pi/agent/models.json"
        self.assertTrue(models.is_file())
        # Magpie generates the model file when it wires Pi. A device that lost
        # it keeps the recorded wiring, so only the file proves the wiring is
        # gone.
        models.unlink()
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the Pi model file is missing", result.stdout)
        self.assertTrue(models.is_file())
        # The agent is wired again even though the recorded state still names
        # the group.
        self.assertEqual([command for command in self.commands() if command == "pi group/workhorse"],
                         ["pi group/workhorse", "pi group/workhorse"])
        self.assertIn("wiring|pi|group/workhorse", self.state_file().read_text(encoding="utf-8"))

    def test_the_apply_routes_dsh_compaction_to_workhorse(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dsh_compact_value(), "group/workhorse")
        self.assertEqual(self.dsh_compact_commands(),
                         ["dsh compact_model", "dsh compact_model group/workhorse"])
        self.assertIn("dsh-compact|group/workhorse", self.state_file().read_text(encoding="utf-8"))

    def test_a_second_apply_does_not_rewrite_the_compaction_choice(self):
        self.assertEqual(self.apply().returncode, 0)
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("compaction already uses group/workhorse", result.stdout)
        # The first apply reads then sets; the second reads again and stops.
        # The recorded order is getter, setter, getter.
        self.assertEqual(self.dsh_compact_commands(),
                         ["dsh compact_model", "dsh compact_model group/workhorse",
                          "dsh compact_model"])

    def test_an_already_correct_compaction_choice_is_left_alone(self):
        self.seed_home()
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "dsh-compact.json").write_text(json.dumps({"value": "group/workhorse"}))
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dsh_compact_commands(), ["dsh compact_model"])

    def test_the_compaction_group_stays_workhorse_when_the_main_wiring_moves_to_conductor(self):
        # Compaction is a lightweight auxiliary route. Moving DSH's main
        # session group to the conductor tier must not drag it along; the
        # enabled Magpie-owned row still only gates whether we set it at all.
        wiring = self.catalog / "wiring.tsv"
        wiring.write_text(wiring.read_text().replace(
            "dsh|group/workhorse|magpie|yes", "dsh|group/conductor|magpie|yes"))
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dsh_compact_value(), "group/workhorse")
        self.assertIn("dsh compact_model group/workhorse", self.commands())
        # The DSH session itself still starts on the conductor group.
        self.assertIn("dsh group/conductor", self.commands())

    def test_a_disabled_dsh_wiring_row_leaves_compaction_alone(self):
        wiring = self.catalog / "wiring.tsv"
        wiring.write_text(wiring.read_text().replace(
            "dsh|group/workhorse|magpie|yes", "dsh|group/workhorse|magpie|no"))
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dsh_compact_value(), "")
        self.assertEqual(self.dsh_compact_commands(), [])

    def test_the_compaction_change_backs_up_its_previous_value(self):
        self.seed_home()
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "dsh-compact.json").write_text(json.dumps({"value": "codex/gpt-6-luna"}))
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = self.home / ".local/state/dotfiles/magpie/backups"
        directories = list(backups.iterdir())
        self.assertEqual(len(directories), 1)
        record = directories[0] / "dsh-compact-model.txt"
        self.assertEqual(record.read_text().strip(), "codex/gpt-6-luna")
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)

    def test_the_compaction_set_preserves_unrelated_state(self):
        self.seed_home()
        self.state.mkdir(parents=True, exist_ok=True)
        # The fake CLI stores the proxy as JSON. Seeding it any other way makes
        # the getter unreadable, which would rewrite it for unrelated reasons.
        proxy = self.state / "proxy.txt"
        original = json.dumps("http://127.0.0.1:7897").encode()
        proxy.write_bytes(original)
        patch = self.home / ".dsh/profiles/default/cordis.patch.yml"
        before = patch.read_bytes()
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(patch.read_bytes(), before)
        self.assertEqual(proxy.read_bytes(), original)
        self.assertEqual(self.dsh_compact_value(), "group/workhorse")

    def test_a_codex_change_during_compaction_aborts_and_keeps_the_backup(self):
        result = self.apply(environment={"FAKE_MAGPIE_TOUCH_CODEX_ON_COMPACT": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the Codex configuration changed during the apply", result.stderr)
        self.assertTrue(list((self.home / ".local/state/dotfiles/magpie/backups").iterdir()))

    def test_an_unreadable_compaction_read_aborts_without_setting_it(self):
        result = self.apply(environment={"FAKE_MAGPIE_FAIL_DSH_COMPACT_GET": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read the DeepSeek Harness compaction model", result.stderr)
        self.assertEqual(self.dsh_compact_value(), "")
        self.assertEqual([command for command in self.commands()
                          if command == "dsh compact_model group/workhorse"], [])

    def test_a_failing_compaction_set_aborts_the_apply(self):
        result = self.apply(environment={"FAKE_MAGPIE_FAIL_DSH_COMPACT_SET": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot set the DeepSeek Harness compaction model", result.stderr)
        self.assertEqual(self.dsh_compact_value(), "")

    def test_an_unavailable_gateway_never_sets_compaction(self):
        result = self.apply(platform="linux", environment={"FAKE_MAGPIE_FAIL_STATUS": "1",
                                                           "MAGPIE_START_ATTEMPTS": "0"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.dsh_compact_commands(), [])

    def test_a_repo_owned_dsh_wiring_row_leaves_compaction_alone(self):
        wiring = self.catalog / "wiring.tsv"
        wiring.write_text(wiring.read_text().replace(
            "dsh|group/workhorse|magpie|yes", "dsh|group/workhorse|repo|yes"))
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dsh_compact_value(), "")
        self.assertEqual(self.dsh_compact_commands(), [])

    def test_an_agent_selection_without_dsh_preserves_gateway_settings(self):
        def setup():
            settings = self.home / ".config/magpie/settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({"pickedModels": {"dsh": ["device/model"]}}))
            (self.state / "visible.json").write_text(json.dumps({"dsh": "device-provider"}))
            (self.state / "dsh-compact.json").write_text(json.dumps({"value": "device/model"}))

        result = self.apply(shell=["DEPLOY_AGENTS=(claude pi)"], setup=setup)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        settings = json.loads((self.home / ".config/magpie/settings.json").read_text())
        self.assertEqual(settings["pickedModels"]["dsh"], ["device/model"])
        self.assertIn("pi", settings["pickedModels"])
        self.assertEqual(json.loads((self.state / "visible.json").read_text())["dsh"], "device-provider")
        self.assertEqual(self.dsh_compact_value(), "device/model")
        self.assertFalse(any(command.startswith(("dsh ", "visible dsh "))
                             for command in self.commands()))
        self.assertNotIn("wiring|dsh|", self.state_file().read_text())
        result = self.apply(shell=["DEPLOY_AGENTS=(claude pi dsh)"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dsh group/workhorse", self.commands())
        self.assertIn("wiring|dsh|group/workhorse", self.state_file().read_text())
        self.assertNotIn("selection|dsh|excluded", self.state_file().read_text())

    def test_an_agent_selection_without_dsh_leaves_compaction_alone(self):
        # The public bootstrap resolves DOTFILES_AGENTS (or --agents) into
        # DEPLOY_AGENTS before it sources the engine. A selection that leaves
        # DSH out must not touch its compaction field even though the wiring
        # row is enabled and Magpie-owned.
        result = self.apply(shell=["DEPLOY_AGENTS=(claude pi)"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dsh_compact_value(), "")
        self.assertEqual(self.dsh_compact_commands(), [])

    def test_an_agent_selection_with_dsh_keeps_the_compaction_route(self):
        result = self.apply(shell=["DEPLOY_AGENTS=(claude pi dsh)"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dsh_compact_value(), "group/workhorse")
        self.assertEqual(self.dsh_compact_commands(),
                         ["dsh compact_model", "dsh compact_model group/workhorse"])

    def test_the_apply_fails_closed_on_a_malformed_getter_answer(self):
        # The fake CLI prints a successful but unparsable answer at the process
        # boundary. Apply must not treat it as an unset field and must never
        # hand an invented value to the setter. The pinned answers themselves
        # (default, matching, other value) are covered through apply above and
        # through status below; no private getter is called here.
        for output in (
            "garbage",
            "DeepSeek Harness compaction model surprise",
            "DeepSeek Harness compaction model magpie/group",
            "DeepSeek Harness compaction model magpie//workhorse",
            "DeepSeek Harness compaction model magpie/group/workhorse/extra",
        ):
            with self.subTest(output=output):
                result = self.apply(environment={"FAKE_MAGPIE_DSH_COMPACT_GET_OUTPUT": output})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("cannot read the DeepSeek Harness compaction model", result.stderr)
                self.assertEqual(self.dsh_compact_value(), "")
                self.assertEqual([command for command in self.commands()
                                  if command == "dsh compact_model group/workhorse"], [])


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
    def test_the_linux_and_wsl_plans_wire_the_gateway(self):
        for platform in ("linux", "wsl"):
            with self.subTest(platform=platform):
                plan = self.plan("--platform", platform)
                self.assertTrue(plan["magpie"])
                self.assertIn("magpie-apply", plan["actions"])
                self.assertLess(plan["actions"].index("magpie-apply"), plan["actions"].index("prepare-shell"))

    def test_the_switch_removes_the_step_on_a_headless_host(self):
        for arguments, environment in ((["--no-magpie"], None), ([], dict(DOTFILES_MAGPIE="false"))):
            with self.subTest(arguments=arguments):
                plan = self.plan("--platform", "linux", *arguments,
                                 environment=dict(self.env, **(environment or {})))
                self.assertFalse(plan["magpie"])
                self.assertNotIn("magpie-apply", plan["actions"])

    def test_the_windows_plan_reports_no_gateway_and_fails_nothing(self):
        plan = self.plan("--platform", "windows", "--arch", "x86_64")
        self.assertFalse(plan["magpie"])
        self.assertNotIn("magpie-apply", plan["actions"])

    def test_full_bootstrap_guard_preserves_client_settings_on_a_synthetic_home(self):
        # A full bootstrap with the gateway enabled probes the real account's
        # loopback port, so the guard refuses a synthetic home before creating
        # any state. This replaces the earlier failed-bootstrap snapshot-cleanup
        # scenario: a synthetic home can no longer reach the snapshot step, and
        # faking a bypass in production to keep that assertion is not allowed.
        # The snapshot-cleanup assertion is therefore retired, not weakened.
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"model":"opus"}\n', encoding="utf-8")
        environment = dict(self.env, DOTFILES_PIXI_BIN="/usr/bin/false")
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "macos"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("simulated or foreign home", result.stderr)
        self.assertIn("--no-magpie", result.stderr)
        # The guard fires before the snapshot and installer steps, so even a
        # failing pixi is never reached and the pre-existing client settings
        # survive byte-for-byte.
        self.assertNotIn("install-managers.pixi", result.stderr)
        self.assertEqual(settings.read_text(encoding="utf-8"), '{"model":"opus"}\n')
        # No target-home state means no temporary snapshot and no backups tree.
        self.assertEqual(list((self.home / ".cache/tmp").glob("magpie-clients.*")), [])
        self.assertFalse((self.home / ".local/state/dotfiles/magpie/backups").exists())
        self.assertEqual([path for path in self.home.rglob("*") if path.is_file()], [settings])

    def test_a_restricted_apply_says_why_the_gateway_is_skipped(self):
        if not self.chezmoi:
            self.skipTest("actual apply requires chezmoi")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi)
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "linux", "--apply-only"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dotfiles: magpie: skipped;", result.stdout)

    def test_restricted_modes_keep_the_compaction_step_out(self):
        # DSH compaction lives inside magpie-apply, so a restricted bootstrap
        # that skips the step cannot reach the compaction field.
        for arguments in (["--apply-only"], ["--agents-only"]):
            with self.subTest(arguments=arguments):
                plan = self.plan("--platform", "macos", *arguments)
                self.assertNotIn("magpie-apply", plan["actions"])


class MagpieCommandTests(MagpieApplyTests):
    """The managed command runs the same engine the deployment step runs."""

    def setUp(self):
        super().setUp()
        self.command = self.home / ".local/bin/dotfiles-magpie"
        self.command.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_dotfiles-magpie", self.command)
        self.command.chmod(0o755)
        # The command resolves the platform and the account home natively, so
        # its guard rejects a synthetic HOME. Install the test-only shim at the
        # engine path the command loads by default; it sources the real engine
        # and neutralizes only the two guard inputs.
        engine_dir = self.home / ".local/share/dotfiles/magpie"
        engine_dir.mkdir(parents=True, exist_ok=True)
        install_engine_shim(engine_dir, name="engine.sh")
        catalogs = self.home / ".config/dotfiles/magpie"
        catalogs.mkdir(parents=True, exist_ok=True)
        for name in CATALOGS:
            shutil.copy2(CATALOG / name, catalogs / name)

    def run_command(self, *arguments, environment=None):
        environ = {
            "HOME": str(self.home),
            "PATH": f"{self.tools}:/usr/bin:/bin:/usr/sbin:/sbin",
            "MAGPIE_BIN": str(self.fake),
            "MAGPIE_PROXY_URL": "http://127.0.0.1:7897",
            "FAKE_MAGPIE_STATE": str(self.state),
            "FAKE_MAGPIE_GATEWAY": "http://127.0.0.1:%d" % self.server.server_address[1],
            "MAGPIE_APP": str(self.fake),
            "DEPLOY_PLATFORM": "macos",
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        environ.update(environment or {})
        return subprocess.run([str(self.command), *arguments], env=environ,
                              capture_output=True, text=True, timeout=120)

    def catalog_column(self, name, column):
        values = {}
        for line in (CATALOG / name).read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            values[fields[0]] = fields[column]
        return values

    def healthy_gateway(self):
        """A gateway that answers with every provider, group, visibility and pick."""
        self.healthy_client_wiring()
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "providers.json").write_text(
            json.dumps(["codex", "opencode-go", "kimi-code-cn", "minimax-cn", "openai", "zed"]),
            encoding="utf-8")
        (self.state / "groups.json").write_text(json.dumps({
            "chatgpt": "codex/gpt-6.1-sol:medium,codex/gpt-6.1-terra:high",
            "openai-stack": "group/chatgpt,openai/gpt-6.1-sol:medium,openai/gpt-6.1-terra:high,kimi-code-cn/k3.1-pro:max",
            "conductor": "codex/gpt-6.2-sol:medium,openai/gpt-6.2-sol:medium,kimi-code-cn/k3.1-pro:max",
            "workhorse": "minimax-cn/MiniMax-M3.1-Flash:max,opencode-go/deepseek-v4.1-flash:max",
            "auto-gpt-6-1-sol": "codex/gpt-6.1-sol:medium,openai/gpt-6.1-sol:medium,zed/gpt-6.1-sol:medium",
            "auto-gpt-6-1-terra": "codex/gpt-6.1-terra:high,openai/gpt-6.1-terra:high",
            "auto-gpt-6-luna": "codex/gpt-6-luna,openai/gpt-6-luna,zed/gpt-6-luna,opencode-go/gpt-6-luna",
            "auto-gpt-6-astra": "codex/gpt-6.2-astra,openai/gpt-6.2-astra",
        }), encoding="utf-8")
        (self.state / "visible.json").write_text(
            json.dumps(self.catalog_column("visible.tsv", 1)), encoding="utf-8")
        settings = self.home / ".config/magpie/settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({
            "pickedModels": {
                agent: picks.split(",")
                for agent, picks in self.catalog_column("picked.tsv", 1).items()
            },
        }), encoding="utf-8")
        spec = "@magpie-community/opencode-zed-auth@0.1.19"
        (self.state / "plugins.json").write_text(
            json.dumps({"loaded": [{"spec": spec}], "plugins": [{"spec": spec}]}), encoding="utf-8")
        (self.state / "proxy.txt").write_text(json.dumps("http://127.0.0.1:7897"), encoding="utf-8")
        (self.state / "dsh-compact.json").write_text(
            json.dumps({"value": "group/workhorse"}), encoding="utf-8")

    def test_every_catalog_reaches_the_managed_home(self):
        managed = SOURCE / "dot_config/dotfiles/magpie"
        for name in CATALOGS:
            with self.subTest(catalog=name):
                wrapper = managed / f"{name}.tmpl"
                self.assertTrue(wrapper.is_file(), wrapper)
                self.assertEqual(wrapper.read_text(encoding="utf-8").strip(),
                                 '{{ include "deployment/magpie/%s" }}' % name)

    def test_the_command_applies_the_same_engine(self):
        self.seed_home()
        result = self.run_command("apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("provider add codex", self.commands())
        self.assertFalse(any("sk-fixture" in command for command in self.commands()))
        self.assertTrue(self.state_file().is_file())

    def test_status_respects_the_last_dsh_exclusion(self):
        result = self.apply(shell=["DEPLOY_AGENTS=(claude pi)"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.healthy_gateway()
        settings = self.home / ".config/magpie/settings.json"
        data = json.loads(settings.read_text())
        data["pickedModels"]["dsh"] = ["device/model"]
        settings.write_text(json.dumps(data))
        (self.state / "dsh-compact.json").write_text(json.dumps({"value": "device/model"}))
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wiring|dsh|excluded", result.stdout)
        self.assertNotIn("dsh-compact|drift", result.stdout)
        self.assertNotIn("picked dsh", result.stderr)

    def test_the_status_exits_zero_on_a_healthy_gateway(self):
        self.seed_home()
        self.healthy_gateway()
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("gateway|", result.stdout)
        self.assertIn("group|workhorse|", result.stdout)
        self.assertIn("wiring|pi|group/workhorse", result.stdout)

    def test_the_status_accepts_the_migrated_claude_policy_without_a_subagent_key(self):
        self.seed_home()
        self.healthy_gateway()
        settings = json.loads((self.home / ".claude/settings.json").read_text(encoding="utf-8"))
        env = settings["env"]
        for key in ("ANTHROPIC_DEFAULT_FABLE_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                    "ANTHROPIC_DEFAULT_SONNET_MODEL"):
            self.assertEqual(env[key], "group/conductor", key)
        for key in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                    "CLAUDE_CODE_AUTO_MODE_MODEL"):
            self.assertEqual(env[key], "codex/gpt-6.1-terra", key)
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", env)
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wiring|claude|group/conductor", result.stdout)
        self.assertNotIn("drift", result.stdout)
        self.assertNotIn("wiring claude", result.stderr)

    def test_the_status_preserves_an_explicit_device_subagent_override(self):
        self.seed_home()
        self.healthy_gateway()
        claude = self.home / ".claude/settings.json"
        settings = json.loads(claude.read_text(encoding="utf-8"))
        settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] = "device/custom-model"
        claude.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("drift", result.stdout)
        self.assertNotIn("wiring claude", result.stderr)
        # A device-owned key is neither deployment wiring nor drift: status is
        # read-only and leaves the explicit override exactly as it found it.
        after = json.loads(claude.read_text(encoding="utf-8"))
        self.assertEqual(after["env"]["CLAUDE_CODE_SUBAGENT_MODEL"], "device/custom-model")

    def test_the_status_reports_drift_for_a_wrong_background_alias(self):
        for key in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"):
            with self.subTest(key=key):
                self.seed_home()
                self.healthy_gateway()
                claude = self.home / ".claude/settings.json"
                settings = json.loads(claude.read_text(encoding="utf-8"))
                # The conductor group is the old value; a background alias that
                # still points there is drift under the new policy.
                settings["env"][key] = "group/conductor"
                claude.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
                result = self.run_command("status")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("wiring|claude|drift (env.%s)" % key, result.stdout)
                self.assertIn("wiring claude", result.stderr)

    def test_the_status_reports_drift_for_a_wrong_classifier(self):
        self.seed_home()
        self.healthy_gateway()
        claude = self.home / ".claude/settings.json"
        settings = json.loads(claude.read_text(encoding="utf-8"))
        settings["env"]["CLAUDE_CODE_AUTO_MODE_MODEL"] = "group/conductor"
        claude.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        result = self.run_command("status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wiring|claude|drift (env.CLAUDE_CODE_AUTO_MODE_MODEL)", result.stdout)
        self.assertIn("wiring claude", result.stderr)

    def test_the_status_names_the_drifted_client_wiring(self):
        self.seed_home()
        self.healthy_gateway()
        claude = self.home / ".claude/settings.json"
        settings = json.loads(claude.read_text(encoding="utf-8"))
        settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"] = "group/workhorse"
        claude.write_text(json.dumps(settings), encoding="utf-8")
        pi = self.home / ".pi/agent/settings.json"
        settings = json.loads(pi.read_text(encoding="utf-8"))
        settings["defaultProvider"] = "other"
        pi.write_text(json.dumps(settings), encoding="utf-8")
        result = self.run_command("status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wiring|claude|drift (env.ANTHROPIC_DEFAULT_SONNET_MODEL)", result.stdout)
        self.assertIn("wiring|pi|drift (defaultProvider)", result.stdout)
        self.assertIn("wiring claude", result.stderr)
        self.assertIn("wiring pi", result.stderr)

    def test_the_status_names_a_missing_client_file_and_model_file(self):
        self.seed_home()
        self.healthy_gateway()
        (self.home / ".claude/settings.json").unlink()
        (self.home / ".pi/agent/models.json").unlink()
        result = self.run_command("status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wiring|claude|missing", result.stdout)
        self.assertIn("models|pi|missing", result.stdout)
        self.assertIn("wiring claude", result.stderr)
        self.assertIn("models pi", result.stderr)

    def test_the_status_reports_the_dsh_group_and_the_official_row(self):
        self.seed_home()
        self.healthy_gateway()
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wiring|dsh|group/workhorse", result.stdout)
        self.assertIn("dsh-official-row|default|present", result.stdout)
        self.assertIn("dsh-compact|group/workhorse", result.stdout)

    def test_the_status_reports_a_matched_compaction_setting(self):
        # The live field, not the recorded intent, is the evidence of health.
        self.seed_home()
        self.healthy_gateway()
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dsh-compact|group/workhorse", result.stdout)
        self.assertNotIn("dsh-compact", result.stderr)

    def test_the_status_reports_a_drifted_compaction_setting(self):
        self.seed_home()
        self.healthy_gateway()
        (self.state / "dsh-compact.json").write_text(
            json.dumps({"value": "codex/gpt-6-luna"}), encoding="utf-8")
        result = self.run_command("status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dsh-compact|drift (codex/gpt-6-luna)", result.stdout)
        self.assertIn("dsh-compact", result.stderr)

    def test_recorded_compaction_intent_never_claims_health(self):
        # A state.tsv that says the route was applied is not health: an unset
        # live field is drift even when the recorded intent says otherwise.
        self.seed_home()
        self.healthy_gateway()
        (self.state / "dsh-compact.json").unlink()
        recorded = self.state_file()
        recorded.parent.mkdir(parents=True, exist_ok=True)
        recorded.write_text("dsh-compact|group/workhorse\ncodex-guard|unchanged\n", encoding="utf-8")
        result = self.run_command("status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dsh-compact|drift (default)", result.stdout)
        self.assertIn("dsh-compact", result.stderr)

    def test_the_status_reports_an_unreadable_compaction_setting(self):
        # A successful but malformed getter answer is not an absent field.
        self.seed_home()
        self.healthy_gateway()
        result = self.run_command("status", environment={
            "FAKE_MAGPIE_DSH_COMPACT_GET_OUTPUT": "garbage"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dsh-compact|unreadable", result.stdout)
        self.assertIn("dsh-compact", result.stderr)

    def test_the_status_reports_the_three_visibility_rows(self):
        self.seed_home()
        self.healthy_gateway()
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("visible|claude|" + self.catalog_column("visible.tsv", 1)["claude"], result.stdout)
        self.assertIn("visible|pi|" + self.catalog_column("visible.tsv", 1)["pi"], result.stdout)
        self.assertIn("visible|dsh|" + self.catalog_column("visible.tsv", 1)["dsh"], result.stdout)

    def test_the_test_command_probes_a_role_through_its_first_live_candidate(self):
        self.seed_home()
        result = self.run_command("test", "conductor.deepseek")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("role|model|state|detail", result.stdout)
        self.assertIn("conductor.deepseek|opencode-go/deepseek-v4.1-flash|ok|", result.stdout)
        self.assertEqual(self.server.completions, ["opencode-go/deepseek-v4.1-flash"])
        # The provider-level probe tests a provider's own endpoints, not the
        # model the routers hold, so the command never runs it.
        self.assertFalse(any(command.startswith("provider test") for command in self.commands()))

    def test_the_test_command_probes_every_role_by_default(self):
        self.seed_home()
        result = self.run_command("test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for role in ("chatgpt.sol", "chatgpt.terra", "openai.sol", "openai.terra",
                     "conductor.kimi", "conductor.deepseek", "workhorse.minimax"):
            self.assertIn(role + "|", result.stdout)

    def test_the_test_command_reports_an_error_and_fails(self):
        self.seed_home()
        self.server.reject_completions = True
        result = self.run_command("test", "workhorse.minimax")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workhorse.minimax|minimax-cn/MiniMax-M3.1-Flash|error|the provider refused the turn",
                      result.stdout)

    def test_the_test_command_rejects_an_unknown_role(self):
        self.seed_home()
        result = self.run_command("test", "conductor.absent")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown model role: conductor.absent", result.stderr)
        self.assertEqual(self.server.completions, [])

    def test_the_test_command_fails_a_role_with_no_live_candidate(self):
        self.seed_home()
        catalog = self.home / ".config/dotfiles/magpie"
        text = (catalog / "models.tsv").read_text(encoding="utf-8").replace(
            "workhorse.minimax|minimax-cn/MiniMax-M3.1-Flash|yes",
            "workhorse.minimax|minimax-cn/MiniMax-M9.9|yes")
        (catalog / "models.tsv").write_text(text, encoding="utf-8")
        result = self.run_command("test", "workhorse.minimax")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workhorse.minimax|-|error|no candidate the gateway serves", result.stdout)
        self.assertEqual(self.server.completions, [])

    def test_the_status_reports_the_plugin_state(self):
        self.seed_home()
        self.healthy_gateway()
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("plugin|zed|loaded", result.stdout)

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
        self.provision(["zed"])
        result = self.run_command("providers")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("env:KIMI_CODE_CN_API_KEY", result.stdout)
        self.assertIn("missing", result.stdout)
        self.assertNotIn("sk-fixture", result.stdout)

    def test_the_command_refuses_a_host_that_cannot_run_magpie(self):
        self.seed_home()
        result = self.run_command("status", environment={"DEPLOY_PLATFORM": "windows"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Magpie is not available on this platform", result.stderr)

    def test_start_adopts_a_running_macos_app_gateway_without_a_native_cli(self):
        self.seed_home()
        result = self.run_command("start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("gateway answers", result.stdout)

    def test_the_launcher_reports_the_missing_app_with_the_cask_command(self):
        launcher = self.home / ".local/bin/magpie"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_magpie", launcher)
        launcher.chmod(0o755)
        result = subprocess.run([str(launcher), "--version"],
                                env={"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                                     "MAGPIE_APP": str(self.root / "no-apps/magpie.app/Contents/MacOS/magpie")},
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("brew install --cask magpie", result.stderr)

    def test_the_macos_launcher_falls_back_to_the_native_cli_when_the_app_is_missing(self):
        launcher = self.home / ".local/bin/magpie"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_magpie", launcher)
        launcher.chmod(0o755)
        cli = self.home / ".local/share/dotfiles/magpie/bin/magpie"
        cli.parent.mkdir(parents=True)
        cli.write_text("#!/bin/sh\nprintf 'native %s\\n' \"$*\"\n", encoding="utf-8")
        cli.chmod(0o755)
        result = subprocess.run([str(launcher), "--version"],
                                env={"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                                     "DEPLOY_PLATFORM": "macos",
                                     "MAGPIE_APP": str(self.root / "missing-app")},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "native --version\n")

    def test_the_launcher_runs_the_app_binary(self):
        launcher = self.home / ".local/bin/magpie"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "dot_local/bin/executable_magpie", launcher)
        launcher.chmod(0o755)
        app = self.root / "magpie.app/Contents/MacOS/magpie"
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text("#!/bin/sh\necho \"magpie 0.1.0\"\n", encoding="utf-8")
        app.chmod(0o755)
        cli = self.root / "native-cli"
        cli.write_text("#!/bin/sh\nprintf 'native cli\\n'\n", encoding="utf-8")
        cli.chmod(0o755)
        result = subprocess.run([str(launcher), "--version"],
                                env={"HOME": str(self.home), "PATH": "/usr/bin:/bin", "MAGPIE_APP": str(app),
                                     "MAGPIE_CLI": str(cli)},
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
        template = (SOURCE / "deployment/client-settings/claude-settings.json.tmpl").read_text()
        self.assertIn('"ANTHROPIC_BASE_URL": "http://127.0.0.1:3425"', template)
        self.assertIn('"ANTHROPIC_AUTH_TOKEN": "magpie"', template)
        self.assertIn('"model": "opus"', template)
        self.assertNotIn('"ANTHROPIC_MODEL"', template)
        # The work tiers keep the conductor group; the cheap background
        # aliases and the auto-mode classifier route to Terra instead.
        for tier in ("ANTHROPIC_DEFAULT_FABLE_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                     "ANTHROPIC_DEFAULT_SONNET_MODEL"):
            self.assertIn(f'"{tier}": "group/conductor"', template)
        for tier in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                     "CLAUDE_CODE_AUTO_MODE_MODEL"):
            self.assertIn(f'"{tier}": "codex/gpt-6.1-terra"', template)
        # Subagents inherit their parent's model natively; the deployment must
        # not pin a separate (potentially stronger) subagent model.
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", template)
        self.assertNotIn("glm", template)
        # The wiring renders only for the magpie step's migration merge; an
        # ordinary client-settings merge never carries it. The macOS
        # application and the native CLI both own a gateway, so the gate
        # names every platform that has one.
        self.assertIn('{{- if and (has .platform (list "macos" "linux" "wsl")) '
                      '(eq (env "DOTFILES_SETTINGS_MAGPIE") "true") }}', template)
        self.assertNotIn("{{- if eq .platform \"macos\" }}", template)

    def test_the_client_settings_policy_enforces_the_magpie_wiring(self):
        policies = json.loads((SOURCE / "deployment/client-settings/policies.json").read_text())
        self.assertEqual(policies["claude-settings"], [
            ["env", "ANTHROPIC_AUTH_TOKEN"],
            ["env", "ANTHROPIC_BASE_URL"],
            ["env", "ANTHROPIC_DEFAULT_FABLE_MODEL"],
            ["env", "ANTHROPIC_DEFAULT_HAIKU_MODEL"],
            ["env", "ANTHROPIC_DEFAULT_OPUS_MODEL"],
            ["env", "ANTHROPIC_DEFAULT_SONNET_MODEL"],
            ["env", "ANTHROPIC_SMALL_FAST_MODEL"],
            ["env", "CLAUDE_CODE_AUTO_MODE_MODEL"],
            ["env", "DISABLE_AUTOUPDATER"],
            ["enabledPlugins", "serena@claude-plugins-official"],
        ])

    def test_no_template_carries_the_glm_data_anymore(self):
        config = (SOURCE / ".chezmoi.toml.tmpl").read_text()
        self.assertNotIn("glmBaseUrl", config)
        self.assertNotIn("glmToken", config)
        for path in (SOURCE / "deployment/client-settings").iterdir():
            if path.is_file():
                self.assertNotIn("glmBaseUrl", path.read_text(), path.name)
                self.assertNotIn("glmToken", path.read_text(), path.name)

    def test_an_apply_only_macos_apply_does_not_wire_the_clients(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi)
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "macos", "--apply-only"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dotfiles: magpie: skipped; --apply-only applies files without the gateway", result.stdout)
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        # The gateway migration belongs to the magpie step, which this mode
        # skips; the partial apply must not point Claude at a gateway.
        self.assertNotIn("ANTHROPIC_BASE_URL", settings["env"])
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", settings["env"])
        self.assertNotIn("model", settings)
        self.assertNotIn("glm", json.dumps(settings))

    def test_an_enforced_path_missing_from_the_template_leaves_the_device_value(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        settings_path = self.home / ".claude/settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({
            "model": "device-model",
            "env": {"ANTHROPIC_BASE_URL": "https://device.example", "ANTHROPIC_AUTH_TOKEN": "device-token"},
        }), encoding="utf-8")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi)
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "linux", "--apply-only"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        settings = json.loads(settings_path.read_text())
        self.assertEqual(settings["env"]["ANTHROPIC_BASE_URL"], "https://device.example")
        self.assertEqual(settings["env"]["ANTHROPIC_AUTH_TOKEN"], "device-token")
        self.assertEqual(settings["model"], "device-model")

    def test_a_linux_apply_keeps_both_clients_off_the_gateway(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi)
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "linux", "--apply-only"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        claude = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertNotIn("ANTHROPIC_BASE_URL", claude["env"])
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", claude["env"])
        self.assertNotIn("model", claude)
        pi = json.loads((self.home / ".pi/agent/settings.json").read_text())
        self.assertNotIn("defaultProvider", pi)
        self.assertNotIn("defaultModel", pi)


class ClaudeSubagentInheritanceTests(unittest.TestCase):
    """The managed subagent model retires only when the baseline owns it.

    These exercise the public `deploy_client_settings` seam against the
    working tree, the same entry point `bootstrap.sh` and the gateway step
    call. The ordinary merge (no gateway wiring) runs first and replaces the
    baseline; the gateway merge (with wiring) runs second, so a migration has
    to happen while the prior baseline is still available.
    """

    VALUE = "group/conductor"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-subagent-model-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.state = self.home / ".local/state"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "UV_",
                                           "NPM_", "ATUIN_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                    "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}
        self.settings = self.home / ".claude/settings.json"
        self.baseline = self.state / "dotfiles/client-settings/claude-settings.json"

    def write_chezmoi_config(self):
        config = self.home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[data]\n    platform = "macos"\n    role = "workstation"\n'
                          '    arch = "aarch64"\n    kimiApiKey = "REPLACE_ME"\n', encoding="utf-8")
        (self.home / ".cache/tmp").mkdir(parents=True, exist_ok=True)

    def write_settings(self, value, *, with_key=True):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        env = {}
        if with_key:
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = value
        self.settings.write_text(json.dumps({"model": "opus", "env": env}, indent=2) + "\n", encoding="utf-8")

    def write_baseline(self, value, *, with_key=True):
        self.baseline.parent.mkdir(parents=True, exist_ok=True)
        env = {}
        if with_key:
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = value
        self.baseline.write_text(json.dumps({"env": env}), encoding="utf-8")

    def merge(self, *, gateway=False):
        """Run `deploy_client_settings` for the Claude policy in a simulated home."""
        if not self.chezmoi:
            self.skipTest("client settings merge requires chezmoi")
        self.write_chezmoi_config()
        script = self.root / ("gateway-merge.sh" if gateway else "ordinary-merge.sh")
        script.write_text("\n".join([
            "export HOME=" + repr(str(self.home)),
            "export DEPLOY_SOURCE=" + repr(str(SOURCE)),
            "export DEPLOY_HOME=$HOME",
            "export DEPLOY_CHEZMOI=" + repr(str(self.chezmoi)),
            "export XDG_CONFIG_HOME=" + repr(str(self.home / ".config")),
            "export XDG_STATE_HOME=" + repr(str(self.state)),
            "export TMPDIR=" + repr(str(self.home / ".cache/tmp")),
            "fail() { printf 'dotfiles: %s\\n' \"$*\" >&2; exit 1; }",
            'source "$DEPLOY_SOURCE/deployment/payload.sh"',
            'source "$DEPLOY_SOURCE/deployment/client-settings.sh"',
            "deploy_client_settings 0 %s claude-settings" % (1 if gateway else 0),
        ]) + "\n", encoding="utf-8")
        environ = dict(self.env, HOME=str(self.home), PATH="/usr/bin:/bin",
                       XDG_CONFIG_HOME=str(self.home / ".config"),
                       XDG_STATE_HOME=str(self.state))
        return subprocess.run(["/bin/bash", str(script)], env=environ,
                              capture_output=True, text=True, timeout=120)

    def live(self):
        return json.loads(self.settings.read_text())["env"]

    def assert_merged(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fresh_install_has_no_subagent_model(self):
        self.assert_merged(self.merge())
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", self.live())
        self.assert_merged(self.merge(gateway=True))
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", self.live())
        self.assertEqual(self.live()["ANTHROPIC_BASE_URL"], "http://127.0.0.1:3425")

    def test_matching_prior_managed_value_is_migrated_then_stays_gone(self):
        self.write_settings(self.VALUE)
        self.write_baseline(self.VALUE)
        self.assert_merged(self.merge())
        # The ordinary merge removed the key and replaced the baseline, so the
        # gateway merge that follows cannot undo the migration.
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", self.live())
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", json.loads(self.baseline.read_text())["env"])
        self.assert_merged(self.merge(gateway=True))
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", self.live())
        self.assertEqual(self.live()["ANTHROPIC_BASE_URL"], "http://127.0.0.1:3425")

    def test_custom_device_value_survives_both_merges(self):
        self.write_settings("device/custom-model")
        self.write_baseline(self.VALUE)
        self.assert_merged(self.merge())
        self.assertEqual(self.live()["CLAUDE_CODE_SUBAGENT_MODEL"], "device/custom-model")
        self.assert_merged(self.merge(gateway=True))
        self.assertEqual(self.live()["CLAUDE_CODE_SUBAGENT_MODEL"], "device/custom-model")

    def test_no_baseline_preserves_an_unowned_value(self):
        self.write_settings(self.VALUE)
        self.assertFalse(self.baseline.exists())
        self.assert_merged(self.merge())
        self.assertEqual(self.live()["CLAUDE_CODE_SUBAGENT_MODEL"], self.VALUE)

    def test_conflicting_baseline_preserves_an_unowned_value(self):
        self.write_settings(self.VALUE)
        self.write_baseline("device/other-model")
        self.assert_merged(self.merge())
        self.assertEqual(self.live()["CLAUDE_CODE_SUBAGENT_MODEL"], self.VALUE)

    def test_gateway_merge_after_baseline_was_replaced_preserves_the_value(self):
        # The gateway merge sees a baseline the ordinary merge already rewrote.
        # Without the prior managed value there is no ownership proof, so the
        # value must be left alone even though it equals the old default.
        self.write_settings(self.VALUE)
        self.write_baseline(self.VALUE, with_key=False)
        self.assert_merged(self.merge(gateway=True))
        self.assertEqual(self.live()["CLAUDE_CODE_SUBAGENT_MODEL"], self.VALUE)

    def test_repeated_runs_are_idempotent(self):
        self.write_settings(self.VALUE)
        self.write_baseline(self.VALUE)
        self.assert_merged(self.merge())
        ordinary = self.settings.read_bytes()
        self.assert_merged(self.merge())
        self.assertEqual(self.settings.read_bytes(), ordinary)
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", self.live())
        self.assert_merged(self.merge(gateway=True))
        gateway = self.settings.read_bytes()
        self.assert_merged(self.merge(gateway=True))
        self.assertEqual(self.settings.read_bytes(), gateway)
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", self.live())


class MagpiePiSettingsTests(unittest.TestCase):
    """Pi selects the Magpie provider and the workhorse group."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-pi-")
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

    def test_the_pi_template_selects_the_magpie_provider(self):
        template = (SOURCE / "deployment/client-settings/pi-settings.json.tmpl").read_text()
        self.assertIn('"defaultProvider": "magpie"', template)
        self.assertIn('"defaultModel": "group/workhorse"', template)
        self.assertIn("modelThinkingLevels", template)
        self.assertNotIn("enabledModels", template)
        self.assertNotIn("minimax-cn", template)

    def test_the_models_file_is_left_to_magpie(self):
        ignore = (SOURCE / ".chezmoiignore").read_text()
        self.assertIn(".pi/agent/models.json", ignore)
        self.assertFalse((SOURCE / "dot_pi").exists())

    def test_an_apply_only_macos_apply_leaves_pi_off_the_gateway(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi)
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                                 "--home", str(self.home), "--platform", "macos", "--apply-only"],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        settings = json.loads((self.home / ".pi/agent/settings.json").read_text())
        self.assertNotIn("defaultProvider", settings)
        self.assertNotIn("defaultModel", settings)
        self.assertNotIn("modelThinkingLevels", settings)
        self.assertNotIn("enabledModels", settings)
        self.assertFalse((self.home / ".pi/agent/models.json").exists())

    def test_the_pi_template_gates_the_wiring_on_the_migration_flag(self):
        template = (SOURCE / "deployment/client-settings/pi-settings.json.tmpl").read_text()
        self.assertIn('{{- if and (has .platform (list "macos" "linux" "wsl")) '
                      '(eq (env "DOTFILES_SETTINGS_MAGPIE") "true") }}', template)
        self.assertNotIn("{{- if eq .platform \"macos\" }}", template)
