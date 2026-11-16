"""Device-owned version overrides for agents, tools, and installer commands.

The repository catalogs keep owning the default version of every managed
component. A device may own a different version of the components it runs.
These checks cover the override contract: the plan reports the effective
versions, an invalid override is rejected before any state is created, the
catalog pins follow the override, and the registry merge installs the
overridden tool version.
"""
import json
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
MERGE = SOURCE / "deployment/merge_pixi.py"


@unittest.skipUnless(os.name == "posix", "Unix plans; native Windows has a separate boundary suite")
class OverridePlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-override-plan-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        (self.home / ".config/dotfiles").mkdir(parents=True)
        self.env = {key: value for value in [os.environ] for key, value in value.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "BUN_", "PIXI_", "UV_", "NPM_",
                                           "ATUIN_", "CARGO_", "RUSTUP_", "KIMI_", "PI_", "OPENCODE_",
                                           "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                    "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN",
                                    "CONTEXT7_TOKEN")}
        self.env.update(HOME=str(self.root / "original"), PATH="/usr/bin:/bin")

    def overrides(self, text):
        (self.home / ".config/dotfiles/versions.tsv").write_text(text, encoding="utf-8")

    def deploy(self, *arguments):
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--home", str(self.home), "--platform", "linux", "--arch", "x86_64",
                               *arguments],
                              cwd=SOURCE, env=self.env, capture_output=True, text=True, timeout=30)

    def test_plan_reports_the_override_and_the_effective_versions(self):
        self.overrides("# device owned versions\nagent|pi|1.5.3\ntool|ruff|0.18.0\n")
        result = self.deploy("--plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["overrides"], [
            {"kind": "agent", "name": "pi", "version": "1.5.3", "default": "1.5.2"},
            {"kind": "tool", "name": "ruff", "version": "0.18.0", "default": "0.17.3"},
        ])
        agents = {item["name"]: item for item in plan["agentPackages"]}
        self.assertEqual(agents["pi"]["version"], "1.5.3")
        self.assertEqual(agents["codex"]["version"], "0.166.0")
        packages = {item["environment"]: item for item in plan["packages"]}
        self.assertEqual(packages["ruff"]["dependencies"], {"ruff": "==0.18.0"})
        self.assertEqual(packages["git"]["dependencies"], {"git": "==2.56.0"})

    def test_plan_reports_the_installer_floor_override(self):
        self.overrides("cli|gh|2.104.0\n")
        result = self.deploy("--plan", "--platform", "macos")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["overrides"], [
            {"kind": "cli", "name": "gh", "version": "2.104.0", "default": "2.103.3"},
        ])
        floors = {item["name"]: item["minimum"] for item in plan["installerTools"]}
        self.assertEqual(floors["gh"], "2.104.0")
        self.assertEqual(floors["git"], "2.56.0")

    def test_invalid_overrides_are_rejected_before_state_creation(self):
        cases = (
            ("agent|unknown-agent|1.0.0\n", "unknown agent"),
            ("tool|unknown-tool|1.0.0\n", "unknown tool"),
            ("cli|unknown-cli|1.0.0\n", "unknown installer tool"),
            ("plugin|pi|1.0.0\n", "unknown version override kind"),
            ("agent|pi\n", "expected kind|name|version"),
            ("agent|pi|1.0.0|extra\n", "expected kind|name|version"),
            ("agent|pi|1.0.0\nagent|pi|1.0.1\n", "duplicate version override"),
            ("agent|pi|not a version\n", "invalid version override version"),
            ("tool|atuin|18.25.0\n", "Atuin version stays with the repository pin"),
            ("cli|atuin|18.25.0\n", "Atuin version stays with the repository pin"),
        )
        for text, message in cases:
            with self.subTest(override=text.strip()):
                self.overrides(text)
                result = self.deploy("--plan")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse((self.home / ".local").exists())
                self.assertFalse((self.home / ".bun").exists())
                self.assertFalse((self.home / ".pixi").exists())

    def test_a_symlinked_override_file_is_rejected(self):
        outside = self.root / "outside.tsv"
        outside.write_text("agent|pi|1.5.3\n", encoding="utf-8")
        try:
            (self.home / ".config/dotfiles/versions.tsv").symlink_to(outside)
        except OSError:
            self.skipTest("platform policy prevents creating symlinks")
        result = self.deploy("--plan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version override file is a symlink", result.stderr)


