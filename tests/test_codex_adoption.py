"""Exact native macOS Codex adoption with real agent installer functions."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from pins import agent_pins, common_pin


SOURCE = Path(__file__).resolve().parents[1]


class CodexAdoptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-codex-adoption-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.tools = self.root / "device tools"
        self.tools.mkdir()
        for relative in (".local/bin", ".bun/bin", ".pixi/bin"):
            (self.home / relative).mkdir(parents=True)
        self.log = self.root / "events.jsonl"
        self.pin = agent_pins()["codex"]["version"]
        self.codex = self.tools / "codex"
        self.write_codex()
        self.write_tool(self.tools / "node", "#!/bin/sh\necho v" + common_pin("nodejs") + "\n")
        self.write_tool(self.tools / "bun", "#!" + sys.executable + "\n" +
                        "import json, os, pathlib, sys\n" +
                        f"pins = {agent_pins()!r}\n" +
                        "if sys.argv[1:] == ['--version']:\n" +
                        f"    print({common_pin('bun')!r}); raise SystemExit\n" +
                        "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n" +
                        "with open(os.environ['ADOPTION_LOG'], 'a') as log:\n" +
                        "    log.write(json.dumps(['bun', project.name, *sys.argv[1:]]) + '\\n')\n" +
                        "for command in pins[project.name]['commands'].split(','):\n" +
                        "    target = project / 'node_modules/.bin' / command\n" +
                        "    target.parent.mkdir(parents=True, exist_ok=True)\n" +
                        "    version = pins[project.name]['version']\n" +
                        "    target.write_text('#!/bin/sh\\necho ' + version + '\\n')\n" +
                        "    target.chmod(0o755)\n")
        self.write_tool(self.home / ".local/bin/wt", "#!" + sys.executable + "\n" +
                        "import json, os, sys\n" +
                        "with open(os.environ['ADOPTION_LOG'], 'a') as log:\n" +
                        "    log.write(json.dumps(['wt', *sys.argv[1:]]) + '\\n')\n")
        self.originals = {}
        for relative in (".codex/auth.json", ".bun/install/global/package.json",
                         ".bun/managed/device-extra/package.json", "project/keep.txt"):
            target = self.home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("device-owned sentinel\n")
            self.originals[target] = target.read_bytes()

    def write_tool(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def write_codex(self, diagnostic=None, status=0, path=None):
        diagnostic = diagnostic if diagnostic is not None else "codex-cli " + self.pin
        self.write_tool(path or self.codex, "#!" + sys.executable + "\n" +
                        "import json, os, sys\n" +
                        "with open(os.environ['ADOPTION_LOG'], 'a') as log:\n" +
                        "    log.write(json.dumps(['device-codex', *sys.argv[1:]]) + '\\n')\n" +
                        f"print({diagnostic!r})\nraise SystemExit({status})\n")

    def events(self, kind):
        if not self.log.exists():
            return []
        return [event for line in self.log.read_text().splitlines()
                if (event := json.loads(line))[0] == kind]

    def install(self, *, platform="macos", native_platform="macos", arch="aarch64",
                native_arch="arm64", selection="codex", extra_path=()):
        environment = {"HOME": str(self.home), "BUN_INSTALL": str(self.home / ".bun"),
                       "PIXI_HOME": str(self.home / ".pixi"), "ADOPTION_LOG": str(self.log),
                       "PATH": os.pathsep.join(map(str, (self.home / ".local/bin", self.home / ".bun/bin",
                                                        *extra_path, self.tools, "/usr/bin", "/bin"))),
                       "DOTFILES_COMMON_BIN": str(self.home / ".local/bin"),
                       "DOTFILES_BUN_BIN": str(self.tools / "bun"),
                       "DOTFILES_NODE_BIN": str(self.tools / "node")}
        script = "\n".join((
            "set -euo pipefail",
            "DEPLOY_SOURCE=" + shlex.quote(str(SOURCE)),
            "DEPLOY_PLATFORM=" + shlex.quote(platform),
            "DEPLOY_ARCH=" + shlex.quote(arch),
            "DEPLOY_TOOLS=()",
            "CLI_AGENTS_SET=true",
            "CLI_AGENTS=" + shlex.quote(selection),
            "detect_platform() { printf '%s' " + shlex.quote(native_platform) + "; }",
            "uname() { printf '%s' " + shlex.quote(native_arch) + "; }",
            "fail() { printf '%s\\n' \"$*\" >&2; exit 1; }",
            'source "$DEPLOY_SOURCE/deployment/installer.sh"',
            'source "$DEPLOY_SOURCE/deployment/agents.sh"',
            "deploy_client_settings() { printf '[\"settings\"]\\n' >> \"$ADOPTION_LOG\"; }",
            "install_agents",
        ))
        result = subprocess.run(["/bin/bash", "-c", script], env=environment, cwd=SOURCE,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)
        return environment

    def assert_frozen_codex(self):
        installs = [event for event in self.events("bun") if event[1] == "codex"]
        self.assertTrue(installs)
        self.assertIn("--frozen-lockfile", installs[-1])
        project = self.home / ".bun/managed/codex"
        self.assertEqual((project / "package.json").read_bytes(),
                         (SOURCE / "deployment/agents/codex/package.json").read_bytes())
        self.assertEqual((project / "bun.lock").read_bytes(),
                         (SOURCE / "deployment/agents/codex/bun.lock").read_bytes())

    def test_exact_device_codex_is_adopted_repeatedly_with_two_regular_launchers(self):
        physical = self.tools / "Caskroom/codex" / self.pin / "bin/codex"
        physical.parent.mkdir(parents=True)
        self.codex.rename(physical)
        self.codex.symlink_to(physical)
        original = physical.read_bytes()
        for _ in range(2):
            environment = self.install()
            self.assertFalse((self.home / ".bun/managed/codex").exists())
            self.assertEqual(physical.read_bytes(), original)
            for relative in (".local/bin/codex", ".bun/bin/codex"):
                launcher = self.home / relative
                self.assertTrue(launcher.is_file())
                self.assertFalse(launcher.is_symlink())
                result = subprocess.run([str(launcher), "argument with spaces", "'literal'"],
                                        env=environment, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.events("device-codex")[-1][1:],
                                 ["argument with spaces", "'literal'"])
        self.assertEqual([event[1] for event in self.events("bun")], ["codegraph", "codegraph"])
        self.assertEqual(len(self.events("settings")), 2)
        self.assertEqual(len(self.events("wt")), 2)
        self.assertEqual(self.events("wt")[0][1:], ["config", "plugins", "codex", "install", "--yes"])

    def test_nonmatching_suffixed_and_failing_diagnostics_use_frozen_bun(self):
        for diagnostic, status in (("codex-cli 99.0.0", 0), ("codex-cli " + self.pin + "-beta", 0),
                                   ("codex-cli " + self.pin + ".1", 0), ("codex-cli " + self.pin, 7),
                                   (self.pin, 0), ("codex-cli " + self.pin + "\nextra output", 0)):
            with self.subTest(diagnostic=diagnostic, status=status):
                self.log.unlink(missing_ok=True)
                self.write_codex(diagnostic, status)
                self.install()
                self.assert_frozen_codex()

    def test_external_version_is_revalidated_after_adoption(self):
        self.install()
        self.assertFalse((self.home / ".bun/managed/codex").exists())
        self.write_codex("codex-cli 99.0.0")
        self.install()
        self.assert_frozen_codex()

    def test_adoption_also_works_before_any_managed_bun_directory_exists(self):
        bun_root = self.home / ".bun"
        self.originals = {path: original for path, original in self.originals.items()
                          if bun_root not in path.parents}
        shutil.rmtree(bun_root)
        self.install()
        self.assertFalse((bun_root / "managed/codex").exists())
        self.assertEqual([event[1] for event in self.events("bun")], ["codegraph"])

    def test_owned_launchers_and_managed_project_cannot_be_adopted(self):
        owned = self.root / "old/bin/codex"
        self.write_tool(owned, '#!/bin/sh\n# Managed by dotfiles; Bun installs the frozen project.\nexit 93\n')
        self.codex.unlink()
        self.codex.symlink_to(owned)
        for relative in (".local/bin/codex", ".bun/bin/codex"):
            self.write_tool(self.home / relative,
                            '#!/bin/sh\n# Managed by dotfiles; adopted macOS Codex.\nexec "$0" "$@"\n')
        self.install()
        self.assert_frozen_codex()
        # Even an exact physical managed package must not become an external provider.
        self.log.unlink()
        self.codex.unlink()
        managed = self.home / ".bun/managed/codex/node_modules/.bin/codex"
        self.write_codex(path=managed)
        self.codex.symlink_to(managed)
        self.install()
        self.assert_frozen_codex()
        self.assertFalse(self.events("device-codex"))

    def test_foreign_platform_or_architecture_never_adopts_host_codex(self):
        for target in ({"platform": "linux"}, {"native_platform": "linux"}, {"arch": "x86_64"}):
            with self.subTest(target=target):
                self.log.unlink(missing_ok=True)
                self.install(**target)
                self.assert_frozen_codex()
                self.assertFalse(self.events("device-codex"))

    def test_other_selected_clients_keep_their_frozen_projects_and_plugins(self):
        self.install(selection="kimi,pi,opencode,claude,codex,minimax")
        self.assertEqual([event[1] for event in self.events("bun")],
                         ["kimi", "pi", "opencode", "claude", "minimax", "codegraph"])
        self.assertTrue(all("--frozen-lockfile" in event for event in self.events("bun")))
        self.assertEqual([event[3] for event in self.events("wt")], ["claude", "codex", "opencode", "pi"])
        self.assertEqual(len(self.events("settings")), 1)


if __name__ == "__main__":
    unittest.main()
