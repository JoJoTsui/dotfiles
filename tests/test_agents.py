"""Agent selection and observable installation through the public bootstrap."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from pins import agent_pins, common_pin

SOURCE = Path(__file__).resolve().parents[1]


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agents-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "BUN_", "PIXI_", "UV_", "NPM_", "ATUIN_", "CARGO_", "RUSTUP_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL", "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}
        self.env.update(HOME=str(self.root / "original"), PATH="/usr/bin:/bin")

    def deploy(self, *arguments, env=None):
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--home", str(self.home), "--platform", os.environ.get("DOTFILES_TEST_PLATFORM", "linux"),
                               "--role", os.environ.get("DOTFILES_TEST_ROLE", "workstation"), *arguments],
                              cwd=SOURCE, env=env or self.env, capture_output=True,
                              text=True, timeout=30)

    def test_default_plan_names_bun_owned_agents_and_independent_codegraph(self):
        result = self.deploy("--plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["agents"], ["kimi", "pi", "opencode", "claude", "codex"])
        selected = {item["name"]: item for item in plan["agentPackages"]}
        self.assertEqual(selected["codex"]["package"], "@openai/codex")
        self.assertEqual(selected["codex"]["version"], agent_pins()["codex"]["version"])
        self.assertEqual(selected["kimi"]["package"], "@moonshot-ai/kimi-code")
        self.assertEqual(selected["opencode"]["package"], "@opencode/cli")
        self.assertEqual(selected["opencode"]["version"], agent_pins()["opencode"]["version"])
        self.assertEqual(selected["codegraph"]["version"], agent_pins()["codegraph"]["version"])
        self.assertEqual(len(selected), 6)
        self.assertFalse(self.home.exists())

    def test_none_and_named_agents_keep_codegraph_and_reject_unknown_names(self):
        for selector, expected in (("none", []), ("codex,kimi-code,codex", ["kimi", "codex"]),
                                   ("claude-code,pi", ["pi", "claude"]), ("all", ["kimi", "pi", "opencode", "claude", "codex"])):
            with self.subTest(selector=selector):
                result = self.deploy("--plan", "--agents", selector)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertEqual(plan["agents"], expected)
                self.assertEqual({item["name"] for item in plan["agentPackages"]}, set(expected) | {"codegraph"})
                self.assertIn("codegraph", plan["tools"])
        for selector in ("unknown", "all,codex", "none,pi", "codex,", ",pi", "pi,,codex", ""):
            with self.subTest(invalid=selector):
                result = self.deploy("--agents", selector)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("agent", result.stderr)
                self.assertFalse(self.home.exists())
        result = self.deploy("--plan", "--agents", "none", env=dict(self.env, DOTFILES_AGENTS="all"))
        self.assertEqual(json.loads(result.stdout)["agents"], [])

    def test_required_bun_failure_has_a_package_step_and_preserves_global_registry(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi")
        tools = self.root / "tools"
        tools.mkdir()
        bun = tools / "bun"
        bun.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo ' + common_pin("bun") + '; else exit 23; fi\n')
        bun.chmod(0o755)
        node = tools / "node"
        node.write_text('#!/bin/sh\necho v' + common_pin("nodejs") + '\n')
        node.chmod(0o755)
        registry = self.home / ".bun/install/global/package.json"
        registry.parent.mkdir(parents=True)
        original = '{"dependencies":{"my-agent":"1.0.0"}}\n'
        registry.write_text(original)
        result = self.deploy("--agents-only", "--agents", "codex", env=dict(self.env,
            DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_BUN_BIN=str(bun), DOTFILES_NODE_BIN=str(node)))
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("step install-agents.codex.install failed (exit 23)", result.stderr)
        self.assertNotIn("dotfiles: applied", result.stdout)
        self.assertEqual(registry.read_text(), original)

    def test_selected_opencode_accepts_rendered_config_with_managed_updates(self):
        opencode = os.environ.get("DOTFILES_TEST_OPENCODE")
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI")
        if not opencode or not chezmoi:
            self.skipTest("requires the actual pinned OpenCode and chezmoi binaries")
        result = self.deploy("--apply-only", env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        diagnostic_env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                          "XDG_CONFIG_HOME": str(self.home / ".config"),
                          "XDG_DATA_HOME": str(self.home / ".local/share"),
                          "XDG_STATE_HOME": str(self.home / ".local/state"),
                          "XDG_CACHE_HOME": str(self.home / ".cache")}
        diagnostic = subprocess.run([opencode, "debug", "config"], cwd=self.home,
                                    env=diagnostic_env, capture_output=True, text=True, timeout=60)
        self.assertEqual(diagnostic.returncode, 0, diagnostic.stdout + diagnostic.stderr)
        sources = json.loads(diagnostic.stdout)
        configs = [item["info"] for item in sources if item["type"] == "document"]
        self.assertTrue(any(config.get("update") == "disable" for config in configs), diagnostic.stdout)
        self.assertTrue(any(config.get("providers", {}).get("headroom", {}).get("settings", {}).get("baseURL") == "http://127.0.0.1:8787/v1" for config in configs))

    def test_selected_kimi_validates_configs_and_leaves_upgrades_to_repo(self):
        kimi = os.environ.get("DOTFILES_TEST_KIMI")
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI")
        if not kimi or not chezmoi:
            self.skipTest("requires the actual pinned Kimi and chezmoi binaries")
        result = self.deploy("--apply-only", env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "KIMI_CODE_HOME": str(self.home / ".kimi-code")}
        for subcommand, path in (("config", ".kimi-code/config.toml"), ("tui", ".kimi-code/tui.toml")):
            diagnostic = subprocess.run([kimi, "doctor", subcommand, str(self.home / path)],
                                        cwd=self.home, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(diagnostic.returncode, 0, diagnostic.stdout + diagnostic.stderr)
        self.assertIn("auto_install = false", (self.home / ".kimi-code/tui.toml").read_text())


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_AGENT_INSTALL") == "1",
                     "requires explicit isolated network agent installation")
class AgentInstallTests(unittest.TestCase):
    def test_linux_default_suite_runs_and_opt_out_preserves_existing_installations(self):
        target = os.environ.get("DOTFILES_TEST_AGENT_HOME")
        if target:
            home = Path(target).resolve()
            self.assertTrue(str(home).startswith("/tmp/"))
        else:
            temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agent-install-")
            self.addCleanup(temporary.cleanup)
            home = Path(temporary.name) / "home"
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("DOTFILES_", "XDG_", "BUN_", "PIXI_", "UV_", "NPM_", "ATUIN_", "CARGO_", "RUSTUP_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
               and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL", "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}
        env.update(HOME=str(home), PATH="/usr/bin:/bin",
                   DOTFILES_CHEZMOI_BIN=os.environ["DOTFILES_TEST_CHEZMOI"],
                   DOTFILES_BUN_BIN=os.environ["DOTFILES_TEST_BUN"],
                   DOTFILES_NODE_BIN=os.environ["DOTFILES_TEST_NODE"])
        registry = home / ".bun/install/global/package.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        original_registry = '{"dependencies":{"device-extra":"1.0.0"},"trustedDependencies":[]}\n'
        registry.write_text(original_registry)
        extra = home / ".bun/bin/device-extra"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text('#!/bin/sh\necho device-extra-1\n')
        extra.chmod(0o755)
        command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(home),
                   "--platform", "linux", "--agents-only"]
        diagnostics = dict(env, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                           XDG_DATA_HOME=str(home / ".local/share"), XDG_STATE_HOME=str(home / ".local/state"),
                           XDG_CACHE_HOME=str(home / ".cache"), BUN_INSTALL=str(home / ".bun"),
                           CODEX_HOME=str(home / ".codex"), CLAUDE_CONFIG_DIR=str(home / ".claude"))
        expected = {name: item["version"] for name, item in agent_pins().items()}
        previous = None
        for attempt, selector in enumerate((None, "none", "codex", "all"), 1):
            selected_command = command if selector is None else [*command, "--agents", selector]
            result = subprocess.run(selected_command, cwd=SOURCE, env=env,
                                    capture_output=True, text=True, timeout=1200)
            (home / f"agents-{attempt}.log").write_text(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr[-7000:])
            self.assertIn("applied agent files and selected packages", result.stdout)
            for tool, version in expected.items():
                with self.subTest(attempt=attempt, command=tool):
                    launcher = home / f".bun/bin/{tool}"
                    self.assertTrue(launcher.is_file())
                    self.assertFalse(launcher.is_symlink())
                    self.assertEqual((home / f".local/bin/{tool}").read_bytes(), launcher.read_bytes())
                    diagnostic = subprocess.run([str(launcher), "--version"], cwd=home,
                                                env=diagnostics, capture_output=True, text=True, timeout=60)
                    self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
                    self.assertIn(version, diagnostic.stdout + diagnostic.stderr)
            self.assertEqual(registry.read_text(), original_registry)
            self.assertEqual(subprocess.check_output([str(extra)], env=diagnostics, text=True).strip(), "device-extra-1")
            current = {tool: (home / f".bun/bin/{tool}").read_bytes() for tool in expected}
            if previous:
                self.assertEqual(current, previous)
            previous = current
            self.assertFalse((SOURCE / ".codegraph").exists())
            self.assertFalse((home / ".codegraph").exists())
            self.assertFalse((home / ".codex/auth.json").exists())


if __name__ == "__main__":
    unittest.main()