@unittest.skipUnless(os.name == "posix", "POSIX installer boundary")
class OverrideResolutionTests(unittest.TestCase):
    """The catalog pins follow the device override inside the deployment."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-override-resolve-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        (self.home / ".config/dotfiles").mkdir(parents=True)
        (self.home / ".config/dotfiles/versions.tsv").write_text(
            "agent|pi|1.5.3\ntool|ruff|0.18.0\ncli|gh|2.104.0\n", encoding="utf-8")

    def resolve(self, body):
        script = self.root / "run.sh"
        script.write_text(
            "set -euo pipefail\n"
            f"DEPLOY_SOURCE='{SOURCE}'\nDEPLOY_PLATFORM=macos\n"
            f"DEPLOY_HOME='{self.home}'\nexport HOME='{self.home}'\n"
            f"export XDG_STATE_HOME='{self.home / '.local/state'}'\n"
            "DEPLOY_TOOLS=()\nDEPLOY_AGENTS=()\nCLI_AGENTS=all\nCLI_AGENTS_SET=false\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            "json_string() { printf '\"%s\"' \"$1\"; }\n"
            "bundle_selected() { return 1; }\n"
            f"source '{SOURCE}/deployment/overrides.sh'\n"
            f"source '{SOURCE}/deployment/common.sh'\n"
            f"source '{SOURCE}/deployment/installer.sh'\n"
            f"source '{SOURCE}/deployment/agents.sh'\n" + body + "\n")
        return subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, timeout=30)

    def test_catalog_pins_follow_the_device_override(self):
        result = self.resolve(
            "printf 'agent=%s\\n' \"$(agent_effective_version pi 1.5.2)\"\n"
            "printf 'tool=%s\\n' \"$(common_package_pin ruff)\"\n"
            "printf 'floor=%s\\n' \"$(installer_common_minimum gh)\"\n"
            "printf 'runtime=%s\\n' \"$(agent_runtime_pin nodejs)\"\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "agent=1.5.3\ntool=0.18.0\nfloor=2.104.0\nruntime=26.12.1\n")

    def test_without_an_override_the_catalog_pins_remain(self):
        (self.home / ".config/dotfiles/versions.tsv").unlink()
        result = self.resolve(
            "printf 'agent=%s\\n' \"$(agent_effective_version pi 1.5.2)\"\n"
            "printf 'tool=%s\\n' \"$(common_package_pin ruff)\"\n"
            "printf 'floor=%s\\n' \"$(installer_common_minimum gh)\"\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "agent=1.5.2\ntool=0.17.3\nfloor=2.103.3\n")


@unittest.skipUnless(tomllib, "registry assertions require Python 3.11 or newer")
class OverrideRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-override-registry-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.desired = self.root / "desired.toml"
        self.desired.write_text('''version = 1
[envs.ruff]
channels = ["conda-forge"]
dependencies = { ruff = "==0.17.3" }
exposed = { ruff = "ruff" }
[envs.git]
dependencies = { git = "==2.56.0" }
exposed = { git = "git" }
''', encoding="utf-8")
        self.overrides = self.root / "overrides.json"
        self.registry = self.root / "pixi-global.toml"

    def merge(self, overrides=None):
        arguments = [sys.executable, str(MERGE)]
        if overrides is not None:
            arguments += ["--overrides", str(overrides)]
        arguments += [str(self.desired), str(self.registry)]
        return subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=15)

    def read(self):
        return tomllib.loads(self.registry.read_text())["envs"]

    def test_the_registry_installs_the_overridden_tool_version(self):
        self.overrides.write_text('{"agents":{},"tools":{"ruff":"0.18.0"},"clis":{}}\n', encoding="utf-8")
        result = self.merge(self.overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        environments = self.read()
        self.assertEqual(environments["ruff"]["dependencies"], {"ruff": "==0.18.0"})
        self.assertEqual(environments["git"]["dependencies"], {"git": "==2.56.0"})

    def test_removing_the_override_restores_the_catalog_pin(self):
        self.overrides.write_text('{"agents":{},"tools":{"ruff":"0.18.0"},"clis":{}}\n', encoding="utf-8")
        self.assertEqual(self.merge(self.overrides).returncode, 0)
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.read()["ruff"]["dependencies"], {"ruff": "==0.17.3"})

    def test_an_unknown_merge_option_is_rejected(self):
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = [sys.executable, str(MERGE), "--unknown", str(self.desired), str(self.registry)]
        result = subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown merge option", result.stderr)


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_AGENT_INSTALL") == "1",
                     "explicit network agent installation check")
class OverrideAgentInstallTests(unittest.TestCase):
    """A device override installs the declared agent version."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-override-install-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "home"
        (self.home / ".config/dotfiles").mkdir(parents=True)

    def test_the_declared_agent_version_is_installed(self):
        pins = {}
        catalog = (SOURCE / "deployment/agents/providers.tsv").read_text(encoding="utf-8")
        for line in catalog.splitlines():
            fields = line.split("|")
            if fields[0] == "pi" and fields[1] == "bun":
                pins = {"package": fields[2], "default": fields[3]}
        other = self.published_version(pins["package"], pins["default"])
        (self.home / ".config/dotfiles/versions.tsv").write_text(f"agent|pi|{other}\n", encoding="utf-8")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("DOTFILES_", "XDG_", "BUN_", "PIXI_", "UV_", "NPM_", "ATUIN_",
                                      "CARGO_", "RUSTUP_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
               and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                               "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN",
                               "CONTEXT7_TOKEN")}
        env.update(HOME=str(self.home), PATH="/usr/bin:/bin",
                   DOTFILES_CHEZMOI_BIN=os.environ["DOTFILES_TEST_CHEZMOI"],
                   DOTFILES_BUN_BIN=os.environ["DOTFILES_TEST_BUN"],
                   DOTFILES_NODE_BIN=os.environ["DOTFILES_TEST_NODE"])
        result = subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(self.home),
                                 "--platform", "macos", "--arch", "aarch64", "--agents-only",
                                 "--agents", "pi"],
                                cwd=SOURCE, env=env, capture_output=True, text=True, timeout=1800)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = json.loads((self.home / ".bun/managed/pi/node_modules" / pins["package"]
                                / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["version"], other)

    def published_version(self, package, default):
        """A published version of the package that differs from the pin."""
        from urllib.request import urlopen
        url = "https://registry.npmjs.org/" + package.replace("/", "%2f")
        with urlopen(url, timeout=30) as response:
            metadata = json.loads(response.read())
        candidates = [version for version in metadata.get("versions", {})
                      if version != default and all(part.isdigit() for part in version.split("."))]
        self.assertTrue(candidates, "the registry publishes no alternative version")
        return sorted(candidates, key=lambda value: [int(part) for part in value.split(".")])[-1]


if __name__ == "__main__":
    unittest.main()
