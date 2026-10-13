"""Optional bundle acceptance through the public deployment boundary."""
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest
import sys
from pins import manager_pin

SOURCE = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-bundles-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.environment = os.environ.copy()
        for name in tuple(self.environment):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_", "PIP_", "NPM_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN", "NODE_OPTIONS", "ENV", "BASH_ENV",
            ):
                self.environment.pop(name)
        self.environment.update(HOME=str(self.root / "original"))
        guards = self.root / "guards"
        guards.mkdir()
        for name in ("curl", "wget", "mysql", "ftp", "sudo", "chsh"):
            command = guards / name
            command.write_text('#!/bin/sh\nprintf "forbidden external command: %s\\n" "$0" >&2\nexit 91\n')
            command.chmod(0o755)
        self.environment["PATH"] = f"{guards}:{self.environment['PATH']}"

    def deploy(self, *arguments, environment=None):
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(self.home), *arguments],
                              env=environment or self.environment, cwd=SOURCE,
                              capture_output=True, text=True, timeout=30)

    def plan(self, *arguments, environment=None):
        result = self.deploy("--plan", *arguments, environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_explicit_bundles_add_tools_and_override_environment_without_writes(self):
        environment = dict(self.environment, DOTFILES_BUNDLES="desktop")
        plan = self.plan("--platform", "linux", "--arch", "x86_64", "--bundles", "bio,gpu", environment=environment)
        self.assertEqual(plan["bundles"], ["bio", "gpu"])
        self.assertIn("samtools", plan["tools"])
        self.assertIn("nvtop", plan["tools"])
        self.assertNotIn("firefox", plan["tools"])
        self.assertFalse(self.home.exists())

    def test_unsupported_and_unknown_full_bundles_fail_before_any_state_is_created(self):
        for platform, architecture, bundle in (
            ("macos", "x86_64", "bio"),
            ("windows", "x86_64", "gpu"),
            ("linux", "aarch64", "desktop"),
            ("macos", "aarch64", "developer"),
            ("linux", "x86_64", "bio,unknown"),
            ("linux", "x86_64", "bio,,gpu"),
            ("linux", "x86_64", ""),
        ):
            with self.subTest(platform=platform, architecture=architecture, bundle=bundle):
                self.home = self.root / f"{platform}-{architecture}-{bundle}"
                result = self.deploy("--platform", platform, "--arch", architecture, "--bundles", bundle)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("dotfiles:", result.stderr)
                self.assertFalse(self.home.exists())

    def test_selected_bundle_application_renders_complete_inventory_and_gates_payloads(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual bundle application requires chezmoi")
        environment = dict(self.environment, DOTFILES_CHEZMOI_BIN=chezmoi)
        result = self.deploy("--apply-only", "--platform", "linux", "--arch", "x86_64",
                             "--bundles", "bio,gpu,desktop,developer", environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        desired = (self.home / ".config/dotfiles/pixi-bundles.toml").read_text()
        for tool in ("aardvark", "bcftools", "bedtools", "gdc-client", "htslib", "kmc", "mosdepth", "picard",
                     "salmon", "sambamba", "samtools", "seqkit", "tgv", "vg", "nvtop", "zed", "firefox",
                     "shellcheck", "shfmt", "fnm", "sd", "duckdb", "zellij", "herdr"):
            self.assertIn(f'[envs."{tool}"]', desired)
        self.assertIn('"duckdb-python" = "python"', desired)
        self.assertIn('"samtools" = "==1.24"', desired)
        for relative in (".config/herdr/config.toml", ".config/zellij/config.kdl", ".local/bin/fetchChromSizes"):
            payload = self.home / relative
            self.assertTrue(payload.is_file(), relative)
            self.assertFalse(payload.is_symlink(), relative)
        self.assertTrue((self.home / ".local/bin/fetchChromSizes").stat().st_mode & 0o100)
        profile = json.loads((self.home / ".config/dotfiles/profile.json").read_text())
        self.assertEqual(profile["bundles"], ["bio", "gpu", "desktop", "developer"])

    def test_selected_tools_merge_with_device_inventory_and_deselection_keeps_it(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual bundle application requires chezmoi")
        try:
            import tomllib
        except ImportError:
            self.skipTest("registry assertions require Python 3.11 or newer")
        registry = self.home / ".pixi/manifests/pixi-global.toml"
        registry.parent.mkdir(parents=True)
        registry.write_text('version = 1\n[envs.device-extra]\nchannels = ["conda-forge"]\ndependencies = { zoxide = "==0.10.0" }\nexposed = { device-zoxide = "zoxide" }\n')
        pixi = self.root / "controlled-pixi"
        pixi.write_text('#!/bin/sh\ncase "$1 $2" in "--version ") echo "pixi ' + manager_pin("PIXI_VERSION") + '" ;; "exec "*) shift 3; shift; exec ' + shlex.quote(sys.executable) + ' "$@" ;; "global sync") exit 37 ;; *) exit 95 ;; esac\n')
        pixi.chmod(0o755)
        environment = dict(self.environment, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_PIXI_BIN=str(pixi))
        for selection in ("bio", "none"):
            result = self.deploy("--platform", "linux", "--arch", "x86_64", "--bundles", selection, environment=environment)
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertIn("install-common.pixi-sync", result.stderr)
            registered = tomllib.loads(registry.read_text())
            self.assertEqual(registered["envs"]["samtools"]["dependencies"], {"samtools": "==1.24"})
            self.assertEqual(registered["envs"]["device-extra"]["exposed"], {"device-zoxide": "zoxide"})

    def test_bundle_plan_declares_exact_tools_channels_and_host_prerequisites(self):
        plan = self.plan("--platform", "linux", "--arch", "aarch64", "--bundles", "bio,gpu")
        packages = {item["environment"]: item for item in plan["bundlePackages"]}
        self.assertEqual(len(packages), 16)
        self.assertEqual(packages["samtools"]["dependencies"], {"samtools": "==1.24"})
        self.assertEqual(packages["samtools"]["channels"], ["conda-forge", "bioconda"])
        self.assertEqual(packages["nvtop"]["exposed"], {"nvtop": "nvtop"})
        self.assertIn("driver", plan["bundlePrerequisites"]["gpu"])
        self.assertIn("Reference", plan["bundlePrerequisites"]["bio"])

    def test_bio_helper_has_a_harmless_help_boundary_and_declares_its_transport(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual bundle application requires chezmoi")
        result = self.deploy("--apply-only", "--platform", "linux", "--arch", "x86_64", "--bundles", "bio",
                             environment=dict(self.environment, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(self.home / ".local/bin/fetchChromSizes"), "--help"],
                                cwd=self.root, env=self.environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage:", result.stdout)
        self.assertNotIn("forbidden external command", result.stdout + result.stderr)
        plan = self.plan("--platform", "linux", "--arch", "x86_64", "--bundles", "bio")
        self.assertIn("curl", plan["tools"])
        self.assertIn("fetchChromSizes", plan["tools"])

    def test_common_defaults_leave_every_optional_bundle_unselected_for_both_roles(self):
        for platform in ("linux", "wsl", "macos", "windows"):
            for role in ("workstation", "remote-compute"):
                for architecture in (("x86_64",) if platform == "windows" else ("x86_64", "aarch64")):
                    plan = self.plan("--platform", platform, "--arch", architecture, "--role", role)
                    self.assertEqual(plan["bundles"], [])
                    self.assertEqual(plan["bundlePackages"], [])
                    for tool in ("samtools", "nvtop", "zed", "firefox", "herdr", "zellij"):
                        self.assertNotIn(tool, plan["tools"])
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if chezmoi:
            for role in ("workstation", "remote-compute"):
                self.home = self.root / role
                result = self.deploy("--apply-only", "--platform", "linux", "--role", role,
                                     environment=dict(self.environment, DOTFILES_CHEZMOI_BIN=chezmoi))
                self.assertEqual(result.returncode, 0, result.stderr)
                for relative in (".config/herdr/config.toml", ".config/zellij/config.kdl", ".local/bin/fetchChromSizes"):
                    self.assertFalse((self.home / relative).exists(), relative)
                self.assertNotIn('[envs."samtools"]', (self.home / ".config/dotfiles/pixi-bundles.toml").read_text())

    def test_linux_desktop_owns_firefox_runtime_libraries_without_foreign_linux_dependencies(self):
        linux = self.plan("--platform", "linux", "--arch", "x86_64", "--bundles", "desktop")
        firefox = next(package for package in linux["bundlePackages"] if package["environment"] == "firefox")
        self.assertEqual(firefox["dependencies"]["xorg-libx11"], "==1.8.13")
        self.assertEqual(firefox["dependencies"]["gtk3"], "==3.24.52")
        for platform in ("macos", "windows"):
            plan = self.plan("--platform", platform, "--arch", "x86_64", "--bundles", "desktop")
            firefox = next(package for package in plan["bundlePackages"] if package["environment"] == "firefox")
            self.assertEqual(firefox["dependencies"], {"firefox": "==157.0.1"})


if __name__ == "__main__":
    unittest.main()
