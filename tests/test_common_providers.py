"""Common command adoption, isolation, and transitions back to Pixi."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import tomllib
except ImportError:
    tomllib = None

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "POSIX installer boundary")
class CommonProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-common-provider-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        (self.source / "deployment").mkdir(parents=True)
        self.home = self.root / "home"
        (self.home / ".local/bin").mkdir(parents=True)
        self.tools = self.root / "device"
        self.tools.mkdir()
        self.formula = self.root / "formula"
        (self.formula / "bin").mkdir(parents=True)
        self.catalog = self.source / "deployment/installer-tools.tsv"
        self.catalog.write_text("uv|homebrew|formula|uv|1.0.0|common|macos\n")
        (self.source / "deployment/common-tools.tsv").write_text(
            "uv|uv==1.0.0|uv=uv,uvx=uvx|all\n")
        self.log = self.root / "brew.log"
        self.brew = self.root / "brew"
        self.brew.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> '{self.log}'\n"
            f"case \"$1\" in --prefix) echo '{self.formula}' ;;\n"
            "list) exit 1 ;; install) exit 17 ;; esac\n")
        self.brew.chmod(0o755)
        self.state = self.home / ".local/state/dotfiles/installer-tools.lock.tsv"

    def binary(self, directory, name, version):
        binary = directory / name
        binary.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n")
        binary.chmod(0o755)
        return binary

    def run_installer(self, body="install_installer_tools", *, native=True, account=False):
        script = self.root / "run.sh"
        script.write_text(
            "set -euo pipefail\n"
            f"DEPLOY_SOURCE='{self.source}'\nDEPLOY_PLATFORM=macos\n"
            f"DEPLOY_HOME='{self.home}'\nexport HOME='{self.home}'\n"
            f"export PIXI_HOME='{self.home / '.pixi'}'\n"
            f"export XDG_STATE_HOME='{self.home / '.local/state'}'\n"
            f"export PATH='{self.tools}:/usr/bin:/bin'\n"
            f"DOTFILES_HOMEBREW_BIN='{self.brew}'\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            "bundle_selected() { return 1; }\n"
            f"detect_platform() {{ echo '{'macos' if native else 'linux'}'; }}\n"
            f"native_account_value() {{ echo '{self.home if account else '/another-account'}'; }}\n"
            f"source '{SOURCE}/deployment/common.sh'\n"
            f"source '{SOURCE}/deployment/installer.sh'\n" + body + "\n")
        return subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, timeout=30)

    def test_adopts_complete_group_and_reapplies_executable_launchers(self):
        for command in ("uv", "uvx"):
            self.binary(self.tools, command, "uv 1.2.0")
        for _ in range(2):
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.state.read_text(), "uv|adopted|1.2.0|1.0.0\n")
            self.assertFalse(self.log.exists())
            for command in ("uv", "uvx"):
                launcher = self.home / ".local/bin" / command
                self.assertFalse(launcher.is_symlink())
                output = subprocess.check_output([str(launcher), "--version"], text=True)
                self.assertEqual(output.strip(), "uv 1.2.0")

    def test_missing_alias_or_old_version_falls_back_without_homebrew_writes(self):
        self.binary(self.tools, "uv", "uv 1.2.0")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_text(), "")
        self.assertNotIn("install", self.log.read_text())
        self.binary(self.tools, "uvx", "uv 1.2.0")
        self.binary(self.tools, "uv", "uv 0.9.0")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_text(), "")

    def test_formula_libexec_adoption_and_transition_back_to_pixi(self):
        self.brew.write_text(
            f"#!/bin/sh\ncase \"$1\" in list) echo 'uv 1.2.0_1' ;; --prefix) echo '{self.formula}' ;; *) exit 18 ;; esac\n")
        self.binary(self.formula / "bin", "uv", "uv 1.2.0")
        (self.formula / "libexec/bin").mkdir(parents=True)
        self.binary(self.formula / "libexec/bin", "uvx", "uv 1.2.0")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uv|homebrew|1.2.0|1.0.0", self.state.read_text())
        (self.formula / "bin/uv").unlink()
        pixi_bin = self.home / ".pixi/bin"
        pixi_bin.mkdir(parents=True)
        for command in ("uv", "uvx"):
            self.binary(pixi_bin, command, "uv 1.0.0")
        result = self.run_installer("install_installer_tools\ninstaller_expose_common")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_text(), "")
        output = subprocess.check_output([str(self.home / ".local/bin/uv"), "--version"], text=True)
        self.assertEqual(output.strip(), "uv 1.0.0")
        self.assertTrue((self.state.parent / "common-tools.ready").is_file())

    def test_failed_install_retries_then_falls_back_and_foreign_target_never_adopts(self):
        result = self.run_installer("sleep() { :; }\ninstall_installer_tools", account=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().count("install uv"), 3)
        for command in ("uv", "uvx"):
            self.binary(self.tools, command, "uv 1.2.0")
        result = self.run_installer(native=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_text(), "")

    def test_missing_formula_is_installed_only_on_the_account_home(self):
        self.brew.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> '{self.log}'\n"
            f"case \"$1\" in list) [ -f '{self.formula}/bin/uv' ] && echo 'uv 1.2.0' ;;\n"
            f"--prefix) echo '{self.formula}' ;;\n"
            f"install) cp '{self.tools}/uv-template' '{self.formula}/bin/uv'; cp '{self.tools}/uv-template' '{self.formula}/bin/uvx' ;; esac\n")
        self.binary(self.tools, "uv-template", "uv 1.2.0")
        result = self.run_installer(account=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().count("install uv"), 1)
        self.assertEqual(self.state.read_text(), "uv|homebrew|1.2.0|1.0.0\n")

    def test_device_file_collision_preserves_file_and_prior_state(self):
        for command in ("uv", "uvx"):
            self.binary(self.tools, command, "uv 1.2.0")
        original = self.home / ".local/bin/uv"
        original.write_text("device content\n")
        self.state.parent.mkdir(parents=True)
        self.state.write_text("previous state\n")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("replace a device file", result.stderr)
        self.assertEqual(original.read_text(), "device content\n")
        self.assertEqual(self.state.read_text(), "previous state\n")
        self.assertFalse((self.state.parent / "common-tools.ready").exists())

    def test_python_aliases_use_the_validated_executables(self):
        self.catalog.write_text("python|homebrew|formula|python@3.15|3.15.2|common|macos\n")
        (self.source / "deployment/common-tools.tsv").write_text(
            "python|python==3.15.2,pip==26.2.2|python=python,python3=python,pip=pip,pip3=pip|all\n")
        for command, version in (("python", "3.15.2"), ("pip", "26.2.2"),
                                 ("python3", "3.8.0"), ("pip3", "19.0.0")):
            self.binary(self.tools, command, version)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        for command, expected in (("python3", "3.15.2"), ("pip3", "26.2.2")):
            output = subprocess.check_output([str(self.home / ".local/bin" / command)], text=True)
            self.assertEqual(output.strip(), expected)

    @unittest.skipUnless(tomllib, "registry assertions require Python 3.11 or newer")
    def test_provider_filter_preserves_existing_registry_and_unresolved_pins(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text("uv|homebrew|1.2.0|1.0.0\n")
        registry = self.root / "pixi-global.toml"
        registry.write_text('version = 1\n[envs.uv]\nexposed = { device-uv = "uv" }\n')
        desired = self.root / "desired.toml"
        desired.write_text('version = 1\n[envs.uv]\ndependencies = { uv = "==1.0.0" }\n'
                           '[envs.ripgrep]\ndependencies = { ripgrep = "==15.2.0" }\n')
        result = subprocess.run([sys.executable, str(SOURCE / "deployment/merge_pixi.py"),
                                 "--providers", str(self.state), str(desired), str(registry)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        environments = tomllib.loads(registry.read_text())["envs"]
        self.assertEqual(environments["uv"], {"exposed": {"device-uv": "uv"}})
        self.assertEqual(environments["ripgrep"]["dependencies"], {"ripgrep": "==15.2.0"})


if __name__ == "__main__":
    unittest.main()
