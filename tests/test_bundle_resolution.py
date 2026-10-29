"""Network resolution of every declared optional bundle target from public plans."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_BUNDLE_RESOLUTION") == "1", "requires explicit foreign package resolution")
class BundleResolutionTests(unittest.TestCase):
    def test_all_declared_bundle_tool_targets_resolve_in_separate_environments(self):
        pixi = os.environ.get("DOTFILES_TEST_PIXI") or shutil.which("pixi")
        self.assertIsNotNone(pixi, "set DOTFILES_TEST_PIXI to the pinned Pixi binary")
        target = os.environ.get("DOTFILES_TEST_BUNDLE_RESOLUTION_ROOT")
        if target:
            root = Path(target).resolve()
            self.assertTrue(str(root).startswith("/tmp/"), "retained resolution root must be under /tmp")
            root.mkdir(parents=True, exist_ok=True)
        else:
            temporary = tempfile.TemporaryDirectory(prefix="dotfiles-bundle-resolution-")
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        home = root / "home"
        home.mkdir(exist_ok=True)
        environment = os.environ.copy()
        for name in tuple(environment):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "CONDA_", "MAMBA_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_", "PIP_", "NPM_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN", "NODE_OPTIONS", "ENV", "BASH_ENV",
            ):
                environment.pop(name)
        environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                           XDG_CACHE_HOME=str(home / ".cache"), PIXI_HOME=str(home / ".pixi"),
                           PIXI_CACHE_DIR=str(home / ".cache/pixi"))
        catalog = {}
        declarations = {"bio": (("linux", "x86_64", "linux-64"), ("linux", "aarch64", "linux-aarch64")),
                        "gpu": (("linux", "x86_64", "linux-64"), ("linux", "aarch64", "linux-aarch64")),
                        "desktop": (("linux", "x86_64", "linux-64"), ("macos", "x86_64", "osx-64"),
                                    ("macos", "aarch64", "osx-arm64"), ("windows", "x86_64", "win-64")),
                        "developer": (("linux", "x86_64", "linux-64"),),
                        "developer-portable": (("linux", "x86_64", "linux-64"), ("linux", "aarch64", "linux-aarch64"),
                                               ("macos", "x86_64", "osx-64"), ("macos", "aarch64", "osx-arm64"),
                                               ("windows", "x86_64", "win-64"))}
        for bundle, targets in declarations.items():
            for platform, architecture, subdir in targets:
                plan = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--plan", "--home", str(home),
                                       "--platform", platform, "--arch", architecture, "--bundles", bundle],
                                      env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(plan.returncode, 0, plan.stderr)
                for package in json.loads(plan.stdout)["bundlePackages"]:
                    name = package["environment"] + "-" + subdir
                    catalog[name] = (package, ["bundle-" + subdir if subdir != "win-64" else subdir])
        lines = ['[workspace]', 'name = "dotfiles-bundle-resolution"', 'channels = ["conda-forge"]',
                 'platforms = [{ name = "bundle-linux-64", platform = "linux-64", glibc = "2.28" }, { name = "bundle-linux-aarch64", platform = "linux-aarch64", glibc = "2.28" }, { name = "bundle-osx-64", platform = "osx-64", macos = "14.2" }, { name = "bundle-osx-arm64", platform = "osx-arm64", macos = "14.2" }, "win-64"]', '']
        for name, (package, targets) in catalog.items():
            lines += [f'[feature.{json.dumps(name)}]', 'platforms = ' + json.dumps(targets),
                      'channels = ' + json.dumps(package["channels"]), f'[feature.{json.dumps(name)}.dependencies]']
            lines += [f'{json.dumps(key)} = {json.dumps(value)}' for key, value in package["dependencies"].items()]
            lines.append('')
        lines += ['[environments]'] + [f'{json.dumps(name)} = {{ features = [{json.dumps(name)}], no-default-feature = true }}' for name in catalog]
        manifest = root / "pixi.toml"
        manifest.write_text('\n'.join(lines) + '\n')
        result = subprocess.run([pixi, "lock", "--manifest-path", str(manifest), "--no-config", "--concurrent-solves", "4"],
                                cwd=root, env=environment, capture_output=True, text=True, timeout=900)
        (root / "solve.log").write_text(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr[-6000:])
        self.assertTrue((root / "pixi.lock").is_file(), "resolution must produce a real Pixi lock")


if __name__ == "__main__":
    unittest.main()
