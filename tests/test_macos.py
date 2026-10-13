"""macOS profile configuration through the public deployment boundary.

These checks render macOS profiles on the current runtime. Native execution is
opt-in and recorded separately by the macOS CI verification entry point.
"""
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class MacOSProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-macos-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device with spaces"
        self.original = self.root / "original"
        self.original.mkdir()
        self.env = {"HOME": str(self.original), "PATH": "/usr/bin:/bin"}
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")

    def deploy(self, *arguments):
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--home", str(self.home), "--platform", "macos", *arguments],
                              env=dict(self.env, **({"DOTFILES_CHEZMOI_BIN": self.chezmoi} if self.chezmoi else {})),
                              cwd=SOURCE, capture_output=True, text=True, timeout=60)

    def test_macos_apply_places_regular_canonical_files_in_native_discovery_locations(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        result = self.deploy("--apply-only", "--arch", "aarch64")
        self.assertEqual(result.returncode, 0, result.stderr)
        native = self.home / "Library/Application Support"
        for filename in ("env.nu", "config.nu", "proxy.nu", "zoxide.nu", "micromamba.nu", "direnv.nu"):
            copied = native / "nushell" / filename
            self.assertTrue(copied.is_file(), str(copied))
            self.assertFalse(copied.is_symlink())
            self.assertEqual(copied.read_bytes(), (self.home / ".config/nushell" / filename).read_bytes())
        self.assertEqual((native / "pip/pip.conf").read_bytes(), (self.home / ".config/pip/pip.conf").read_bytes())
        self.assertFalse((self.home / ".github").exists())
        self.assertEqual(list(self.original.iterdir()), [])

    def test_native_discovery_symlinks_fail_before_any_source_application(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        for relative in ("Library", "Library/Application Support/nushell",
                         "Library/Application Support/pip/pip.conf",
                         ".local/share/nushell/vendor"):
            with self.subTest(relative=relative):
                self.home = self.root / relative.replace("/", "-")
                target = self.home / relative
                target.parent.mkdir(parents=True)
                target.symlink_to(self.original, target_is_directory=True)
                result = self.deploy("--apply-only")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("symlink", result.stderr)
                self.assertIn("apply-source.macos-discovery", result.stderr)
                self.assertFalse((self.home / ".env_core").exists())
                self.assertEqual(list(self.original.iterdir()), [])

    def test_existing_prepared_resources_are_discovered_with_native_nu_config(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        autoload = self.home / ".local/share/nushell/vendor/autoload"
        autoload.mkdir(parents=True)
        for name in ("starship", "pixi-completions", "atuin"):
            (autoload / f"{name}.nu").write_text(f'# synthetic prepared {name}\n')
        unrelated = self.home / "Library/Application Support/nushell/autoload/device.nu"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text('# unrelated user startup\n')
        result = self.deploy("--apply-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("starship", "pixi-completions", "atuin"):
            self.assertEqual((unrelated.parent / f"{name}.nu").read_bytes(),
                             (autoload / f"{name}.nu").read_bytes())
        self.assertEqual(unrelated.read_text(), '# unrelated user startup\n')

    def test_remote_editor_uses_selected_platform_and_managed_paths_with_literal_proxy(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        proxy = 'http://127.0.0.1:17777/?quote="value\\path\n$literal`'
        self.env["HTTP_PROXY_URL"] = proxy
        for platform, suffix, bash_relative in (
            ("macos", "osx", ".pixi/bin/bash"),
            ("linux", "linux", ".pixi/bin/bash"),
            ("windows", "windows", ".local/share/dotfiles/git-bash/bin/bash.exe"),
        ):
            with self.subTest(platform=platform):
                self.home = self.root / f'{platform} "quoted" \\ home'
                result = self.deploy("--platform", platform, "--role", "remote-compute", "--apply-only")
                self.assertEqual(result.returncode, 0, result.stderr)
                text = (self.home / ".vscode-server/data/Machine/settings.json").read_text()
                config = json.loads('\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('//')))
                self.assertEqual(config["http.proxy"], proxy)
                self.assertEqual(config["python.condaPath"], str(self.home / ".pixi/bin/micromamba") + (".exe" if platform == "windows" else ""))
                self.assertEqual(config["python.venvPath"], str(self.home / ".local/share/micromamba/envs"))
                self.assertEqual(config[f"terminal.integrated.defaultProfile.{suffix}"], "bash")
                profiles = config[f"terminal.integrated.profiles.{suffix}"]
                self.assertEqual(profiles["bash"]["path"], str(self.home / bash_relative))
                self.assertEqual(profiles["bash"]["env"]["DOTFILES_SECONDARY_SHELL"], "1")
                for other in ({"linux", "osx", "windows"} - {suffix}):
                    self.assertNotIn(f"terminal.integrated.env.{other}", config)

    @unittest.skipIf(sys.platform == "darwin", "this check exercises refusal on a foreign runtime")
    def test_native_verifier_reports_foreign_execution_as_unavailable(self):
        report = self.root / "native-report.json"
        result = subprocess.run([sys.executable, str(SOURCE / "tests/native_macos.py"),
                                 "--arch", "x86_64", "--role", "workstation", "--report", str(report)],
                                env=self.env, cwd=SOURCE, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report.is_file(), result.stderr)
        evidence = json.loads(report.read_text())
        self.assertEqual(evidence["status"], "unavailable")
        self.assertFalse(evidence["native_execution"])
        self.assertEqual(list(self.original.iterdir()), [])

    def test_both_architectures_and_roles_preserve_device_state_after_reapplication(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        for arch in ("x86_64", "aarch64"):
            for role in ("workstation", "remote-compute"):
                with self.subTest(arch=arch, role=role):
                    self.home = self.root / f"{arch}-{role}"
                    originals = {
                        ".codex/auth.json": '{"synthetic-only":"preserve"}\n',
                        ".bash_history": 'echo unrelated-history\n',
                        "Library/Application Support/nushell/history.txt": 'echo native-nu-history\n',
                        "Library/Application Support/nushell/autoload/device.nu": '# device startup\n',
                        ".agents/skills/device-extra/SKILL.md": '# device-only skill\n',
                    }
                    for relative, content in originals.items():
                        path = self.home / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(content)
                    arguments = ("--apply-only", "--arch", arch, "--role", role)
                    result = self.deploy(*arguments)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    desired = (self.home / ".config/dotfiles/pixi-global.toml").read_text()
                    self.assertIn('"bun" = "==1.3.11"', desired)
                    self.assertIn('"atuin" = "==18.23.0"', desired)
                    self.assertNotIn('[envs."nvtop"]', desired)
                    native_env = self.home / "Library/Application Support/nushell/env.nu"
                    self.assertIn(f'$env.CHOKIDAR_USEPOLLING? | default "{1 if role == "remote-compute" else 0}"', native_env.read_text())
                    before = native_env.read_bytes()
                    repeated = self.deploy(*arguments)
                    self.assertEqual(repeated.returncode, 0, repeated.stderr)
                    self.assertEqual(native_env.read_bytes(), before)
                    for relative, content in originals.items():
                        self.assertEqual((self.home / relative).read_text(), content)
                    self.assertEqual((self.home / ".vscode-server/data/Machine/settings.json").exists(), role == "remote-compute")

    def test_copied_native_startup_executes_real_generated_nu_resources(self):
        tool_home = os.environ.get("DOTFILES_TEST_TOOL_HOME")
        if not self.chezmoi or not tool_home:
            self.skipTest("requires chezmoi and read-only pinned tool prefix")
        result = self.deploy("--apply-only", "--role", "remote-compute")
        self.assertEqual(result.returncode, 0, result.stderr)
        prefix = Path(tool_home)
        tools = {"nu": "nushell", "starship": "starship", "zoxide": "zoxide",
                 "atuin": "atuin", "python": "python", "vivid": "vivid"}
        for command, environment in tools.items():
            binary = prefix / ".pixi/envs" / environment / "bin" / command
            self.assertTrue(binary.is_file(), str(binary))
            launcher = self.home / ".pixi/bin" / command
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(str(binary)) + ' "$@"\n')
            launcher.chmod(0o755)
        pixi = self.home / ".pixi/bin/pixi"
        pixi.write_text('#!/bin/sh\nexec ' + shlex.quote(str(prefix / ".pixi/bin/pixi")) + ' "$@"\n')
        pixi.chmod(0o755)
        env = dict(self.env, HOME=str(self.home), TERM="xterm-256color")
        for command in ("dotfiles-shell-prepare", "dotfiles-history-prepare"):
            prepared = subprocess.run([str(self.home / ".local/bin" / command)], env=env, cwd=self.home,
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertEqual(self.deploy("--apply-only", "--role", "remote-compute").returncode, 0)
        native = self.home / "Library/Application Support/nushell"
        # On Linux this verifies copied syntax at an explicit config directory.
        # Native macOS CI separately launches with no config/XDG overrides.
        command = [str(self.home / ".pixi/bin/nu"), "--config-home", str(native), "-e",
                   'print ({polling: $env.CHOKIDAR_USEPOLLING, starship: $env.STARSHIP_SHELL?, '
                   'pixi: (scope commands | where name == "pixi" | length), '
                   'history_hooks: ($env.config.hooks.pre_execution | length)} | to json --raw); exit']
        diagnostic = subprocess.run(command, env=env, cwd=self.home, capture_output=True, text=True, timeout=30)
        self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
        values = json.loads(diagnostic.stdout)
        self.assertEqual(values["polling"], "1")
        self.assertEqual(values["starship"], "nu")
        self.assertEqual(values["pixi"], 1)
        self.assertGreater(values["history_hooks"], 0)


if __name__ == "__main__":
    unittest.main()
