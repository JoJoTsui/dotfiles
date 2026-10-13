"""Real optional Linux installation; never substitutes metadata for execution.

Enable with DOTFILES_TEST_BUNDLE_INSTALL=1. A retained home and supplied manager
binary must be under /tmp; GPU/GUI capabilities are separate host prerequisites.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_BUNDLE_INSTALL") == "1", "requires explicit isolated bundle installation")
class BundleInstallTests(unittest.TestCase):
    def test_selected_linux_bundles_expose_commands_and_remain_after_deselection(self):
        target = os.environ.get("DOTFILES_TEST_BUNDLE_HOME")
        if target:
            home = Path(target).resolve()
            self.assertTrue(str(home).startswith("/tmp/"), "retained test home must be under /tmp")
        else:
            temporary = tempfile.TemporaryDirectory(prefix="dotfiles-bundle-install-")
            self.addCleanup(temporary.cleanup)
            home = Path(temporary.name) / "home"
        environment = os.environ.copy()
        for name in tuple(environment):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_", "PIP_", "NPM_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN", "NODE_OPTIONS", "ENV", "BASH_ENV",
                "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
            ):
                environment.pop(name)
        environment.update(HOME=str(home), PATH="/usr/bin:/bin")
        for variable, setting in (("DOTFILES_TEST_PIXI", "DOTFILES_PIXI_BIN"), ("DOTFILES_TEST_CHEZMOI", "DOTFILES_CHEZMOI_BIN")):
            supplied = os.environ.get(variable)
            if supplied:
                self.assertTrue(str(Path(supplied).resolve()).startswith("/tmp/"), "supplied test manager must be under /tmp")
                if setting == "DOTFILES_PIXI_BIN":
                    # A fresh shell discovers its manager in the designated
                    # managed PATH. Copy only the verified supplied executable;
                    # all prefixes, registries, and caches remain independent.
                    managed_pixi = home / ".pixi/bin/pixi"
                    managed_pixi.parent.mkdir(parents=True, exist_ok=True)
                    if Path(supplied).resolve() != managed_pixi.resolve():
                        shutil.copy2(supplied, managed_pixi)
                    supplied = str(managed_pixi)
                environment[setting] = supplied
        registry = home / ".pixi/manifests/pixi-global.toml"
        if not registry.exists():
            registry.parent.mkdir(parents=True)
            registry.write_text('version = 1\n[envs.device-extra]\nchannels = ["conda-forge"]\ndependencies = { zoxide = "==0.10.0" }\nexposed = { device-zoxide = "zoxide" }\n')
        selection = os.environ.get("DOTFILES_TEST_BUNDLE_SELECTION", "bio,gpu,desktop,developer")
        command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(home), "--platform", "linux", "--arch", "x86_64"]
        help_result = subprocess.run(command + ["--help"], env=environment, capture_output=True, text=True)
        if "--agents" in help_result.stdout:
            command += ["--agents", "none"]
        selected = selection.split(",")
        for attempt, bundles in enumerate((selection, "none"), 1):
            result = subprocess.run(command + ["--bundles", bundles], cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=1800)
            (home / f"bundle-install-{attempt}.log").write_text(result.stdout + result.stderr)
            if "--agents" in help_result.stdout:
                self.assertEqual(result.returncode, 0, result.stderr[-5000:])
            else:
                # The common/bundle stage is measurable before ticket04 lands;
                # this midpoint is never described as a full-bootstrap pass.
                self.assertEqual(result.returncode, 1, result.stderr[-5000:])
                self.assertIn("agent installation awaits ticket 04", result.stderr, result.stderr[-5000:])
            managed = dict(environment, PATH=f"{home}/.local/bin:{home}/.pixi/bin:{home}/.cargo/bin:/usr/bin:/bin",
                           XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
                           XDG_CACHE_HOME=str(home / ".cache"), PIXI_HOME=str(home / ".pixi"),
                           CARGO_HOME=str(home / ".cargo"), RUSTUP_HOME=str(home / ".rustup"), MOZ_HEADLESS="1")
            diagnostics = {"bio": (("samtools", "--version"), ("seqkit", "version"), ("fetchChromSizes", "--help")),
                           "gpu": (("nvtop", "--version"),),
                           "desktop": (("firefox", "--version"), ("zed", "--version")),
                           "developer": (("sd", "--version"), ("shellcheck", "--version"), ("herdr", "--version"), ("zellij", "--version"),
                                         ("duckdb-python", "-c", "import duckdb; assert duckdb.sql('select 42').fetchone() == (42,)"))}
            for bundle in selected:
                for tool, *arguments in diagnostics[bundle]:
                    with self.subTest(attempt=attempt, command=tool):
                        location = subprocess.run(["/bin/sh", "-c", f"command -v {tool}"], env=managed, capture_output=True, text=True)
                        self.assertEqual(location.returncode, 0, location.stderr)
                        self.assertTrue(location.stdout.strip().startswith(str(home) + "/"), location.stdout)
                        diagnostic = subprocess.run([location.stdout.strip(), *arguments], env=managed, cwd=home, capture_output=True, text=True, timeout=30)
                        self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
            registered = subprocess.run([str(home / ".pixi/bin/python"), "-c", "import json,pathlib,tomllib; print(json.dumps(tomllib.loads(pathlib.Path.home().joinpath('.pixi/manifests/pixi-global.toml').read_text())))"], env=managed, capture_output=True, text=True)
            self.assertEqual(registered.returncode, 0, registered.stderr)
            contents = json.loads(registered.stdout)
            self.assertEqual(contents["envs"]["device-extra"]["exposed"], {"device-zoxide": "zoxide"})
            for bundle, sample in (("bio", "samtools"), ("gpu", "nvtop"), ("desktop", "zed"), ("developer", "herdr")):
                if bundle in selected:
                    self.assertIn(sample, contents["envs"])


if __name__ == "__main__":
    unittest.main()
