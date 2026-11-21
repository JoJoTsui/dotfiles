"""WSL profile behavior; Linux rendering is distinct from native WSL execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from fixtures.skills import STATIC_LIBRARY, assert_skill_copies

SOURCE = Path(__file__).resolve().parents[1]
CATALOG = "deployment/agents/providers.tsv"


def catalog_records(source=SOURCE):
    """The provider catalog rows the deployment reads, in catalog order."""
    records = []
    for line in (source / CATALOG).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        records.append(line.split("|"))
    return records


def platform_serves(platforms, platform):
    """Whether a catalog record can serve a platform.

    It mirrors the platform match of the deployment, so the fixture names the
    providers a platform resolves and no other.
    """
    fields = platforms.split(",")
    if "all" in fields:
        return True
    if "unix" in fields and platform != "windows":
        return True
    return platform in fields


def catalog_agents(platform, source=SOURCE):
    """The catalog agents of a platform in dispatch order.

    Every entry names the agent, its selection mode, and whether one of its
    records can serve the platform. The deployment rejects a catalog whose
    agent cannot serve the deployment platform, so a served agent is the one
    the plan can install.
    """
    order = []
    index = {}
    for record in catalog_records(source):
        name = record[0]
        if name not in index:
            order.append(name)
            index[name] = {"mode": record[9], "serves": False}
        if platform_serves(record[7], platform):
            index[name]["serves"] = True
    return [(name, index[name]["mode"], index[name]["serves"]) for name in order]


def catalog_default_agents(platform, source=SOURCE):
    """The ordered default agent selection of a platform.

    The catalog order is the installation and the plan order. An agent the
    deployment always installs is not part of the selectable default.
    """
    return [name for name, mode, serves in catalog_agents(platform, source)
            if mode == "selectable" and serves]


def catalog_dispatched_agents(platform, source=SOURCE):
    """The ordered agent packages a platform dispatches, always-installed ones included."""
    return [name for name, mode, serves in catalog_agents(platform, source) if serves]


class WSLDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-wsl-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "linux-home"
        self.environment = {"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                            "USERPROFILE": r"C:\Users\WindowsDevice",
                            "APPDATA": r"C:\Users\WindowsDevice\AppData\Roaming",
                            "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library")}
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")

    def deploy(self, *arguments, source=SOURCE, environment=None):
        return subprocess.run(["/bin/bash", str(source / "bootstrap.sh"), *arguments],
                              env=environment or self.environment, cwd=source,
                              capture_output=True, text=True, timeout=45)

    def linux_uname_fixture(self, name="system-probe-fixture", machine="x86_64",
                            release="generic"):
        """A bounded uname fixture so the detection does not depend on the host.

        The deployment reads the operating system and the architecture from
        uname, so the fixture answers those three probes and nothing else.
        """
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        uname = directory / "uname"
        uname.write_text(f'#!/bin/sh\ncase "$1" in -s) echo Linux ;; -r) echo {release} ;; '
                         f'-m) echo {machine} ;; esac\n')
        uname.chmod(0o755)
        return directory

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
                     "tests/fixtures/skill-library/tdd/SKILL.md"):
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
                     "tests/fixtures/skill-library/tdd/SKILL.md"):
            with self.subTest(file=name):
                self.assertEqual((checkout / name).read_bytes(), (SOURCE / name).read_bytes(),
                                 "Unix entry points and the raw library must survive a Windows checkout")

    def test_wsl_environment_selects_linux_defaults_and_explicit_choices_win(self):
        guards = self.linux_uname_fixture("wsl-session-uname", machine="x86_64")
        environment = dict(self.environment, PATH=f"{guards}:/usr/bin:/bin",
                           WSL_DISTRO_NAME="Ubuntu-24.04",
                           WSL_INTEROP="/run/WSL/synthetic_interop",
                           SSH_CONNECTION="synthetic ssh session")
        result = self.deploy("--plan", environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["profile"], "wsl-workstation")
        self.assertEqual(plan["platform"], "wsl")
        self.assertEqual(plan["arch"], "x86_64")
        self.assertEqual(plan["home"], str(self.home))
        self.assertEqual(plan["roots"]["config"], str(self.home / ".config"))
        self.assertTrue({"nu", "bash", "zsh", "bun", "node", "atuin", "rtk", "zoxide",
                         "tspin", "codegraph"}.issubset(plan["tools"]))
        # The default selection follows the catalog instead of a frozen list.
        self.assertEqual(plan["agents"], catalog_default_agents("wsl"))
        self.assertEqual([entry["name"] for entry in plan["agentPackages"]],
                         catalog_dispatched_agents("wsl"))
        # WSL has no installer-owned provider; Homebrew serves macOS alone.
        for entry in plan["agentPackages"]:
            self.assertNotEqual(entry["provider"], "homebrew")
        self.assertFalse(plan["settings"]["systemChanges"])
        self.assertFalse(plan["settings"]["loginShellChanges"])
        overridden = self.deploy("--plan", "--platform", "linux", "--role", "remote-compute",
                                 environment=dict(environment, DOTFILES_PLATFORM="windows"))
        self.assertEqual(overridden.returncode, 0, overridden.stderr)
        linux = json.loads(overridden.stdout)
        self.assertEqual(linux["profile"], "linux-remote-compute")
        self.assertEqual(linux["agents"], catalog_default_agents("linux"))
        explicit = self.deploy("--plan", "--platform", "wsl", "--role", "workstation",
                               environment=dict(environment, DOTFILES_PLATFORM="linux"))
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        wsl = json.loads(explicit.stdout)
        self.assertEqual(wsl["profile"], "wsl-workstation")
        self.assertEqual(wsl["agents"], catalog_default_agents("wsl"))
        self.assertFalse(self.home.exists())

    def test_wsl_kernel_detection_works_without_session_environment_markers(self):
        guards = self.linux_uname_fixture(machine="aarch64",
                                           release="6.6.87.2-microsoft-standard-WSL2")
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
                        assert_skill_copies(self, self.home, STATIC_LIBRARY,
                                            ("show-me/SKILL.md", "show-me/agents/openai.yaml"))
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
                environment = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color",
                               "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library")}
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
                probe = subprocess.run([sys.executable, str(SOURCE / "tests/native/wsl.py"), "--probe-nu",
                                        "--home", str(self.home), "--role", role, "--report", str(report)],
                                       env=environment, cwd=self.home, capture_output=True, text=True, timeout=30)
                self.assertEqual(probe.returncode, 0, probe.stderr)
                observed = json.loads(report.read_text())
                self.assertFalse(observed["nativePass"], "a Linux configuration probe cannot claim WSL2 native acceptance")
                self.assertFalse(observed["acceptance"], "a configuration probe is not native acceptance")
                startup = observed["scenarios"][0]["details"]
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
        result = subprocess.run([sys.executable, str(SOURCE / "tests/native/wsl.py"), "--verify",
                                 "--home", str(home), "--report", str(report)],
                                env={"HOME": str(self.root), "PATH": "/usr/bin:/bin"},
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WSL2", result.stderr)
        evidence = json.loads(report.read_text())
        self.assertFalse(evidence["nativePass"])
        self.assertEqual(evidence["phase"], "native-preflight")
        self.assertEqual(evidence["status"], "unavailable")
        self.assertFalse(evidence["acceptance"],
                         "an ordinary Linux host cannot establish WSL2 acceptance")
        self.assertEqual(evidence["scenarios"][0]["outcome"], "unavailable")
        self.assertIn("WSL2", evidence["scenarios"][0]["reason"])
        self.assertFalse(home.exists(), "a simulated Linux run must stop before package installation")

    def test_the_native_gate_names_the_source_revision_it_verified(self):
        if os.name != "posix" or "microsoft" in os.uname().release.lower():
            self.skipTest("this check demonstrates that ordinary Linux cannot establish a WSL pass")
        home = self.root / "validation-home"
        report = self.root / "native-wsl.json"
        result = subprocess.run([sys.executable, str(SOURCE / "tests/native/wsl.py"), "--verify",
                                 "--home", str(home), "--report", str(report)],
                                env={"HOME": str(self.root), "PATH": "/usr/bin:/bin"},
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        evidence = json.loads(report.read_text())
        revision = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"],
                                           text=True).strip()
        self.assertEqual(evidence["commit"], revision,
                         "the report has to name the revision of the source it verified")
        self.assertEqual(evidence["checkout"]["commit"], revision)
        self.assertEqual(evidence["checkout"]["revision_status"], "verified")

    def test_a_failed_probe_names_the_exact_scenario(self):
        home = self.root / "probe-home"
        (home / ".config/dotfiles").mkdir(parents=True)
        (home / ".pixi/bin").mkdir(parents=True)
        (home / ".config/dotfiles/profile.json").write_text(
            json.dumps({"platform": "wsl", "role": "workstation"}))
        nu = home / ".pixi/bin/nu"
        nu.write_text("#!/bin/sh\necho 'not the managed startup state'\n")
        nu.chmod(0o755)
        report = self.root / "probe-report.json"
        result = subprocess.run([sys.executable, str(SOURCE / "tests/native/wsl.py"), "--probe-nu",
                                 "--home", str(home), "--role", "workstation", "--report", str(report)],
                                env={"HOME": str(self.root), "PATH": "/usr/bin:/bin"},
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        evidence = json.loads(report.read_text())
        outcomes = {record["name"]: record for record in evidence["scenarios"]}
        self.assertIn("ordinary Nu env/config/vendor startup", outcomes)
        self.assertEqual(outcomes["ordinary Nu env/config/vendor startup"]["outcome"], "failed")
        self.assertEqual(evidence["failed_scenario"], "ordinary Nu env/config/vendor startup")


if __name__ == "__main__":
    unittest.main()
