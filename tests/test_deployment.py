"""Deployment acceptance checks; all writes stay in disposable environments."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from pins import common_pin, manager_pin

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
        self.env["DOTFILES_SKILLS_DIR"] = str(SOURCE / "tests/fixtures/skill-library")
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

    def test_common_plan_names_default_tools_and_exact_package_owners(self):
        plan = self.plan("--platform", "linux")
        for command in ("pixi", "uv", "bun", "node", "nu", "bash", "zsh",
                        "rtk", "atuin", "zoxide", "tspin", "less", "rustup"):
            self.assertIn(command, plan["tools"])
        packages = {item["environment"]: item for item in plan["packages"]}
        self.assertEqual(packages["rtk-cli"]["dependencies"], {"rtk-cli": "==" + common_pin("rtk-cli")})
        self.assertEqual(packages["tailspin"]["exposed"], {"tspin": "tspin"})
        self.assertEqual(packages["nodejs"]["dependencies"], {"nodejs": "==" + common_pin("nodejs")})
        self.assertEqual(packages["python"]["dependencies"], {"python": "==" + common_pin("python"), "pip": "==" + common_pin("pip")})
        self.assertNotIn("codex", packages)
        for specialist in ("samtools", "nvtop", "zed", "firefox"):
            self.assertNotIn(specialist, packages)
        self.assertFalse(self.home.exists())

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

    def test_wsl_apply_handles_crlf_deployment_catalogs(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi; set DOTFILES_TEST_CHEZMOI to an isolated binary")
        source = self.root / "crlf-source"
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        for catalog in (source / "deployment").rglob("*.tsv"):
            original = catalog.read_bytes().replace(b"\r\n", b"\n")
            catalog.write_bytes(original.replace(b"\n", b"\r\n"))
        self.home = self.root / "crlf-device"
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi)
        arguments = ("--source", str(source), "--platform", "wsl", "--role", "workstation")
        plan_result = self.deploy("--plan", *arguments, env=environment)
        self.assertEqual(plan_result.returncode, 0, plan_result.stderr)
        plan = json.loads(plan_result.stdout)
        self.assertEqual(plan["profile"], "wsl-workstation")
        self.assertTrue(all("\r" not in value for package in plan["packages"]
                            for value in package["dependencies"].values()))
        result = self.deploy("--apply-only", *arguments, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / ".agents/skills/tdd/SKILL.md").is_file())
        self.assertTrue((self.home / ".claude/skills/implement-spec/SKILL.md").is_file())
        self.assertTrue((self.home / ".claude.json").is_file())
        profile = json.loads((self.home / ".config/dotfiles/profile.json").read_text())
        self.assertEqual((profile["platform"], profile["role"]), ("wsl", "workstation"))

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

    def test_plan_reports_explicit_system_and_login_shell_actions_without_running_them(self):
        plan = self.plan("--platform", "linux", "--system-config", "--login-shell")
        self.assertTrue(plan["settings"]["systemChanges"])
        self.assertTrue(plan["settings"]["loginShellChanges"])
        self.assertEqual(plan["actions"][-2:], ["configure-system", "set-login-shell"])
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.original_home.iterdir()), [])

    def test_privileged_options_reject_a_simulated_home_before_writing(self):
        result = self.deploy("--platform", "linux", "--system-config", "--login-shell")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot target a simulated or different home", result.stderr)
        self.assertNotIn("forbidden external command", result.stderr)
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.original_home.iterdir()), [])

    def test_privileged_options_are_rejected_for_native_windows_plans(self):
        result = self.deploy("--plan", "--platform", "windows", "--system-config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unavailable on native Windows", result.stderr)
        self.assertFalse(self.home.exists())

    def test_login_shell_opt_in_requires_normal_shell_preparation(self):
        result = self.deploy("--plan", "--apply-only", "--login-shell")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires a full deployment with shell preparation", result.stderr)
        self.assertFalse(self.home.exists())

    def test_apply_renders_owned_manifest_without_replacing_local_registries(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi")
        registry = self.home / ".pixi/manifests/pixi-global.toml"
        registry.parent.mkdir(parents=True)
        existing = 'version = 1\n[envs.my-tool]\nchannels = ["conda-forge"]\ndependencies = { my-tool = "==1.0.0" }\n'
        registry.write_text(existing)
        bun_registry = self.home / ".bun/install/global/package.json"
        bun_registry.parent.mkdir(parents=True)
        bun_registry.write_text('{"dependencies":{"my-agent":"1.0.0"}}\n')
        result = self.deploy("--apply-only", "--platform", "linux",
                             env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(registry.read_text(), existing)
        self.assertEqual(json.loads(bun_registry.read_text())["dependencies"], {"my-agent": "1.0.0"})
        desired = (self.home / ".config/dotfiles/pixi-global.toml").read_text()
        self.assertIn('[envs."rtk-cli"]', desired)
        self.assertIn('"rtk-cli" = "==' + common_pin("rtk-cli") + '"', desired)
        self.assertIn('"tspin" = "tspin"', desired)
        self.assertIn('"pip" = "==' + common_pin("pip") + '"', desired)
        self.assertNotIn('[envs."codex"]', desired)
        for specialist in ("samtools", "nvtop", "zed", "firefox"):
            self.assertNotIn(f'[envs."{specialist}"]', desired)

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

    def test_required_pixi_sync_failure_is_named_and_returns_failure(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("actual apply requires chezmoi")
        pixi = self.guards / "pixi"
        pixi.write_text('#!/bin/sh\ncase "$1 $2" in "--version ") echo "pixi ' + manager_pin("PIXI_VERSION") + '" ;; "exec "*) exit 0 ;; "global sync") exit 37 ;; *) exit 95 ;; esac\n')
        pixi.chmod(0o755)
        result = self.deploy("--platform", "linux", env=dict(self.env,
                             DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_PIXI_BIN=str(pixi)))
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertIn("step install-common.pixi-sync failed (exit 37)", result.stderr)
        self.assertNotIn("applied", result.stdout)

    def test_unverified_manager_download_fails_before_execution_or_apply(self):
        downloader = self.guards / "curl"
        downloader.write_text('#!/bin/sh\nwhile [ "$#" -gt 0 ]; do if [ "$1" = -o ]; then shift; printf "corrupt archive\\n" > "$1"; exit 0; fi; shift; done\nexit 94\n')
        downloader.chmod(0o755)
        result = self.deploy("--platform", "linux")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertIn("step install-managers.pixi failed (exit 1)", result.stderr)
        self.assertFalse((self.home / ".env_core").exists())
        self.assertFalse((self.home / ".pixi/bin/pixi").exists())
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
