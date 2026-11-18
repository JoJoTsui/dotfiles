"""macOS resolves Homebrew first and falls back to the frozen Bun project.

The device's Homebrew owns the installed version. The deployment adopts a
package at or above the catalog floor, never installs or upgrades one, and
falls back to the frozen Bun project when the package is missing, below the
floor, or removed after adoption.
"""
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
CATALOG = "deployment/agents/providers.tsv"


def catalog_records():
    records = []
    for line in (SOURCE / CATALOG).read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            records.append(line.split("|"))
    return records


def homebrew_record(name):
    """The Homebrew record of one agent: package, kind, floor, and commands."""
    record = next(item for item in catalog_records()
                  if item[0] == name and item[1] == "homebrew")
    return {"package": record[2], "kind": record[3], "floor": record[4],
            "commands": record[6].split(","), "diagnostic": record[14]}


class MacosBrewFirstTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-brew-first-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.tools = self.root / "device tools"
        self.tools.mkdir()
        for relative in (".local/bin", ".bun/bin", ".pixi/bin", ".local/state"):
            (self.home / relative).mkdir(parents=True)
        self.log = self.root / "events.jsonl"
        self.brew_log = self.root / "brew.log"
        self.packages = self.root / "brew-packages"
        self.packages.mkdir()
        self.commands = {name: entry["commands"].split(",") for name, entry in agent_pins().items()}
        self.write_tool(self.tools / "node", self.node_script())
        self.write_tool(self.tools / "bun", self.bun_script())
        self.write_tool(self.root / "brew", self.brew_script())

    def write_tool(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def node_script(self):
        # The deployment reads and rewrites one package manifest with Node.
        return ("#!" + sys.executable + "\n"
                "import json, pathlib, sys\n"
                "if sys.argv[1:2] == ['--version']:\n"
                f"    print('v{common_pin('nodejs')}'); raise SystemExit\n"
                "args = sys.argv[3:]\n"
                "if len(args) == 4:\n"
                "    source, destination, package, version = args\n"
                "    manifest = json.loads(pathlib.Path(source).read_text())\n"
                "    manifest.setdefault('dependencies', {})[package] = version\n"
                "    pathlib.Path(destination).write_text(json.dumps(manifest, indent=2) + '\\n')\n"
                "elif len(args) == 2:\n"
                "    manifest, package = args\n"
                "    try:\n"
                "        declared = json.loads(pathlib.Path(manifest).read_text())['dependencies'][package]\n"
                "    except Exception:\n"
                "        raise SystemExit(0)\n"
                "    print(declared)\n"
                "elif len(args) == 1:\n"
                "    try:\n"
                "        data = json.loads(pathlib.Path(args[0]).read_text())\n"
                "    except Exception:\n"
                "        raise SystemExit(0)\n"
                "    bins = data.get('bin') or {}\n"
                "    names = [pathlib.Path(bins).name] if isinstance(bins, str) else list(bins)\n"
                "    print(str(data.get('version', '')) + '\\t' + ' '.join(names))\n")

    def bun_script(self):
        # The frozen project installs from its lock; the fake runtime writes
        # the commands the catalog declares and reports the manifest version.
        commands = json.dumps(self.commands)
        return ("#!" + sys.executable + "\n"
                "import json, os, pathlib, sys\n"
                "commands = " + commands + "\n"
                "if sys.argv[1:] == ['--version']:\n"
                f"    print({common_pin('bun')!r}); raise SystemExit\n"
                "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
                "with open(os.environ['ADOPTION_LOG'], 'a') as log:\n"
                "    log.write(json.dumps(['bun', project.name, *sys.argv[1:]]) + '\\n')\n"
                "if '--lockfile-only' in sys.argv:\n"
                "    (project / 'bun.lock').write_text('{\"lockfileVersion\": 1}\\n')\n"
                "    raise SystemExit\n"
                "manifest = json.loads((project / 'package.json').read_text())\n"
                "version = next(iter(manifest['dependencies'].values()))\n"
                "for command in commands[project.name]:\n"
                "    target = project / 'node_modules/.bin' / command\n"
                "    target.parent.mkdir(parents=True, exist_ok=True)\n"
                "    target.write_text('#!/bin/sh\\necho ' + version + '\\n')\n"
                "    target.chmod(0o755)\n")

    def brew_script(self):
        # The fake Homebrew lists the packages the device already has. It
        # never installs one.
        return ("#!" + sys.executable + "\n"
                "import os, pathlib, sys\n"
                "with open(os.environ['BREW_LOG'], 'a') as log:\n"
                "    log.write(' '.join(sys.argv[1:]) + '\\n')\n"
                "args = sys.argv[1:]\n"
                "if args[:1] == ['list']:\n"
                "    kind = 'cask' if '--cask' in args else 'formula'\n"
                "    package = args[-1]\n"
                "    marker = pathlib.Path(os.environ['BREW_PACKAGES']) / (kind + '-' + package)\n"
                "    if marker.exists():\n"
                "        print(package + ' ' + marker.read_text().strip())\n"
                "        raise SystemExit(0)\n"
                "    raise SystemExit(1)\n"
                "raise SystemExit(0)\n")

    def write_package(self, record, version):
        """The device's Homebrew provides this package at this version."""
        (self.packages / (record["kind"] + "-" + record["package"])).write_text(version + "\n")

    def remove_package(self, record):
        (self.packages / (record["kind"] + "-" + record["package"])).unlink()

    def write_command(self, name, version, template="-"):
        """The command the device's Homebrew exposes on PATH."""
        diagnostic = version if template == "-" else template.replace("{version}", version)
        self.write_tool(self.tools / name, "#!/bin/sh\nprintf '%s\\n' " + shlex.quote(diagnostic) + "\n")

    def install(self, *, selection="kimi", platform="macos", native_platform="macos",
                arch="aarch64", native_arch="arm64", override=None, homebrew=True, source=SOURCE,
                extra_path=(), expect_success=True):
        if override:
            versions = self.home / ".config/dotfiles"
            versions.mkdir(parents=True, exist_ok=True)
            (versions / "versions.tsv").write_text(f"agent|{selection}|{override}\n")
        environment = {"HOME": str(self.home), "BUN_INSTALL": str(self.home / ".bun"),
                       "PIXI_HOME": str(self.home / ".pixi"), "ADOPTION_LOG": str(self.log),
                       "BREW_LOG": str(self.brew_log), "BREW_PACKAGES": str(self.packages),
                       "XDG_STATE_HOME": str(self.home / ".local/state"),
                       "PATH": os.pathsep.join(map(str, (self.home / ".local/bin", self.home / ".bun/bin",
                                                        *extra_path, self.tools, "/usr/bin", "/bin"))),
                       "DOTFILES_COMMON_BIN": str(self.home / ".local/bin"),
                       "DOTFILES_BUN_BIN": str(self.tools / "bun"),
                       "DOTFILES_NODE_BIN": str(self.tools / "node")}
        if homebrew:
            environment["DOTFILES_HOMEBREW_BIN"] = str(self.root / "brew")
        script = "\n".join((
            "set -euo pipefail",
            "DEPLOY_SOURCE=" + shlex.quote(str(source)),
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
            "client_claude_uses_plain_opus() { return 1; }",
            "deploy_client_settings() { printf '[\"settings\"]\\n' >> \"$ADOPTION_LOG\"; }",
            "install_agents",
        ))
        result = subprocess.run(["/bin/bash", "-c", script], env=environment, cwd=SOURCE,
                                capture_output=True, text=True, timeout=120)
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def state(self):
        path = self.home / ".local/state/dotfiles/agents.lock.tsv"
        if not path.exists():
            return {}
        rows = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            rows[fields[0]] = "|".join(fields[1:])
        return rows

    def launcher(self, name):
        return (self.home / ".local/bin" / name).read_text()

    def status(self, selection="kimi"):
        """The managed status view of the deployed agents."""
        command = self.root / "dotfiles-agents"
        template = (SOURCE / "dot_local/bin/executable_dotfiles-agents.tmpl").read_text()
        command.write_text(template.replace("{{ .chezmoi.sourceDir }}", str(SOURCE)))
        command.chmod(0o755)
        environment = {"HOME": str(self.home), "PATH": os.pathsep.join(map(str, (
            self.home / ".local/bin", self.home / ".bun/bin", self.tools, "/usr/bin", "/bin"))),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "DOTFILES_PYTHON": sys.executable}
        return subprocess.run(["/bin/bash", str(command), "status", selection], env=environment,
                               cwd=self.root, capture_output=True, text=True, timeout=60)

    def bun_launcher(self, name):
        return (self.home / ".bun/bin" / name).read_text()

    def brew_calls(self):
        if not self.brew_log.exists():
            return []
        return self.brew_log.read_text(encoding="utf-8").splitlines()

    def bun_projects(self):
        if not self.log.exists():
            return []
        return [json.loads(line)[1] for line in self.log.read_text().splitlines()
                if json.loads(line)[0] == "bun"]

    def test_bun_install_preserves_device_launcher(self):
        launcher = self.home / ".bun/bin/kimi"
        original = "#!/bin/sh\necho device-launcher\n"
        self.write_tool(launcher, original)

        result = self.install(homebrew=False, expect_success=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agent launcher would replace a device file", result.stderr)
        self.assertEqual(launcher.read_text(), original)
        self.assertFalse((self.home / ".local/bin/kimi").exists())

    def test_adopted_agent_preserves_local_launcher_symlink(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        managed = self.home / ".bun/bin/kimi"
        previous = "#!/bin/sh\n# Managed by dotfiles; earlier launcher.\n"
        self.write_tool(managed, previous)
        target = self.root / "device-launcher"
        original = "#!/bin/sh\necho device-launcher\n"
        self.write_tool(target, original)
        launcher = self.home / ".local/bin/kimi"
        launcher.symlink_to(target)

        result = self.install(expect_success=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agent launcher is a symlink", result.stderr)
        self.assertTrue(launcher.is_symlink())
        self.assertEqual(target.read_text(), original)
        self.assertEqual(managed.read_text(), previous)

    def test_a_package_at_the_floor_is_adopted_without_a_bun_project(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        result = self.install()
        self.assertIn(f"dotfiles: adopted kimi {record['floor']} from ", result.stdout)
        # The deployment owns no frozen project for an adopted agent.
        self.assertNotIn("kimi", self.bun_projects())
        self.assertFalse((self.home / ".bun/managed/kimi").exists())
        for launcher in (self.launcher("kimi"), self.bun_launcher("kimi")):
            self.assertIn(str(self.tools / "kimi"), launcher)
        self.assertEqual(self.state()["kimi"], f"homebrew|{record['floor']}|{record['floor']}")

    def test_a_package_above_the_floor_is_adopted_at_its_own_version(self):
        record = homebrew_record("kimi")
        self.write_package(record, "9.9.9")
        self.write_command("kimi", "9.9.9")
        self.install()
        self.assertNotIn("kimi", self.bun_projects())
        self.assertIn(str(self.tools / "kimi"), self.launcher("kimi"))
        self.assertEqual(self.state()["kimi"], f"homebrew|9.9.9|{record['floor']}")

    def test_a_package_below_the_floor_falls_back_to_the_frozen_bun_project(self):
        record = homebrew_record("kimi")
        self.write_package(record, "0.0.1")
        self.write_command("kimi", "0.0.1")
        self.install()
        self.assertIn("kimi", self.bun_projects())
        project = self.home / ".bun/managed/kimi/node_modules/.bin/kimi"
        self.assertTrue(project.is_file())
        for launcher in (self.launcher("kimi"), self.bun_launcher("kimi")):
            self.assertIn(str(project), launcher)
        self.assertNotIn(str(self.tools / "kimi"), self.launcher("kimi"))
        self.assertEqual(self.state()["kimi"], f"bun|{record['floor']}|{record['floor']}")

    def test_a_missing_package_falls_back_to_the_frozen_bun_project(self):
        record = homebrew_record("kimi")
        self.write_command("kimi", record["floor"])
        self.install()
        self.assertIn("kimi", self.bun_projects())
        self.assertEqual(self.state()["kimi"], f"bun|{record['floor']}|{record['floor']}")

    def test_an_older_command_earlier_on_path_does_not_block_the_adoption(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        stale = self.root / "stale"
        stale.mkdir()
        self.write_tool(stale / "kimi", "#!/bin/sh\nprintf '%s\\n' 0.0.1\n")
        self.install(extra_path=(stale,))
        # The command that reports the package version is the adopted one.
        self.assertIn(str(self.tools / "kimi"), self.launcher("kimi"))
        self.assertNotIn(str(stale / "kimi"), self.launcher("kimi"))
        self.assertEqual(self.state()["kimi"], f"homebrew|{record['floor']}|{record['floor']}")

    def test_a_device_without_homebrew_falls_back_to_the_frozen_bun_project(self):
        record = homebrew_record("kimi")
        self.write_command("kimi", record["floor"])
        self.install(homebrew=False)
        self.assertIn("kimi", self.bun_projects())
        self.assertEqual(self.state()["kimi"], f"bun|{record['floor']}|{record['floor']}")

    def test_a_package_removed_after_adoption_is_repaired_on_the_next_apply(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        self.install()
        self.assertEqual(self.state()["kimi"], f"homebrew|{record['floor']}|{record['floor']}")
        # The device removes the package; the next apply repairs the launchers.
        self.remove_package(record)
        self.install()
        project = self.home / ".bun/managed/kimi/node_modules/.bin/kimi"
        self.assertTrue(project.is_file())
        for launcher in (self.launcher("kimi"), self.bun_launcher("kimi")):
            self.assertIn(str(project), launcher)
            self.assertNotIn(str(self.tools / "kimi"), launcher)
        self.assertEqual(self.state()["kimi"], f"bun|{record['floor']}|{record['floor']}")

    def test_the_deployment_never_installs_or_upgrades_a_homebrew_package(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        self.install()
        for call in self.brew_calls():
            self.assertTrue(call.startswith("list "), call)
            self.assertNotIn("install", call)
            self.assertNotIn("upgrade", call)

    def test_every_agent_homebrew_ships_resolves_through_its_package(self):
        for name in ("kimi", "pi", "opencode", "claude", "codex"):
            record = homebrew_record(name)
            with self.subTest(agent=name):
                self.write_package(record, record["floor"])
                # The package exposes one executable; the catalog may name
                # more than one command for it.
                self.write_command(record["commands"][0], record["floor"], record["diagnostic"])
                self.install(selection=name)
                self.assertNotIn(name, self.bun_projects())
                for command in record["commands"]:
                    self.assertIn(str(self.tools / record["commands"][0]), self.launcher(command))
                    self.assertIn(str(self.tools / record["commands"][0]), self.bun_launcher(command))
                self.assertEqual(self.state()[name], f"homebrew|{record['floor']}|{record['floor']}")

    def test_an_unselected_agent_keeps_its_managed_launchers(self):
        self.write_tool(self.home / ".local/bin/pi", "#!/bin/sh\n# Managed by dotfiles; device state.\n")
        self.write_tool(self.home / ".bun/bin/pi", "#!/bin/sh\n# Managed by dotfiles; device state.\n")
        before = (self.home / ".local/bin/pi").read_bytes()
        self.install(selection="kimi")
        self.assertEqual((self.home / ".local/bin/pi").read_bytes(), before)
        self.assertNotIn("pi", self.state())

    def test_a_device_version_override_forces_the_deployment_owned_install(self):
        record = homebrew_record("kimi")
        self.write_package(record, "9.9.9")
        self.write_command("kimi", "9.9.9")
        self.install(selection="kimi", override="8.8.8")
        # An installer-owned provider cannot promise an exact version.
        self.assertIn("kimi", self.bun_projects())
        project = self.home / ".bun/managed/kimi/node_modules/.bin/kimi"
        self.assertTrue(project.is_file())
        self.assertIn(str(project), self.launcher("kimi"))
        self.assertEqual(self.state()["kimi"], f"bun|8.8.8|{record['floor']}")

    def test_a_package_that_drops_below_the_floor_is_revalidated_on_the_next_apply(self):
        record = homebrew_record("kimi")
        self.write_package(record, "9.9.9")
        self.write_command("kimi", "9.9.9")
        self.install()
        self.assertEqual(self.state()["kimi"], f"homebrew|9.9.9|{record['floor']}")
        self.write_package(record, "0.0.1")
        self.install()
        project = self.home / ".bun/managed/kimi/node_modules/.bin/kimi"
        self.assertIn(str(project), self.launcher("kimi"))
        self.assertEqual(self.state()["kimi"], f"bun|{record['floor']}|{record['floor']}")

    def test_the_managed_launchers_are_never_adopted_as_a_provider(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        # The device's own command is the managed launcher, not an installer copy.
        self.write_tool(self.home / ".local/bin/kimi", "#!/bin/sh\n# Managed by dotfiles; device state.\n")
        self.write_tool(self.home / ".bun/bin/kimi", "#!/bin/sh\n# Managed by dotfiles; device state.\n")
        self.install()
        self.assertIn("kimi", self.bun_projects())
        self.assertEqual(self.state()["kimi"], f"bun|{record['floor']}|{record['floor']}")

    def test_a_foreign_platform_or_architecture_never_adopts_the_host_package(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        for target in ({"platform": "linux"}, {"native_platform": "linux"}, {"arch": "x86_64"}):
            with self.subTest(target=target):
                self.install(**target)
                self.assertIn("kimi", self.bun_projects())
                self.assertEqual(self.state()["kimi"], f"bun|{record['floor']}|{record['floor']}")

    def test_adoption_works_before_any_managed_bun_directory_exists(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        shutil.rmtree(self.home / ".bun")
        self.install()
        self.assertEqual(self.state()["kimi"], f"homebrew|{record['floor']}|{record['floor']}")

    def test_status_reports_the_provider_and_the_effective_version(self):
        record = homebrew_record("kimi")
        self.write_package(record, "9.9.9")
        self.write_command("kimi", "9.9.9")
        self.install()
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PROVIDER", result.stdout)
        line = next(line for line in result.stdout.splitlines() if line.startswith("kimi "))
        self.assertIn("homebrew", line)
        self.assertIn("9.9.9", line)
        self.assertIn("installed", line)

    def test_status_reports_a_version_above_the_floor_as_installed(self):
        record = homebrew_record("kimi")
        # Without device state the status compares the device's version with
        # the catalog floor.
        self.write_command("kimi", "9.9.9")
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next(line for line in result.stdout.splitlines() if line.startswith("kimi "))
        self.assertIn("homebrew", line)
        self.assertIn(record["floor"], line)
        self.assertIn("installed", line)
        self.assertNotIn("mismatch", line)

    def test_status_reports_a_device_owned_version_as_device_owned(self):
        record = homebrew_record("kimi")
        self.write_package(record, "9.9.9")
        self.write_command("kimi", "9.9.9")
        self.install(selection="kimi", override="8.8.8")
        result = self.status()
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next(line for line in result.stdout.splitlines() if line.startswith("kimi "))
        self.assertIn("bun", line)
        self.assertIn("8.8.8", line)
        self.assertIn("device-owned version", line)


if __name__ == "__main__":
    unittest.main()
