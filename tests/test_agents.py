"""Agent selection and observable installation through the public bootstrap."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from pins import agent_pins, common_pin, native_agent_pins

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
        self.env.update(HOME=str(self.root / "original"), PATH="/usr/bin:/bin",
                        DOTFILES_SKILLS_DIR=str(SOURCE / "tests/fixtures/skill-library"))

    def deploy(self, *arguments, env=None):
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--home", str(self.home), "--platform", os.environ.get("DOTFILES_TEST_PLATFORM", "linux"),
                               "--role", os.environ.get("DOTFILES_TEST_ROLE", "workstation"), *arguments],
                              cwd=SOURCE, env=env or self.env, capture_output=True,
                              text=True, timeout=30)

    def test_targeted_update_repairs_pi_and_preserves_unrelated_state(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual agent update requires Chezmoi")
        tools = self.root / "tools"
        tools.mkdir()
        installed = self.root / "projects.log"
        pins = agent_pins()
        bun = tools / "bun"
        bun.write_text(
            f"#!{sys.executable}\n"
            "import sys\nfrom pathlib import Path\n"
            "if sys.argv[1:] == ['--version']:\n"
            f"    print({common_pin('bun')!r}); raise SystemExit\n"
            "if '--cwd' in sys.argv:\n"
            "    project = Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            f"    with Path({str(installed)!r}).open('a') as log: log.write(project.name + (' force' if '--force' in sys.argv else '') + '\\n')\n"
            f"    for command in { {name: row['commands'].split(',') for name, row in pins.items()}!r}[project.name]:\n"
            f"        version = { {name: row['version'] for name, row in pins.items()}!r}[project.name]\n"
            "        launcher = project / 'node_modules/.bin' / command\n"
            "        if launcher.exists() and '--force' not in sys.argv: continue\n"
            "        launcher.parent.mkdir(parents=True, exist_ok=True)\n"
            "        launcher.write_text('#!/bin/sh\\necho ' + version + '\\n')\n"
            "        launcher.chmod(0o755)\n"
        )
        bun.chmod(0o755)
        node = tools / "node"
        node.write_text(f"#!/bin/sh\necho v{common_pin('nodejs')}\n")
        node.chmod(0o755)
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_BUN_BIN=str(bun),
                           DOTFILES_NODE_BIN=str(node))
        seeded = self.deploy("--agents-only", "--agents", "pi", env=environment)
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        installed.write_text("")

        unrelated = {
            ".codex/config.toml": b"invalid TOML left for a full apply",
            ".config/git/ignore": b"device ignore drift\n",
            ".agents/skills/herdr/SKILL.md": b"existing generated skill\n",
            ".local/state/dotfiles/generated-skills.tsv": b"herdr|.agents/skills|fixture\n",
            ".pi/agent/mcp.json": b'{"codegraph":"device drift"}\n',
            ".local/bin/codegraph": b"preserve independent CodeGraph\n",
        }
        for relative, content in unrelated.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        timestamps = {relative: (self.home / relative).stat().st_mtime_ns for relative in unrelated}
        state = self.home / ".local/state/dotfiles/herdr.tsv"
        state.write_text("# agent|kind|state\ncodex|codex|current\n")
        launcher = self.home / ".local/bin/pi"
        launcher.write_text("#!/bin/sh\n# Managed by dotfiles; older launcher.\nexit 99\n")
        (self.home / ".bun/bin/pi").unlink()
        # A broken selected package bin must be checked and repaired even
        # when the catalog and lock still match.
        package_entry = self.home / ".bun/managed/pi/node_modules/.bin/pi"
        package_entry.write_text("#!/bin/sh\nexit 99\n")
        settings = self.home / ".pi/agent/settings.json"
        settings.unlink()
        adjusted = tools / "replacement/node"
        adjusted.parent.mkdir()
        shutil.copy2(node, adjusted)
        updated = self.deploy("--agent-update", "--agents", "pi", env=dict(environment, DOTFILES_NODE_BIN=str(adjusted)))
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.assertEqual(installed.read_text().splitlines(), ["pi", "pi force"])
        self.assertIn("reconciled pi", updated.stdout)
        self.assertIn("skipped shared source", updated.stdout)
        self.assertIn("repairing the installed pi package", updated.stdout)
        self.assertIn(str(adjusted.parent), launcher.read_text())
        self.assertEqual(subprocess.check_output([str(launcher), "--version"], text=True).strip(),
                         pins["pi"]["version"])
        self.assertTrue(settings.exists())
        self.assertIn("codex|codex|current", state.read_text())
        for relative, content in unrelated.items():
            path = self.home / relative
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path.stat().st_mtime_ns, timestamps[relative])

    def test_default_plan_names_bun_owned_agents_and_independent_codegraph(self):
        result = self.deploy("--plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["agents"], ["kimi", "pi", "opencode", "claude", "codex", "minimax", "qoder",
                                         "dsh", "dsh-tui"])
        selected = {item["name"]: item for item in plan["agentPackages"]}
        self.assertEqual(selected["codex"]["package"], "@openai/codex")
        self.assertEqual(selected["codex"]["version"], agent_pins()["codex"]["version"])
        self.assertEqual(selected["kimi"]["package"], "@moonshot-ai/kimi-code")
        self.assertEqual(selected["opencode"]["package"], "@opencode/cli")
        self.assertEqual(selected["opencode"]["version"], agent_pins()["opencode"]["version"])
        self.assertEqual(selected["minimax"]["package"], "@minimax-ai/code")
        self.assertEqual(selected["minimax"]["version"], agent_pins()["minimax"]["version"])
        self.assertEqual(selected["qoder"]["manager"], "native")
        self.assertEqual(selected["qoder"]["version"], native_agent_pins()["qoder"]["version"])
        self.assertEqual(selected["codegraph"]["version"], agent_pins()["codegraph"]["version"])
        self.assertEqual(selected["dsh"]["package"], "@deepseek-ai/dsh")
        self.assertEqual(selected["dsh"]["commands"], ["dsh"])
        self.assertEqual(selected["dsh-tui"]["package"], "@deepseek-harness-tui/dsh-tui")
        self.assertEqual(selected["dsh-tui"]["commands"], ["dsh-tui", "dst"])
        self.assertEqual(len(selected), 10)
        self.assertFalse(self.home.exists())

    def test_the_dsh_agents_install_their_launchers(self):
        """The frozen Bun projects expose dsh, dsh-tui, and dst."""
        pins = agent_pins()
        tools = self.root / "tools"
        tools.mkdir()
        bun = tools / "bun"
        bun.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            f"pins = {pins!r}\n"
            "if sys.argv[1:2] == ['--version']:\n"
            f"    print({common_pin('bun')!r}); raise SystemExit\n"
            "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            "pin = pins[project.name]\n"
            "for command in pin['commands'].split(','):\n"
            "    target = project / 'node_modules/.bin' / command\n"
            "    target.parent.mkdir(parents=True, exist_ok=True)\n"
            "    target.write_text('#!/bin/sh\\necho ' + pin['version'] + '\\n')\n"
            "    target.chmod(0o755)\n",
            encoding="utf-8")
        bun.chmod(0o755)
        node = tools / "node"
        node.write_text("#!/bin/sh\necho v" + common_pin("nodejs") + "\n", encoding="utf-8")
        node.chmod(0o755)
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("the source application requires chezmoi")
        environment = dict(self.env, DOTFILES_BUN_BIN=str(bun), DOTFILES_NODE_BIN=str(node),
                           DOTFILES_CHEZMOI_BIN=chezmoi)
        result = self.deploy("--agents-only", "--agents", "dsh,dsh-tui", env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for command in ("dsh", "dsh-tui", "dst"):
            launcher = self.home / ".local/bin" / command
            self.assertTrue(launcher.is_file(), command)
            self.assertTrue(launcher.stat().st_mode & 0o111, command)
            owner = "dsh-tui" if command in ("dsh-tui", "dst") else "dsh"
            self.assertIn(f"/.bun/managed/{owner}/node_modules/.bin/{command}",
                          launcher.read_text(encoding="utf-8"))

    # A fake Bun/Node pair whose installed shims report the PATH and the first
    # dsh they discover at runtime. This exercises observable discovery through
    # the generated launchers instead of matching their literal text. The probe
    # body lives in its own file so the fake Bun only has to copy a path into
    # each shim, keeping shell quoting simple.
    def _deploy_probe_launchers(self, agents):
        self.home = self.root / "device with spaces"
        pins = agent_pins()
        tools = self.root / "tools with spaces"
        tools.mkdir()
        probe = tools / "probe.sh"
        probe.write_text(
            "#!/bin/sh\n"
            "printf 'PATH=%s\\n' \"$PATH\"\n"
            "printf 'FIRST_DSH=%s\\n' \"$(command -v dsh || true)\"\n"
            "printf 'DSH_BIN=%s\\n' \"${DSH_TUI_CLI_DSH_BIN-<unset>}\"\n",
            encoding="utf-8")
        probe.chmod(0o755)
        bun = tools / "bun"
        bun_source = (
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "pins = __PINS__\n"
            "if sys.argv[1:2] == ['--version']:\n"
            "    print(__BUNPIN__); raise SystemExit\n"
            "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            "pin = pins[project.name]\n"
            "for command in pin['commands'].split(','):\n"
            "    target = project / 'node_modules/.bin' / command\n"
            "    target.parent.mkdir(parents=True, exist_ok=True)\n"
            "    target.write_text('#!/bin/sh\\necho ' + pin['version'] + '\\n\"__TOOLS__/probe.sh\"\\n')\n"
            "    target.chmod(0o755)\n")
        bun_source = (bun_source.replace("__PINS__", repr(pins))
                                .replace("__BUNPIN__", repr(common_pin("bun")))
                                .replace("__TOOLS__", str(tools)))
        bun.write_text(bun_source, encoding="utf-8")
        bun.chmod(0o755)
        node = tools / "node"
        node.write_text("#!/bin/sh\necho v" + common_pin("nodejs") + "\n", encoding="utf-8")
        node.chmod(0o755)
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("the source application requires chezmoi")
        environment = dict(self.env, DOTFILES_BUN_BIN=str(bun), DOTFILES_NODE_BIN=str(node),
                           DOTFILES_CHEZMOI_BIN=chezmoi)
        result = self.deploy("--agents-only", "--agents", agents, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return tools

    def _run_probe(self, command, path="/usr/bin:/bin", extra=None):
        run_env = {"HOME": str(self.home), "PATH": path}
        if extra:
            run_env.update(extra)
        result = subprocess.run([str(self.home / ".local/bin" / command)], cwd=self.home,
                                env=run_env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value
        return fields

    def test_unix_dsh_tui_launchers_prepend_managed_dsh_bin(self):
        """dsh-tui/dst resolve the managed DSH JS entry, not the shell launcher."""
        tools = self._deploy_probe_launchers("dsh,dsh-tui")
        dsh_bin = self.home / ".bun/managed/dsh/node_modules/.bin"
        for command in ("dsh-tui", "dst"):
            with self.subTest(command=command):
                fields = self._run_probe(command)
                effective = fields["PATH"]
                self.assertTrue(effective.startswith(str(dsh_bin) + os.pathsep), effective)
                self.assertIn(str(tools), effective)  # Node/Bun tools remain resolvable
                self.assertEqual(fields["FIRST_DSH"], str(dsh_bin / "dsh"))

    def test_unix_dsh_tui_launchers_respect_explicit_dsh_bin(self):
        """An explicit DSH_TUI_CLI_DSH_BIN is never rewritten by the launcher."""
        self._deploy_probe_launchers("dsh,dsh-tui")
        explicit = "/opt/dsh/lib/bin.js"
        for command in ("dsh-tui", "dst"):
            with self.subTest(command=command):
                fields = self._run_probe(command, extra={"DSH_TUI_CLI_DSH_BIN": explicit})
                self.assertEqual(fields["DSH_BIN"], explicit)

    def test_unix_dsh_tui_launchers_keep_other_path_discovery_without_dsh(self):
        """With DSH omitted, a device-provided dsh elsewhere on PATH still wins."""
        self._deploy_probe_launchers("dsh-tui")
        device_dir = self.root / "device-bin"
        device_dir.mkdir()
        device_dsh = device_dir / "dsh"
        device_dsh.write_text("#!/bin/sh\necho device-dsh\n", encoding="utf-8")
        device_dsh.chmod(0o755)
        for command in ("dsh-tui", "dst"):
            with self.subTest(command=command):
                fields = self._run_probe(command, path=f"{device_dir}:/usr/bin:/bin")
                self.assertEqual(fields["FIRST_DSH"], str(device_dsh))

    def test_unix_dsh_launcher_does_not_prepend_managed_dsh_bin(self):
        """Only dsh-tui/dst change; the dsh launcher keeps the shared PATH."""
        tools = self._deploy_probe_launchers("dsh,dsh-tui")
        dsh_bin = self.home / ".bun/managed/dsh/node_modules/.bin"
        fields = self._run_probe("dsh")
        effective = fields["PATH"]
        self.assertFalse(effective.startswith(str(dsh_bin) + os.pathsep), effective)
        self.assertTrue(effective.startswith(str(tools) + os.pathsep), effective)

    def test_none_and_named_agents_keep_codegraph_and_reject_unknown_names(self):
        for selector, expected in (("none", []), ("codex,kimi-code,codex", ["kimi", "codex"]),
                                   ("claude-code,pi", ["pi", "claude"]),
                                   ("minimax-code,qoder", ["minimax", "qoder"]),
                                   ("all", ["kimi", "pi", "opencode", "claude", "codex", "minimax", "qoder",
                                            "dsh", "dsh-tui"])):
            with self.subTest(selector=selector):
                result = self.deploy("--plan", "--agents", selector)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertEqual(plan["agents"], expected)
                self.assertEqual({item["name"] for item in plan["agentPackages"]}, set(expected) | {"codegraph"})
                self.assertIn("codegraph", plan["tools"])
                if "qoder" in expected:
                    self.assertIn("qodercli", plan["tools"])
                else:
                    self.assertNotIn("qodercli", plan["tools"])
        for selector in ("unknown", "all,codex", "none,pi", "codex,", ",pi", "pi,,codex", ""):
            with self.subTest(invalid=selector):
                result = self.deploy("--agents", selector)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("agent", result.stderr)
                self.assertFalse(self.home.exists())
        result = self.deploy("--plan", "--agents", "none", env=dict(self.env, DOTFILES_AGENTS="all"))
        self.assertEqual(json.loads(result.stdout)["agents"], [])

    def test_macos_accepts_newer_runtimes_before_the_frozen_install(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi")
        tools = self.root / "tools"
        tools.mkdir()
        bun = tools / "bun"
        bun.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo 99.0.0; else exit 23; fi\n')
        bun.chmod(0o755)
        node = tools / "node"
        node.write_text('#!/bin/sh\necho v99.0.0\n')
        node.chmod(0o755)
        result = self.deploy("--platform", "macos", "--agents-only", "--agents", "none", env=dict(
            self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_BUN_BIN=str(bun), DOTFILES_NODE_BIN=str(node)))
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("step install-agents.codegraph.install failed", result.stderr)

    def test_plugin_settings_are_stable_on_the_first_and_second_deployment(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi")
        tools = self.root / "tools"
        tools.mkdir()
        bun = tools / "bun"
        helper = tools / "bun.py"
        helper.write_text(
            "import os, pathlib, sys\n"
            f"pins = {agent_pins()!r}\n"
            "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            "pin = pins[project.name]\n"
            "for command in pin['commands'].split(','):\n"
            "    launcher = project / 'node_modules/.bin' / command\n"
            "    launcher.parent.mkdir(parents=True, exist_ok=True)\n"
            "    launcher.write_text('#!/bin/sh\\necho ' + pin['version'] + '\\n')\n"
            "    launcher.chmod(0o755)\n")
        bun.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo ' + common_pin("bun") +
                       '; else exec "' + sys.executable + '" "' + str(helper) + '" "$@"; fi\n')
        bun.chmod(0o755)
        node = tools / "node"
        node.write_text('#!/bin/sh\necho v' + common_pin("nodejs") + '\n')
        node.chmod(0o755)
        wt = self.home / ".pixi/bin/wt"
        wt.parent.mkdir(parents=True)
        wt.write_text('#!' + sys.executable + '\n'
                      'import json, os, pathlib\n'
                      'path = pathlib.Path(os.environ["HOME"]) / ".claude/settings.json"\n'
                      'settings = json.loads(path.read_text())\n'
                      'if "worktrunk@worktrunk" not in settings.get("enabledPlugins", {}):\n'
                      '    settings.setdefault("enabledPlugins", {})["worktrunk@worktrunk"] = True\n'
                      '    path.write_text(json.dumps(settings, indent=2) + "\\n")\n')
        wt.chmod(0o755)
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi,
                           DOTFILES_BUN_BIN=str(bun), DOTFILES_NODE_BIN=str(node))
        settings = self.home / ".claude/settings.json"
        before = None
        for _ in range(2):
            result = self.deploy("--agents-only", "--agents", "claude", env=environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(settings.read_text())["enabledPlugins"]["worktrunk@worktrunk"])
            self.assertFalse(json.loads(settings.read_text())["enabledPlugins"]["serena@claude-plugins-official"])
            if before is not None:
                self.assertEqual(settings.read_bytes(), before)
            before = settings.read_bytes()

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

    def test_deployment_reports_a_leftover_bun_global_copy(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi")
        tools = self.root / "tools"
        tools.mkdir()
        bun = tools / "bun"
        helper = tools / "bun.py"
        helper.write_text(
            "import os, pathlib, sys\n"
            f"pins = {agent_pins()!r}\n"
            "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            "pin = pins[project.name]\n"
            "for command in pin['commands'].split(','):\n"
            "    launcher = project / 'node_modules/.bin' / command\n"
            "    launcher.parent.mkdir(parents=True, exist_ok=True)\n"
            "    launcher.write_text('#!/bin/sh\\necho ' + pin['version'] + '\\n')\n"
            "    launcher.chmod(0o755)\n")
        bun.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo ' + common_pin("bun") +
                       '; else exec "' + sys.executable + '" "' + str(helper) + '" "$@"; fi\n')
        bun.chmod(0o755)
        node = tools / "node"
        # The deployment reads a package version and its bins with Node.
        node.write_text('#!/bin/sh\nif [ "$1" = "-e" ]; then exec "' + sys.executable +
                        '" -c \'import json,sys; m=json.load(open(sys.argv[1])); b=m.get("bin") or {}; '
                        'names=[b] if isinstance(b,str) else list(b); '
                        'print(str(m.get("version",""))+chr(9)+" ".join(names))\' "$3"; fi\n'
                        'echo v' + common_pin("nodejs") + '\n')
        node.chmod(0o755)
        leftover = self.home / ".bun/install/global/node_modules/@earendil-works/pi-coding-agent/package.json"
        leftover.parent.mkdir(parents=True)
        leftover.write_text(json.dumps({"name": "@earendil-works/pi-coding-agent", "version": "9.9.9",
                                        "bin": {"pi": "dist/bundle/cli.js", "pi-extra": "dist/extra.js"}}))
        result = self.deploy("--agents-only", "--agents", "pi", env=dict(
            self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_BUN_BIN=str(bun), DOTFILES_NODE_BIN=str(node)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("@earendil-works/pi-coding-agent@9.9.9 is also installed in the Bun global registry",
                      result.stdout)
        self.assertIn("the managed launcher owns pi", result.stdout)
        self.assertIn("the global copy also provides pi-extra, which no managed launcher owns",
                      result.stdout)
        self.assertIn("bun remove -g @earendil-works/pi-coding-agent", result.stdout)
        # The device-owned package stays; the deployment only reports it.
        self.assertTrue(leftover.is_file())

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
        # 2.2.0 starts the managed service for `debug config`; standalone keeps
        # the diagnostic off a host service that may already hold the port.
        diagnostic = subprocess.run([opencode, "debug", "config", "--standalone"], cwd=self.home,
                                    env=diagnostic_env, capture_output=True, text=True, timeout=60)
        self.assertEqual(diagnostic.returncode, 0, diagnostic.stdout + diagnostic.stderr)
        sources = json.loads(diagnostic.stdout)
        configs = [item["info"] for item in sources if item["type"] == "document"]
        self.assertTrue(any(config.get("update") == "disable" for config in configs), diagnostic.stdout)
        self.assertFalse(any("headroom" in config.get("providers", {}) or "headroom" in config.get("mcp", {}).get("servers", {}) for config in configs),
                         "Headroom is removed; neither its provider nor its MCP server may render")
        self.assertTrue(any(config.get("skills") == [str(self.home / ".agents/skills")] for config in configs),
                        "OpenCode config does not register the target home skill library")

    def test_selected_kimi_validates_configs_and_leaves_upgrades_to_repo(self):
        kimi = os.environ.get("DOTFILES_TEST_KIMI")
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI")
        if not kimi or not chezmoi:
            self.skipTest("requires the actual pinned Kimi and chezmoi binaries")
        result = self.deploy("--apply-only", env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        node = os.environ.get("DOTFILES_TEST_NODE")
        path = "/usr/bin:/bin" + (os.pathsep + os.path.dirname(node) if node else "")
        env = {"HOME": str(self.home), "PATH": path, "KIMI_CODE_HOME": str(self.home / ".kimi-code")}
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
        expected = {name: (item["version"], item["commands"].split(",")[0])
                    for name, item in agent_pins().items()}
        previous = None
        for attempt, selector in enumerate((None, "none", "codex", "all"), 1):
            selected_command = command if selector is None else [*command, "--agents", selector]
            result = subprocess.run(selected_command, cwd=SOURCE, env=env,
                                    capture_output=True, text=True, timeout=1200)
            (home / f"agents-{attempt}.log").write_text(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr[-7000:])
            self.assertIn("applied agent files and selected packages", result.stdout)
            for tool, (version, command_name) in expected.items():
                with self.subTest(attempt=attempt, command=command_name):
                    launcher = home / f".bun/bin/{command_name}"
                    self.assertTrue(launcher.is_file())
                    self.assertFalse(launcher.is_symlink())
                    self.assertEqual((home / f".local/bin/{command_name}").read_bytes(), launcher.read_bytes())
                    diagnostic = subprocess.run([str(launcher), "--version"], cwd=home,
                                                env=diagnostics, capture_output=True, text=True, timeout=60)
                    self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
                    self.assertIn(version, diagnostic.stdout + diagnostic.stderr)
            qoder = native_agent_pins()["qoder"]
            if selector in (None, "all"):
                self.assertTrue((home / ".local/bin/qodercli").is_file())
                diagnostic = subprocess.run([str(home / ".local/bin/qodercli"), "--version"], cwd=home,
                                            env=diagnostics, capture_output=True, text=True, timeout=60)
                self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
                self.assertIn(qoder["version"], diagnostic.stdout + diagnostic.stderr)
            self.assertEqual(registry.read_text(), original_registry)
            self.assertEqual(subprocess.check_output([str(extra)], env=diagnostics, text=True).strip(), "device-extra-1")
            current = {tool: (home / f".bun/bin/{command_name}").read_bytes()
                       for tool, (_, command_name) in expected.items()}
            if previous:
                self.assertEqual(current, previous)
            previous = current
            self.assertFalse((SOURCE / ".codegraph").exists())
            self.assertFalse((home / ".codegraph").exists())
            self.assertFalse((home / ".codex/auth.json").exists())


if __name__ == "__main__":
    unittest.main()
