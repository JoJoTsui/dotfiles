"""WSL profile behavior; Linux rendering is distinct from native WSL execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class WSLDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-wsl-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "linux-home"
        self.environment = {"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                            "USERPROFILE": r"C:\Users\WindowsDevice",
                            "APPDATA": r"C:\Users\WindowsDevice\AppData\Roaming"}
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")

    def deploy(self, *arguments, source=SOURCE, environment=None):
        return subprocess.run(["/bin/bash", str(source / "bootstrap.sh"), *arguments],
                              env=environment or self.environment, cwd=source,
                              capture_output=True, text=True, timeout=45)

    def test_wsl_application_keeps_ci_bookkeeping_out_of_linux_home(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        source = self.root / "working-source"
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        workflow = source / ".github/workflows/native-wsl.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text("name: temporary-ci-only-marker\n")
        result = self.deploy("--platform", "wsl", "--apply-only", source=source,
                             environment=dict(self.environment, DOTFILES_CHEZMOI_BIN=self.chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / ".github").exists(), "CI files must not deploy into the device home")

    def test_windows_checkout_keeps_unix_entry_points_and_raw_skill_bytes(self):
        repository = self.root / "repository"
        repository.mkdir()
        for name in (".gitattributes", "bootstrap.sh", "dot_profile",
                     "dot_local/bin/executable_nu-login",
                     "dot_config/nushell/config.nu",
                     "tests/native/wsl.ps1",
                     "deployment/agent-payload/skills/tdd/SKILL.md"):
            destination = repository / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, destination)
        for arguments in (["init", "--quiet"], ["add", "."],
                          ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                           "commit", "--quiet", "-m", "checkout fixture"]):
            subprocess.run(["git", *arguments], cwd=repository, env=self.environment,
                           check=True, capture_output=True)
        checkout = self.root / "windows-checkout"
        subprocess.run(["git", "clone", "--quiet", "--config", "core.autocrlf=true",
                        str(repository), str(checkout)], env=self.environment,
                       check=True, capture_output=True)
        for name in ("bootstrap.sh", "dot_profile", "dot_local/bin/executable_nu-login",
                     "dot_config/nushell/config.nu", "tests/native/wsl.ps1",
                     "deployment/agent-payload/skills/tdd/SKILL.md"):
            with self.subTest(file=name):
                self.assertEqual((checkout / name).read_bytes(), (SOURCE / name).read_bytes(),
                                 "Unix entry points and the raw library must survive a Windows checkout")

    def test_wsl_environment_selects_linux_defaults_and_explicit_choices_win(self):
        environment = dict(self.environment, WSL_DISTRO_NAME="Ubuntu-24.04",
                           WSL_INTEROP="/run/WSL/synthetic_interop", SSH_CONNECTION="synthetic ssh session")
        result = self.deploy("--plan", environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["profile"], "wsl-workstation")
        self.assertEqual(plan["home"], str(self.home))
        self.assertEqual(plan["roots"]["config"], str(self.home / ".config"))
        self.assertTrue({"nu", "bash", "zsh", "bun", "node", "atuin", "rtk", "zoxide",
                         "tspin", "codegraph"}.issubset(plan["tools"]))
        self.assertEqual(plan["agents"], ["kimi", "pi", "opencode", "claude", "codex"])
        self.assertFalse(plan["settings"]["systemChanges"])
        self.assertFalse(plan["settings"]["loginShellChanges"])
        overridden = self.deploy("--plan", "--platform", "linux", "--role", "remote-compute",
                                 environment=dict(environment, DOTFILES_PLATFORM="windows"))
        self.assertEqual(overridden.returncode, 0, overridden.stderr)
        self.assertEqual(json.loads(overridden.stdout)["profile"], "linux-remote-compute")
        self.assertFalse(self.home.exists())

    def test_wsl_kernel_detection_works_without_session_environment_markers(self):
        guards = self.root / "system-probe-fixture"
        guards.mkdir()
        uname = guards / "uname"
        uname.write_text('#!/bin/sh\ncase "$1" in -s) echo Linux ;; -r) echo 6.6.87.2-microsoft-standard-WSL2 ;; -m) echo aarch64 ;; esac\n')
        uname.chmod(0o755)
        result = self.deploy("--plan", "--role", "remote-compute",
                             environment=dict(self.environment, PATH=f"{guards}:/usr/bin:/bin"))
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["profile"], "wsl-remote-compute")
        self.assertEqual(plan["arch"], "aarch64")
        self.assertEqual(plan["home"], str(self.home))
        self.assertFalse(self.home.exists())

    def test_each_wsl_architecture_and_role_renders_portable_defaults_without_losing_device_state(self):
        if not self.chezmoi:
            self.skipTest("actual source application requires chezmoi")
        for architecture in ("x86_64", "aarch64"):
            for role in ("workstation", "remote-compute"):
                with self.subTest(architecture=architecture, role=role):
                    self.home = self.root / f"{architecture}-{role}"
                    auth = self.home / ".codex/auth.json"
                    history = self.home / ".local/share/atuin/local-state-marker"
                    registry = self.home / ".bun/install/global/package.json"
                    for path in (auth, history, registry):
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("synthetic-device-state\n")
                    for attempt in range(2):
                        result = self.deploy("--home", str(self.home), "--profile", f"wsl-{role}",
                                             "--arch", architecture, "--apply-only",
                                             environment=dict(self.environment, DOTFILES_CHEZMOI_BIN=self.chezmoi))
                        self.assertEqual(result.returncode, 0, result.stderr)
                        profile = json.loads((self.home / ".config/dotfiles/profile.json").read_text())
                        self.assertEqual(profile["platform"], "wsl")
                        self.assertEqual(profile["role"], role)
                        self.assertEqual(profile["arch"], architecture)
                        env = (self.home / ".env_core").read_text()
                        self.assertIn('EDITOR:=hx', env)
                        self.assertNotIn("WindowsDevice", env)
                        self.assertTrue((self.home / ".local/bin/nu-login").is_file())
                        for name in (".agents/skills/tdd/SKILL.md", ".claude/skills/tdd/SKILL.md",
                                     ".claude/CLAUDE.md", ".codex/AGENTS.md",
                                     ".config/atuin/config.toml", ".config/uv/uv.toml"):
                            self.assertTrue((self.home / name).is_file(), name)
                            self.assertFalse((self.home / name).is_symlink(), name)
                        for name in (".claude.json", ".codex/config.toml", ".kimi-code/mcp.json",
                                     ".config/opencode/opencode.jsonc"):
                            self.assertIn("codegraph", (self.home / name).read_text())
                        self.assertEqual((self.home / ".vscode-server/data/Machine/settings.json").exists(),
                                         role == "remote-compute")
                        for path in (auth, history, registry):
                            self.assertEqual(path.read_text(), "synthetic-device-state\n")

    def test_native_nu_probe_loads_ordinary_env_config_and_vendor_startup(self):
        tool_home = os.environ.get("DOTFILES_TEST_TOOL_HOME")
        if not self.chezmoi or not tool_home:
            self.skipTest("ordinary Nu startup requires chezmoi and pinned isolated tools")
        for role in ("workstation", "remote-compute"):
            with self.subTest(role=role):
                self.home = self.root / role
                environment = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color"}
                result = self.deploy("--home", str(self.home), "--profile", f"wsl-{role}", "--apply-only",
                                     environment=dict(environment, DOTFILES_CHEZMOI_BIN=self.chezmoi))
                self.assertEqual(result.returncode, 0, result.stderr)
                tools = self.home / ".pixi/bin"
                tools.mkdir(parents=True, exist_ok=True)
                for binary in (Path(tool_home) / ".pixi/bin").iterdir():
                    if binary.is_file():
                        (tools / binary.name).symlink_to(binary)
                for command in ("dotfiles-shell-prepare", "dotfiles-history-prepare"):
                    prepared = subprocess.run([str(self.home / ".local/bin" / command)], env=environment,
                                              cwd=self.home, capture_output=True, text=True, timeout=30)
                    self.assertEqual(prepared.returncode, 0, prepared.stderr)
                report = self.root / f"nu-startup-{role}.json"
                probe = subprocess.run(["python3", str(SOURCE / "tests/native/wsl.py"), "--probe-nu",
                                        "--home", str(self.home), "--role", role, "--report", str(report)],
                                       env=environment, cwd=self.home, capture_output=True, text=True, timeout=30)
                self.assertEqual(probe.returncode, 0, probe.stderr)
                observed = json.loads(report.read_text())
                self.assertFalse(observed["nativePass"], "a Linux configuration probe cannot claim WSL2 native acceptance")
                startup = observed["checks"][0]["details"]
                self.assertEqual(startup["editor"], "hx")
                self.assertEqual(startup["polling"], "1" if role == "remote-compute" else "0")
                self.assertEqual(startup["prompt"], "nu")
                self.assertEqual(startup["logs"], 1)
                self.assertEqual(startup["zoxide"], 1)
                self.assertGreater(startup["historyHooks"], 0)


class WSLNativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-wsl-native-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pwsh = os.environ.get("DOTFILES_TEST_PWSH") or shutil.which("pwsh")

    def test_disposable_distro_plan_pins_rootfs_and_never_provisions(self):
        if not self.pwsh:
            self.skipTest("PowerShell parser/planning check requires DOTFILES_TEST_PWSH")
        target = self.root / "runner-temp"
        result = subprocess.run([self.pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                                 str(SOURCE / "tests/native/wsl.ps1"), "-Plan", "-RunnerTemp", str(target),
                                 "-Source", str(SOURCE), "-Role", "remote-compute", "-Architecture", "aarch64"],
                                env={"HOME": str(self.root), "PATH": "/usr/bin:/bin"},
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["platform"], "wsl")
        self.assertEqual(plan["role"], "remote-compute")
        self.assertEqual(plan["architecture"], "aarch64")
        self.assertEqual(plan["wslGeneration"], 2)
        self.assertEqual(plan["rootfs"]["sha256"], "74478b5024d9047397ba79d17c27f73caf85ada4988f88cffc2892d65e6a806b")
        self.assertFalse(plan["nativePass"])
        self.assertIn("self-hosted", plan["coverage"])
        self.assertFalse(target.exists(), "planning must not create a distro, report, or manager roots")

    def test_provisioning_refuses_an_ordinary_linux_host_without_creating_state(self):
        if not self.pwsh or os.name != "posix":
            self.skipTest("the non-Windows refusal check requires Linux PowerShell")
        target = self.root / "runner-temp"
        result = subprocess.run([self.pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                                 str(SOURCE / "tests/native/wsl.ps1"), "-Provision", "-RunnerTemp", str(target),
                                 "-Source", str(SOURCE)],
                                env={"HOME": str(self.root), "PATH": "/usr/bin:/bin"},
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("native Windows", result.stderr)
        self.assertFalse(target.exists(), "a Linux runtime must not begin WSL provisioning")

    def test_native_gate_reports_linux_as_unavailable_before_bootstrap(self):
        if os.name != "posix" or "microsoft" in os.uname().release.lower():
            self.skipTest("this check demonstrates that ordinary Linux cannot establish a WSL pass")
        home = self.root / "validation-home"
        report = self.root / "native-wsl.json"
        result = subprocess.run(["python3", str(SOURCE / "tests/native/wsl.py"), "--verify",
                                 "--home", str(home), "--report", str(report)],
                                env={"HOME": str(self.root), "PATH": "/usr/bin:/bin"},
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WSL2", result.stderr)
        evidence = json.loads(report.read_text())
        self.assertFalse(evidence["nativePass"])
        self.assertEqual(evidence["phase"], "native-preflight")
        self.assertFalse(home.exists(), "a simulated Linux run must stop before package installation")


if __name__ == "__main__":
    unittest.main()
