"""Deployment acceptance checks; all writes stay in disposable environments."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-deployment-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.original_home = self.root / "original"
        self.original_home.mkdir()
        self.env = os.environ.copy()
        for name in tuple(self.env):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN", "NODE_OPTIONS", "ENV", "BASH_ENV",
            ):
                self.env.pop(name)
        self.env["HOME"] = str(self.original_home)
        # Guard the network/account/system boundary even while a red test runs
        # against an older bootstrap that does not understand --plan.
        self.guards = self.root / "guards"
        self.guards.mkdir()
        for name in ("curl", "sudo", "chsh"):
            command = self.guards / name
            command.write_text('#!/bin/sh\nprintf "forbidden external command: %s\\n" "$0" >&2\nexit 91\n')
            command.chmod(0o755)
        self.env["PATH"] = f"{self.guards}:{self.env['PATH']}"

    def deploy(self, *arguments, env=None):
        command = ["bash", str(SOURCE / "bootstrap.sh"), "--home", str(self.home), *arguments]
        return subprocess.run(command, env=env or self.env, cwd=SOURCE, capture_output=True, text=True, timeout=30)

    def plan(self, *arguments, env=None):
        result = self.deploy("--plan", *arguments, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_plan_selects_role_independently_and_leaves_target_absent(self):
        plan = self.plan("--platform", "linux", "--role", "remote-compute")
        self.assertEqual(plan["profile"], "linux-remote-compute")
        self.assertEqual(plan["platform"], "linux")
        self.assertEqual(plan["role"], "remote-compute")
        self.assertEqual(plan["home"], str(self.home))
        self.assertEqual(plan["source"], str(SOURCE))
        self.assertEqual(plan["settings"]["mode"], "copy")
        self.assertIn("apply-source", plan["actions"])
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.original_home.iterdir()), [])

    def test_profile_presets_and_explicit_selectors_override_environment(self):
        legacy = dict(self.env, DOTFILES_CLASS="t9k")
        self.assertEqual(self.plan(env=legacy)["profile"], "linux-remote-compute")
        self.assertEqual(self.plan("--role", "workstation", env=legacy)["profile"], "linux-workstation")
        self.assertEqual(self.plan("--profile", "macos-workstation", env=legacy)["profile"], "macos-workstation")
        self.assertEqual(self.plan()["role"], "workstation")

    def test_invalid_or_conflicting_selections_fail_before_writing(self):
        cases = (
            ("--platform", "plan9"),
            ("--role", "server"),
            ("--profile", "linux-workstation", "--role", "remote-compute"),
            ("--class", "t9k", "--platform", "macos"),
            ("--platform", "windows", "--arch", "arm64"),
            ("--arch", "sparc"),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.deploy("--plan", *arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr.startswith("dotfiles:"), result.stderr)
                self.assertFalse(self.home.exists())

    def test_apply_uses_working_source_in_copy_mode_and_is_idempotent(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi; set DOTFILES_TEST_CHEZMOI to an isolated binary")
        source = self.root / "working-source"
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        with (source / "dot_env_core.tmpl").open("a") as handle:
            handle.write("\n# uncommitted-working-tree-marker\n")
        sentinel = self.original_home / "untouched"
        sentinel.write_text("other device state\n")
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi,
                           XDG_CONFIG_HOME=str(self.original_home / "config"),
                           PIXI_HOME=str(self.original_home / "pixi"),
                           BUN_INSTALL=str(self.original_home / "bun"))
        for role in ("workstation", "remote-compute"):
            with self.subTest(role=role):
                self.home = self.root / role
                args = ("--apply-only", "--source", str(source), "--platform", "linux", "--role", role)
                result = self.deploy(*args, env=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("uncommitted-working-tree-marker", (self.home / ".env_core").read_text())
                self.assertFalse((self.home / ".env_core").is_symlink())
                self.assertTrue((self.home / ".local/bin/nu-login").stat().st_mode & 0o100)
                self.assertEqual((self.home / ".vscode-server/data/Machine/settings.json").exists(), role == "remote-compute")
                self.assertIn("REPLACE_ME", (self.home / ".claude/settings.json").read_text())
                profile = json.loads((self.home / ".config/dotfiles/profile.json").read_text())
                self.assertEqual(profile["role"], role)
                for name in ("docs", "README.md", "AGENTS.md", "GLOSSARY.md", "deployment", "tests", "bootstrap.sh"):
                    self.assertFalse((self.home / name).exists(), name)
                before = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
                repeated = self.deploy(*args, env=environment)
                self.assertEqual(repeated.returncode, 0, repeated.stderr)
                after = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
                # chezmoi's state database records operation times; the target
                # payload and config remain identical after reapplication.
                before.pop(Path(".config/chezmoi/chezmoistate.boltdb"), None)
                after.pop(Path(".config/chezmoi/chezmoistate.boltdb"), None)
                self.assertEqual(before, after)
        self.assertEqual(sentinel.read_text(), "other device state\n")
        self.assertEqual(list(self.original_home.iterdir()), [sentinel])

    def test_plan_reports_isolated_state_roots_and_configured_actions(self):
        self.home = self.root / 'device "quoted" \\ path'
        environment = dict(self.env, GLM_API_TOKEN="synthetic-plan-secret", KIMI_API_KEY="synthetic-plan-secret")
        plan = self.plan("--apply-only", "--platform", "linux", env=environment)
        self.assertEqual(plan["actions"], ["apply-source"])
        self.assertEqual(plan["roots"]["config"], str(self.home / ".config"))
        self.assertEqual(plan["roots"]["pixi"], str(self.home / ".pixi"))
        self.assertEqual(plan["roots"]["bun"], str(self.home / ".bun"))
        self.assertEqual(plan["settings"]["primaryShell"], "nu")
        self.assertFalse(plan["settings"]["systemChanges"])
        self.assertFalse(plan["settings"]["loginShellChanges"])
        self.assertNotIn("synthetic-plan-secret", json.dumps(plan))
        self.assertFalse(self.home.exists())

    def test_apply_refuses_state_roots_that_escape_through_symlinks(self):
        self.home.mkdir()
        (self.home / ".local").symlink_to(self.original_home, target_is_directory=True)
        installer = self.guards / "chezmoi"
        installer.write_text("#!/bin/sh\nexit 42\n")
        installer.chmod(0o755)
        result = self.deploy("--apply-only", env=dict(self.env, DOTFILES_CHEZMOI_BIN=str(installer)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(list(self.original_home.iterdir()), [])

    def test_required_apply_failure_is_named_and_returns_failure(self):
        installer = self.guards / "chezmoi"
        installer.write_text("#!/bin/sh\nexit 42\n")
        installer.chmod(0o755)
        result = self.deploy("--apply-only", env=dict(self.env, DOTFILES_CHEZMOI_BIN=str(installer)))
        self.assertEqual(result.returncode, 42)
        self.assertIn("step apply-source failed (exit 42)", result.stderr)
        self.assertNotIn("applied", result.stdout)

    def test_all_profile_plans_resolve_the_accepted_platform_role_matrix(self):
        for platform in ("linux", "macos", "wsl", "windows"):
            for role in ("workstation", "remote-compute"):
                for architecture in (("x86_64",) if platform == "windows" else ("x86_64", "aarch64")):
                    with self.subTest(platform=platform, role=role, architecture=architecture):
                        plan = self.plan("--profile", f"{platform}-{role}", "--arch", architecture)
                        self.assertEqual(plan["platform"], platform)
                        self.assertEqual(plan["role"], role)
                        self.assertEqual(plan["arch"], architecture)
        self.assertFalse(self.home.exists())

    def test_detection_is_independent_of_ssh_and_explicit_flags_override_it(self):
        uname = self.guards / "uname"
        uname.write_text('#!/bin/sh\ncase "$1" in -s) echo Linux ;; -r) echo generic ;; -m) echo x86_64 ;; esac\n')
        uname.chmod(0o755)
        environment = dict(self.env, SSH_CONNECTION="synthetic", WSL_DISTRO_NAME="")
        environment.pop("WSL_INTEROP", None)
        self.assertEqual(self.plan(env=environment)["profile"], "linux-workstation")
        environment["WSL_DISTRO_NAME"] = "SyntheticLinux"
        self.assertEqual(self.plan(env=environment)["profile"], "wsl-workstation")
        self.assertEqual(self.plan("--platform", "linux", env=environment)["profile"], "linux-workstation")
        uname.write_text('#!/bin/sh\ncase "$1" in -s) echo SunOS ;; -m) echo x86_64 ;; esac\n')
        self.assertEqual(self.plan("--profile", "linux-workstation", env=environment)["profile"], "linux-workstation")


if __name__ == "__main__":
    unittest.main()
