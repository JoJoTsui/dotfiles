"""Public PowerShell boundary; Linux results cover planning/rendering only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
POWERSHELL = os.environ.get("DOTFILES_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "set DOTFILES_TEST_POWERSHELL for the public Windows boundary")
class WindowsBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-windows-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device with spaces"
        self.original = self.root / "other-profile"
        self.original.mkdir()
        self.env = os.environ.copy()
        for name in tuple(self.env):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL", "NODE_OPTIONS", "CLAUDE_CONFIG_DIR",
            ):
                self.env.pop(name)
        # PowerShell itself initializes its module cache before script entry.
        # Confine that runtime to this test, apart from the protected profile.
        self.env.update(HOME=str(self.root / 'powershell-runtime'), USERPROFILE=str(self.original),
                        APPDATA=str(self.original / "roaming"), LOCALAPPDATA=str(self.original / "local"))

    def deploy(self, *arguments, env=None):
        return subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                               str(SOURCE / "bootstrap.ps1"), "-TargetHome", str(self.home), *arguments],
                              cwd=SOURCE, env=env or self.env, capture_output=True, text=True, timeout=90)

    def test_native_plan_selects_role_and_default_owners_without_writes(self):
        result = self.deploy("-Plan", "-Profile", "windows-remote-compute", "-Arch", "x86_64")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["profile"], "windows-remote-compute")
        self.assertEqual(plan["settings"]["primaryShell"], "nu")
        self.assertEqual(plan["settings"]["secondaryShells"], ["git-bash"])
        self.assertFalse(plan["settings"]["systemChanges"])
        self.assertFalse(plan["settings"]["loginShellChanges"])
        for tool in ("pixi", "bun", "atuin", "rtk", "nu", "uv", "zoxide", "tspin", "hx", "jq", "kimi", "pi", "opencode", "claude", "codex", "codegraph"):
            self.assertIn(tool, plan["tools"])
        packages = {item["environment"]: item for item in plan["packages"]}
        self.assertEqual(packages["rtk-cli"]["dependencies"], {"rtk-cli": "==0.51.0"})
        self.assertNotIn("zsh", packages)
        self.assertNotIn("bun", packages)
        self.assertEqual(plan["roots"]["appData"], str(self.home / "AppData/Roaming"))
        self.assertEqual(plan["roots"]["localAppData"], str(self.home / "AppData/Local"))
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.original.iterdir()), [])

    def test_apply_only_copies_native_discovery_and_preserves_device_content(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        source = self.root / 'working source'
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        with (source / 'dot_env_core.tmpl').open('a') as handle:
            handle.write('\n# uncommitted-windows-source\n')
        settings = self.home / '.claude/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{"deviceOnly":true,"permissions":{"allow":["Read(*)"]}}\n')
        instructions = self.home / '.codex/AGENTS.md'
        instructions.parent.mkdir()
        instructions.write_text('device instructions stay\n')
        custom_skill = self.home / '.agents/skills/device-only/SKILL.md'
        custom_skill.parent.mkdir(parents=True)
        custom_skill.write_text('custom skill\n')
        registry = self.home / '.pixi/manifests/pixi-global.toml'
        registry.parent.mkdir(parents=True)
        registry.write_text('version = 1\n[envs.device]\ndependencies = { device = "==1.0" }\n')
        auth = self.home / '.codex/auth.json'
        auth.write_text('{"synthetic":"device-auth"}\n')
        history = self.home / '.local/share/atuin/history.db'
        history.parent.mkdir(parents=True)
        history.write_bytes(b'synthetic-existing-history')
        old_nu_history = self.home / '.config/nushell/history.txt'
        old_nu_history.parent.mkdir(parents=True)
        old_nu_history.write_text('synthetic-existing-xdg-history\n')
        native_nu_history = self.home / 'AppData/Roaming/nushell/history.txt'
        native_nu_history.parent.mkdir(parents=True)
        native_nu_history.write_text('synthetic-existing-native-history\n')
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi,
                           GLM_API_TOKEN='synthetic-quote"\\\n$`', KIMI_API_KEY='synthetic-quote"\\\n$`')
        for role in ('remote-compute', 'workstation'):
            result = self.deploy('-ApplyOnly', '-Source', str(source), '-Role', role, env=environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('uncommitted-windows-source', (self.home / '.env_core').read_text())
            self.assertTrue(json.loads(settings.read_text())['deviceOnly'])
            self.assertEqual(json.loads(settings.read_text())['env']['ANTHROPIC_AUTH_TOKEN'], environment['GLM_API_TOKEN'])
            self.assertIn('device instructions stay', instructions.read_text())
            self.assertEqual(custom_skill.read_text(), 'custom skill\n')
            self.assertEqual(auth.read_text(), '{"synthetic":"device-auth"}\n')
            self.assertEqual(history.read_bytes(), b'synthetic-existing-history')
            self.assertEqual(native_nu_history.read_text(), 'synthetic-existing-native-history\n')
            self.assertIn('[envs.device]', registry.read_text())
            native = self.home / 'AppData/Roaming'
            for relative in ('nushell/env.nu', 'nushell/config.nu', 'nushell/zoxide.nu', 'nushell/proxy.nu', 'uv/uv.toml', 'pip/pip.ini'):
                self.assertTrue((native / relative).is_file(), relative)
                self.assertFalse((native / relative).is_symlink(), relative)
            self.assertEqual((native / 'nushell/env.nu').read_bytes(), (self.home / '.config/nushell/env.nu').read_bytes())
            for relative in ('bootstrap.ps1', 'deployment', 'tests', '.github'):
                self.assertFalse((self.home / relative).exists(), relative)
            mcp = json.loads((self.home / '.claude.json').read_text())['mcpServers']['codegraph']
            self.assertEqual(mcp['command'], str(self.home / '.pixi/bin/node.exe'))
            self.assertEqual(mcp['args'][1:], ['serve', '--mcp'])
            self.assertEqual(Path(mcp['args'][0]).parts[-3:], ('@colbymchenry', 'codegraph', 'npm-shim.js'))
            self.assertEqual(json.loads((self.home / '.config/dotfiles/profile.json').read_text())['role'], role)
            # Role changes stop managing remote-only files without deleting
            # device content that was deployed by an earlier role.
            self.assertTrue((self.home / '.vscode-server/data/Machine/settings.json').exists())

    def test_plan_reports_verified_windows_exceptions_and_bundle_targets(self):
        result = self.deploy('-Plan', '-Agents', 'codex,kimi-code', '-Bundles', 'desktop')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['agents'], ['kimi', 'codex'])
        exceptions = {item['name']: item for item in plan['exceptions']}
        self.assertEqual(exceptions['bun']['sha256'], '9d0e0f923e9626f3bc6044fc32e0d3ab29039aea753f5678ef8801cf26f75288')
        self.assertEqual(exceptions['atuin']['version'], '18.23.0')
        self.assertIn('git-bash', exceptions)
        for item in exceptions.values():
            self.assertTrue(item['url'].startswith('https://'))
            self.assertEqual(len(item['sha256']), 64)
        self.assertEqual(plan['bundles'], ['desktop'])
        self.assertIn('zed', plan['tools'])
        self.assertIn('firefox', plan['tools'])
        self.assertFalse(self.home.exists())

    def test_invalid_selections_and_nested_symlinks_fail_before_mutation(self):
        for args in (('-Plan', '-Arch', 'arm64'), ('-Plan', '-Bundles', 'bio'),
                     ('-Plan', '-Profile', 'windows-workstation', '-Role', 'remote-compute'),
                     ('-Plan', '-Agents', 'unknown'), ('-ApplyOnly', '-AgentsOnly')):
            with self.subTest(args=args):
                result = self.deploy(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.home.exists())
        self.home.mkdir()
        target = self.home / '.agents/skills/tdd'
        target.parent.mkdir(parents=True)
        try:
            target.symlink_to(self.original, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        result = self.deploy('-ApplyOnly')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink or reparse', result.stderr)
        self.assertEqual(list(self.original.iterdir()), [])

    def test_native_installer_directory_rejects_nested_reparse_paths_before_application(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source preservation requires Chezmoi')
        target = self.home / '.local/share/dotfiles/git-bash/bin'
        target.parent.mkdir(parents=True)
        try:
            target.symlink_to(self.original, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink or reparse', result.stderr)
        self.assertEqual(list(self.original.iterdir()), [])
        self.assertFalse((self.home / '.config').exists())

    def test_invalid_client_syntax_preserves_every_client_and_hides_values(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual client preservation requires Chezmoi')
        claude = self.home / '.claude/settings.json'
        claude.parent.mkdir(parents=True)
        claude.write_text('{"deviceOnly":true}\n')
        kimi = self.home / '.kimi-code/config.toml'
        kimi.parent.mkdir()
        kimi.write_text('password = "synthetic-private-parser-value\n')
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.kimi-code/config.toml', result.stderr)
        self.assertNotIn('synthetic-private-parser-value', result.stderr + result.stdout)
        self.assertEqual(claude.read_text(), '{"deviceOnly":true}\n')
        self.assertEqual(kimi.read_text(), 'password = "synthetic-private-parser-value\n')


@unittest.skipUnless(os.name == 'nt' and os.environ.get('DOTFILES_TEST_NATIVE_WINDOWS_INSTALL') == '1',
                     'actual Windows installation runs on the native runner')
class WindowsNativeInstallTests(unittest.TestCase):
    setUp = WindowsBoundaryTests.setUp
    def deploy(self, *arguments, env=None):
        return subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                               '-File', str(SOURCE / 'bootstrap.ps1'), '-TargetHome', str(self.home), *arguments],
                              cwd=SOURCE, env=env or self.env, capture_output=True, text=True, timeout=2400)

    def test_default_install_reapply_and_native_diagnostics(self):
        role = os.environ.get('DOTFILES_TEST_WINDOWS_ROLE', 'workstation')
        self.env['DOTFILES_ROLE'] = role
        result = self.deploy('-Role', role)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('sync pending activation', result.stdout)
        environment = self.env.copy()
        environment.update(HOME=str(self.home), USERPROFILE=str(self.home), APPDATA=str(self.home / 'AppData/Roaming'),
                           LOCALAPPDATA=str(self.home / 'AppData/Local'), XDG_CONFIG_HOME=str(self.home / '.config'),
                           XDG_DATA_HOME=str(self.home / '.local/share'), XDG_STATE_HOME=str(self.home / '.local/state'),
                           XDG_CACHE_HOME=str(self.home / '.cache'), PIXI_HOME=str(self.home / '.pixi'),
                           ATUIN_CONFIG_DIR=str(self.home / '.config/atuin'), ATUIN_DATA_DIR=str(self.home / '.local/share/atuin'),
                           KIMI_SHELL_PATH=str(self.home / '.local/share/dotfiles/git-bash/bin/bash.exe'),
                           CODEX_HOME=str(self.home / '.codex'), KIMI_CODE_HOME=str(self.home / '.kimi-code'),
                           PI_CODING_AGENT_DIR=str(self.home / '.pi/agent'),
                           OPENCODE_CONFIG=str(self.home / '.config/opencode/opencode.jsonc'),
                           CODEGRAPH_NO_DOWNLOAD='1', DO_NOT_TRACK='1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
        environment['PATH'] = ';'.join(str(self.home / relative) for relative in ('.bun/bin', '.local/bin', '.pixi/bin')) + ';' + environment['PATH']
        commands = {'bun': ('1.3.11', '.bun/bin/bun.exe'), 'atuin': ('18.23.0', '.pixi/bin/atuin.exe'),
                    'nu': ('0.116.1', '.pixi/bin/nu.exe'), 'rtk': ('0.51.0', '.pixi/bin/rtk.exe'),
                    'hx': ('25.07.1', '.pixi/bin/hx.exe'), 'jq': ('1.8.2', '.pixi/bin/jq.exe'),
                    'kimi': ('2.1.1', '.bun/bin/kimi.cmd'), 'pi': ('1.2.0', '.bun/bin/pi.cmd'),
                    'opencode': ('2.0.27', '.bun/bin/opencode.cmd'), 'claude': ('2.1.296', '.bun/bin/claude.cmd'),
                    'codex': ('0.162.1', '.bun/bin/codex.cmd'), 'codegraph': ('1.6.2', '.bun/bin/codegraph.cmd')}
        for name, (pin, relative) in commands.items():
            with self.subTest(command=name):
                diagnostic = subprocess.run([str(self.home / relative), '--version'], env=environment,
                                            capture_output=True, text=True, timeout=60)
                self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
                self.assertIn(pin, diagnostic.stdout)
        doctor = subprocess.run([str(self.home / '.bun/bin/kimi.cmd'), 'doctor'], env=environment,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn('bash', doctor.stdout.lower())
        # Native managed Nu discovers its configured home without --config flags.
        ordinary = environment.copy()
        # Nu's native fallback uses Known Folder APIs. Do not remove the XDG
        # startup boundary in a disposable-home test and scaffold the real CI
        # user's RoamingAppData. Ordinary managed launch has no --config flags.
        probe = subprocess.run([str(self.home / '.pixi/bin/nu.exe'), '-c',
                                '[$nu.default-config-dir $env.EDITOR $env.UV_PYTHON_PREFERENCE] | to json'],
                               env=ordinary, capture_output=True, text=True, timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        values = json.loads(probe.stdout)
        self.assertEqual(Path(values[0]), self.home / '.config/nushell')
        self.assertEqual(values[1:], ['hx', 'managed'])
        pip = subprocess.run([str(self.home / '.pixi/bin/python.exe'), '-m', 'pip', 'config', 'debug'],
                             env=ordinary, capture_output=True, text=True, timeout=30)
        self.assertEqual(pip.returncode, 0, pip.stderr)
        self.assertIn(str(self.home / 'AppData/Roaming/pip/pip.ini'), pip.stdout)
        self.assertIn('mirrors.tuna.tsinghua.edu.cn', pip.stdout)
        uv_environment = ordinary.copy()
        for name in tuple(uv_environment):
            if name.startswith(('UV_DEFAULT_INDEX', 'UV_INDEX', 'PIP_INDEX', 'UV_CONFIG_FILE')):
                uv_environment.pop(name)
        uv = subprocess.run([str(self.home / '.pixi/bin/uv.exe'), 'pip', 'install', '--dry-run', '--system',
                             '--offline', '--no-cache', '-v', 'dotfiles-native-absent-discovery-probe'],
                            cwd=self.home, env=uv_environment, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(uv.returncode, 0)  # The synthetic package is deliberately unavailable.
        self.assertIn('mirrors.tuna.tsinghua.edu.cn', uv.stdout + uv.stderr)
        bash = subprocess.run([environment['KIMI_SHELL_PATH'], '--noprofile', '-c',
                               '. "$HOME/.env_core"; command -v nu; command -v atuin; atuin config get --resolved db_path'],
                              env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(bash.returncode, 0, bash.stderr)
        self.assertIn('.pixi', bash.stdout)
        self.assertEqual(Path(bash.stdout.splitlines()[-1]), self.home / '.local/share/atuin/history.db')
        from fixtures.windows_clients import verify_clients
        verify_clients(self, SOURCE, environment)
        console_report = self.root / 'native-console-report.json'
        console = subprocess.run([str(self.home / '.pixi/bin/python.exe'), str(SOURCE / 'tests/fixtures/windows_console.py'),
                                  '--home', str(self.home), '--source', str(SOURCE), '--report', str(console_report)],
                                 env=environment, creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=300)
        self.assertEqual(console.returncode, 0, console_report.read_text() if console_report.exists() else 'native console fixture produced no report')
        self.assertEqual(json.loads(console_report.read_text())['status'], 'passed')
        native_atuin = str(self.home / '.pixi/bin/atuin.exe')
        no_console = subprocess.run([str(self.home / '.pixi/bin/python.exe'),
                                     str(SOURCE / 'dot_local/lib/dotfiles/history.py'), 'join'],
                                    env=environment, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(no_console.returncode, 0)
        self.assertIn('interactive Windows console', no_console.stderr)
        # File-only migration also runs with native Rust/SQLite, never a Known
        # Folder importer. The same two public probes passed locally on Linux.
        from test_portable_history_import import PortableHistoryImportTests
        saved_tools = {name: os.environ.get(name) for name in ('DOTFILES_TEST_ATUIN', 'DOTFILES_TEST_PYTHON')}
        os.environ.update(DOTFILES_TEST_ATUIN=native_atuin, DOTFILES_TEST_PYTHON=str(self.home / '.pixi/bin/python.exe'))
        try:
            import test_portable_history_import as portable
            portable.ATUIN = native_atuin
            portable.PYTHON = str(self.home / '.pixi/bin/python.exe')
            for method in ('test_explicit_nu_text_uses_only_selected_file_and_filters_before_activation',
                           'test_nu_sqlite_preserves_public_metadata_and_signed_session'):
                probe = PortableHistoryImportTests(method)
                probe.setUp()
                try:
                    getattr(probe, method)()
                finally:
                    probe.doCleanups()
        finally:
            for name, value in saved_tools.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        protected = self.home / '.codex/auth.json'
        protected.write_text('{"synthetic":"native-preserve"}')
        again = self.deploy('-Role', role, '-Agents', 'none')
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(protected.read_text(), '{"synthetic":"native-preserve"}')
        self.assertTrue((self.home / '.bun/bin/codex.cmd').exists())




if __name__ == "__main__":
    unittest.main()
