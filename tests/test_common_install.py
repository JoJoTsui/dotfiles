"""Network-enabled Linux acceptance, separate from deterministic plan checks.

Set DOTFILES_TEST_INSTALL=1. DOTFILES_TEST_INSTALL_HOME optionally retains an
isolated home for later diagnostics; it must be under /tmp.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from pins import common_pin, manager_pin

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_INSTALL") == "1", "requires explicit isolated network installation")
class CommonInstallTests(unittest.TestCase):
    def test_linux_common_tools_install_expose_and_preserve_device_inventory(self):
        target = os.environ.get("DOTFILES_TEST_INSTALL_HOME")
        if target:
            home = Path(target).resolve()
            self.assertTrue(str(home).startswith("/tmp/"), "retained test home must be under /tmp")
        else:
            temporary = tempfile.TemporaryDirectory(prefix="dotfiles-common-")
            self.addCleanup(temporary.cleanup)
            home = Path(temporary.name) / "home"
        environment = os.environ.copy()
        for name in tuple(environment):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_", "PIP_", "NPM_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN", "NODE_OPTIONS", "ENV", "BASH_ENV",
            ):
                environment.pop(name)
        environment.update(HOME=str(home), PATH="/usr/bin:/bin")
        registry = home / ".pixi/manifests/pixi-global.toml"
        if not registry.exists():
            registry.parent.mkdir(parents=True)
            registry.write_text('version = 1\n[envs.device-extra]\nchannels = ["conda-forge"]\ndependencies = { zoxide = "==0.10.0" }\nexposed = { device-zoxide = "zoxide" }\n')
        # The gateway slice has its own tests; this one measures the common
        # tool installation, so the gateway step stays out of the run.
        command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(home), "--platform", "linux",
                   "--no-magpie"]
        for attempt in (1, 2):
            result = subprocess.run(command, cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=1800)
            (home / f"install-{attempt}.log").write_text(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr[-7000:])
            self.assertIn("dotfiles: applied", result.stdout)
            managed_path = f"{home}/.local/bin:{home}/.pixi/bin:{home}/.bun/bin:{home}/.cargo/bin:/usr/bin:/bin"
            diagnostic_environment = dict(environment, PATH=managed_path,
                XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
                XDG_CACHE_HOME=str(home / ".cache"), PIXI_HOME=str(home / ".pixi"),
                CARGO_HOME=str(home / ".cargo"), RUSTUP_HOME=str(home / ".rustup"),
                ATUIN_CONFIG_DIR=str(home / ".config/atuin"), ATUIN_DATA_DIR=str(home / ".local/share/atuin"))
            for tool in ("pixi", "uv", "bun", "node", "nu", "bash", "zsh", "rtk", "atuin", "zoxide", "tspin", "less", "hx", "git", "gh", "starship", "direnv", "micromamba", "rustup", "device-zoxide"):
                with self.subTest(attempt=attempt, command=tool):
                    location = subprocess.run(["/bin/sh", "-c", f"command -v {tool}"], env=diagnostic_environment, capture_output=True, text=True)
                    self.assertEqual(location.returncode, 0, location.stderr)
                    self.assertTrue(location.stdout.strip().startswith(str(home) + "/"), location.stdout)
                    diagnostic = subprocess.run([location.stdout.strip(), "--version"], env=diagnostic_environment, capture_output=True, text=True, timeout=30)
                    self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
            node = subprocess.run([str(home / ".pixi/bin/node"), "--version"], env=diagnostic_environment, capture_output=True, text=True)
            self.assertEqual(node.stdout.strip(), "v" + common_pin("nodejs"))
            pip = subprocess.run([str(home / ".pixi/bin/pip"), "config", "get", "global.index-url"], env=diagnostic_environment, capture_output=True, text=True)
            self.assertEqual(pip.returncode, 0, pip.stderr)
            self.assertEqual(pip.stdout.strip(), "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
            uv_config = home / ".config/uv/uv.toml"
            self.assertTrue(uv_config.is_file(), f"rendered uv config is missing: {uv_config}")
            uv = subprocess.run([str(home / ".pixi/bin/uv"), "--show-settings", "pip", "install", "--dry-run", "--system", "--python", str(home / ".pixi/bin/python"), "--offline", "dotfiles-unavailable==0.0.0"], env=diagnostic_environment, capture_output=True, text=True)
            uv_settings = uv.stdout + uv.stderr
            self.assertIn("https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple", uv_settings,
                          f"uv did not discover the TUNA index; config={uv_config.read_text()}\n"
                          f"settings tail={uv_settings[-3000:]}")
            contents = subprocess.run([str(home / ".pixi/bin/python"), "-c", "import json,pathlib,tomllib; print(json.dumps(tomllib.loads(pathlib.Path.home().joinpath('.pixi/manifests/pixi-global.toml').read_text())))"], env=diagnostic_environment, capture_output=True, text=True)
            self.assertEqual(contents.returncode, 0, contents.stderr)
            registered = json.loads(contents.stdout)
            self.assertEqual(registered["envs"]["device-extra"]["exposed"], {"device-zoxide": "zoxide"})
            for specialist in ("samtools", "nvtop", "zed", "firefox"):
                self.assertNotIn(specialist, registered["envs"])


class PixiConcurrencyTests(unittest.TestCase):
    """Focused checks at the public-bootstrap/fake-Pixi seam.

    The native macOS gate supplies DOTFILES_PIXI_CONCURRENCY to bound Pixi's
    concurrent solves and downloads. These checks verify the value
    reaches both Pixi operations, that malformed values fail before either
    operation, and that an unset value leaves Pixi's flags untouched.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-pixi-concurrency-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        original = self.root / "original"
        original.mkdir()
        self.guards = self.root / "guards"
        self.guards.mkdir()
        for name in ("curl", "sudo", "chsh"):
            command = self.guards / name
            command.write_text('#!/bin/sh\nprintf "forbidden external command: %s\\n" "$0" >&2\nexit 91\n')
            command.chmod(0o755)
        self.env = {
            "HOME": str(original),
            "PATH": f"{self.guards}:/usr/bin:/bin:/usr/sbin:/sbin",
            "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library"),
            "PIXI_LOG": str(self.root / "pixi.log"),
        }
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")

    def fake_pixi(self):
        pixi = self.guards / "pixi"
        pixi.write_text(
            '#!/bin/sh\n'
            'case "$1 $2" in\n'
            '  "exec "*|"global sync"*) printf "%s\\n" "$*" >> "$PIXI_LOG" ;;\n'
            'esac\n'
            'case "$1 $2" in\n'
            '  "--version ") echo "pixi ' + manager_pin("PIXI_VERSION") + '" ;;\n'
            '  "exec "*) exit 0 ;;\n'
            '  "global sync") exit 37 ;;\n'
            '  *) exit 95 ;;\n'
            'esac\n')
        pixi.chmod(0o755)
        return pixi

    def deploy(self, **environment):
        environment.update(DOTFILES_PIXI_BIN=str(self.fake_pixi()),
                           DOTFILES_CHEZMOI_BIN=self.chezmoi)
        return subprocess.run(
            ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(self.home),
             "--platform", "linux", "--no-magpie"],
            env=dict(self.env, **environment), cwd=SOURCE, capture_output=True,
            text=True, timeout=60)

    def pixi_calls(self):
        log = self.root / "pixi.log"
        return log.read_text().splitlines() if log.exists() else []

    def require_chezmoi(self):
        if not self.chezmoi:
            self.skipTest("actual apply requires chezmoi")

    def test_bound_reaches_both_pixi_operations(self):
        self.require_chezmoi()
        result = self.deploy(DOTFILES_PIXI_CONCURRENCY="3")
        self.assertEqual(result.returncode, 37, result.stderr)
        calls = self.pixi_calls()
        self.assertEqual(len(calls), 2, calls)
        self.assertTrue(calls[0].startswith("exec "), calls)
        self.assertTrue(calls[1].startswith("global sync"), calls)
        for call in calls:
            self.assertIn("--concurrent-solves 3", call)
            self.assertIn("--concurrent-downloads 3", call)

    def test_unset_bound_keeps_pixi_defaults(self):
        self.require_chezmoi()
        result = self.deploy()
        self.assertEqual(result.returncode, 37, result.stderr)
        calls = self.pixi_calls()
        self.assertEqual(len(calls), 2, calls)
        for call in calls:
            self.assertNotIn("--concurrent-solves", call)
            self.assertNotIn("--concurrent-downloads", call)

    def test_malformed_bound_fails_before_either_pixi_operation(self):
        self.require_chezmoi()
        log = self.root / "pixi.log"
        for value in ("0", "-1", "2.5", "many"):
            with self.subTest(value=value):
                if log.exists():
                    log.unlink()
                result = self.deploy(DOTFILES_PIXI_CONCURRENCY=value)
                self.assertNotEqual(result.returncode, 37, result.stderr)
                self.assertIn("DOTFILES_PIXI_CONCURRENCY", result.stderr)
                calls = self.pixi_calls()
                self.assertFalse(any(call.startswith("exec ") or call.startswith("global sync")
                                     for call in calls), calls)


if __name__ == "__main__":
    unittest.main()
