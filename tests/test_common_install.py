"""Network-enabled Linux acceptance, separate from deterministic plan checks.

Set DOTFILES_TEST_INSTALL=1. DOTFILES_TEST_INSTALL_HOME optionally retains an
isolated home for later diagnostics; it must be under /tmp.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

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
        command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(home), "--platform", "linux"]
        for attempt in (1, 2):
            result = subprocess.run(command, cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=1800)
            (home / f"install-{attempt}.log").write_text(result.stdout + result.stderr)
            # Ticket 04 supplies the next stage. A midpoint check establishes
            # only common success, and never calls the full bootstrap a pass.
            if result.returncode:
                self.assertEqual(result.returncode, 1, result.stderr[-5000:])
                self.assertIn("agent installation awaits ticket 04", result.stderr, result.stderr[-5000:])
                self.assertNotIn("dotfiles: applied", result.stdout)
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
            self.assertEqual(node.stdout.strip(), "v24.21.0")
            pip = subprocess.run([str(home / ".pixi/bin/pip"), "config", "get", "global.index-url"], env=diagnostic_environment, capture_output=True, text=True)
            self.assertEqual(pip.returncode, 0, pip.stderr)
            self.assertEqual(pip.stdout.strip(), "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
            uv = subprocess.run([str(home / ".pixi/bin/uv"), "--show-settings", "pip", "install", "--dry-run", "--system", "--python", str(home / ".pixi/bin/python"), "--offline", "dotfiles-unavailable==0.0.0"], env=diagnostic_environment, capture_output=True, text=True)
            self.assertIn("https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/", uv.stdout + uv.stderr)
            contents = subprocess.run([str(home / ".pixi/bin/python"), "-c", "import json,pathlib,tomllib; print(json.dumps(tomllib.loads(pathlib.Path.home().joinpath('.pixi/manifests/pixi-global.toml').read_text())))"], env=diagnostic_environment, capture_output=True, text=True)
            self.assertEqual(contents.returncode, 0, contents.stderr)
            registered = json.loads(contents.stdout)
            self.assertEqual(registered["envs"]["device-extra"]["exposed"], {"device-zoxide": "zoxide"})
            for specialist in ("samtools", "nvtop", "zed", "firefox"):
                self.assertNotIn(specialist, registered["envs"])


if __name__ == "__main__":
    unittest.main()
