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


def bun_version(name):
    """The pinned version of one agent's deployment-owned Bun record."""
    record = next(item for item in catalog_records()
                  if item[0] == name and item[1] == "bun")
    return record[4]


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
        self.brew_prefix = self.root / "homebrew"
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
                f"prefix = pathlib.Path({str(self.brew_prefix)!r})\n"
                "if args == ['--prefix']:\n"
                "    print(prefix); raise SystemExit(0)\n"
                "if args[0] in ('--cellar', '--caskroom'):\n"
                "    root = prefix / ('Cellar' if args[0] == '--cellar' else 'Caskroom')\n"
                "    print(root.joinpath(*args[1:])); raise SystemExit(0)\n"
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
        """Install a keg or staged cask and link its Homebrew exposures."""
        agent = next(row[0] for row in catalog_records()
                     if row[1] == "homebrew" and row[6].split(",")[0] == name)
        record = homebrew_record(agent)
        formula = record["kind"] == "formula"
        keg = self.brew_prefix / ("Cellar" if formula else "Caskroom") / record["package"] / version
        binary = keg / "bin" / name
        diagnostic = version if template == "-" else template.replace("{version}", version)
        self.write_tool(binary, "#!/bin/sh\nprintf '%s\\n' " + shlex.quote(diagnostic) + "\n")
        links = [self.brew_prefix / "bin" / name]
        if formula:
            links.append(self.brew_prefix / "opt" / record["package"])
        for link, target in zip(links, (binary, keg)):
            link.parent.mkdir(parents=True, exist_ok=True)
            link.unlink(missing_ok=True)
            link.symlink_to(target)
        return binary

    def formula_command(self, name):
        record = homebrew_record(name)
        return self.brew_prefix / "opt" / record["package"] / "bin" / record["commands"][0]

    def install(self, *, selection="kimi", platform="macos", native_platform="macos",
                arch="aarch64", native_arch="arm64", override=None, homebrew=True, source=SOURCE,
                extra_path=(), expect_success=True, update=False):
        if override:
            versions = self.home / ".config/dotfiles"
            versions.mkdir(parents=True, exist_ok=True)
            (versions / "versions.tsv").write_text(f"agent|{selection}|{override}\n")
        environment = {"HOME": str(self.home), "BUN_INSTALL": str(self.home / ".bun"),
                       "PIXI_HOME": str(self.home / ".pixi"), "ADOPTION_LOG": str(self.log),
                       "BREW_LOG": str(self.brew_log), "BREW_PACKAGES": str(self.packages),
                       "XDG_STATE_HOME": str(self.home / ".local/state"),
                       "PATH": os.pathsep.join(map(str, (self.home / ".local/bin", self.home / ".bun/bin",
                                                        *extra_path, self.brew_prefix / "bin",
                                                        self.tools, "/usr/bin", "/bin"))),
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
        invocation = ["/bin/bash", "-c", script]
        if update:
            # Exercise the managed CLI and real Homebrew update command. Only
            # the upstream pin lookup is replaced. Bootstrap runs the same
            # Homebrew/Bun installer seam as the rest of the fixture.
            update_source = self.root / "update-source"
            update_source.mkdir(exist_ok=True)
            deployment = update_source / "deployment"
            if not deployment.is_symlink():
                deployment.symlink_to(source / "deployment", target_is_directory=True)
            (update_source / "bootstrap.sh").write_text(script)
            python = self.root / "offline-python"
            self.write_tool(python, "#!" + sys.executable + "\n"
                            "import os, pathlib, sys\n"
                            "args = sys.argv[1:]\n"
                            "if args[1:2] == ['propose-agents']:\n"
                            "    pathlib.Path(args[args.index('--output') + 1]).write_text('{\"agents\": {}}')\n"
                            "else:\n"
                            "    os.execv(sys.executable, [sys.executable, *args])\n")
            environment.update(DOTFILES_SOURCE=str(update_source), DOTFILES_PYTHON=str(python))
            invocation = ["/bin/bash", str(self.agent_wrapper()), "update", selection]
        result = subprocess.run(invocation, env=environment, cwd=SOURCE,
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

    def test_a_narrow_install_keeps_the_state_of_the_agents_it_did_not_install(self):
        # The state records every agent the device runs. An install that
        # covers part of the selection replaces its own rows and keeps the
        # rest, so a narrow apply does not erase what it did not look at.
        for name, version in (("kimi", "2.7.0"), ("opencode", "2.3.2")):
            self.write_package(homebrew_record(name), version)
            self.write_command(name, version)
        self.install(selection="kimi")
        self.assertIn("kimi", self.state())
        self.install(selection="opencode")
        state = self.state()
        self.assertIn("opencode", state)
        self.assertIn("kimi", state)

    def launcher(self, name):
        return (self.home / ".local/bin" / name).read_text()

    def agent_wrapper(self):
        command = self.root / "dotfiles-agents"
        template = (SOURCE / "dot_local/bin/executable_dotfiles-agents.tmpl").read_text()
        command.write_text(template.replace("{{ .chezmoi.sourceDir }}", str(SOURCE)))
        command.chmod(0o755)
        return command

    def status(self, selection="kimi"):
        """The managed status view of the deployed agents."""
        environment = {"HOME": str(self.home), "PATH": os.pathsep.join(map(str, (
            self.home / ".local/bin", self.home / ".bun/bin", self.brew_prefix / "bin",
            self.tools, "/usr/bin", "/bin"))),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "DOTFILES_PYTHON": sys.executable, "DOTFILES_HOMEBREW_BIN": str(self.root / "brew"),
            "BREW_LOG": str(self.brew_log), "BREW_PACKAGES": str(self.packages)}
        return subprocess.run(["/bin/bash", str(self.agent_wrapper()), "status", selection], env=environment,
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
            self.assertIn(str(self.formula_command("kimi")), launcher)
        self.assertEqual(self.state()["kimi"], f"homebrew|{record['floor']}|{record['floor']}")

    def test_a_package_above_the_floor_is_adopted_at_its_own_version(self):
        record = homebrew_record("kimi")
        self.write_package(record, "9.9.9")
        self.write_command("kimi", "9.9.9")
        self.install()
        self.assertNotIn("kimi", self.bun_projects())
        self.assertIn(str(self.formula_command("kimi")), self.launcher("kimi"))
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
        self.assertNotIn(str(self.formula_command("kimi")), self.launcher("kimi"))
        self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

    def test_a_missing_package_falls_back_to_the_frozen_bun_project(self):
        record = homebrew_record("kimi")
        self.write_command("kimi", record["floor"])
        self.install()
        self.assertIn("kimi", self.bun_projects())
        self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

    def test_a_same_version_command_earlier_on_path_is_not_adopted(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        stale = self.root / "stale"
        stale.mkdir()
        marker = self.root / "shadow-executed"
        self.write_tool(stale / "kimi", f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n"
                        f"printf '%s\\n' {record['floor']}\n")
        self.install(extra_path=(stale,))
        self.assertIn(str(self.formula_command("kimi")), self.launcher("kimi"))
        self.assertNotIn(str(stale / "kimi"), self.launcher("kimi"))
        self.assertFalse(marker.exists())
        self.assertEqual(self.state()["kimi"], f"homebrew|{record['floor']}|{record['floor']}")

    def test_same_version_links_outside_the_installed_keg_fall_back_to_bun(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        binary = self.write_command("kimi", record["floor"])
        foreign = self.brew_prefix / "Cellar/other" / record["floor"] / "bin/kimi"
        marker = self.root / "foreign-executed"
        self.write_tool(foreign, f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n"
                        f"printf '%s\\n' {record['floor']}\n")
        binary.unlink()
        binary.symlink_to(foreign)

        self.install()
        self.assertFalse(marker.exists())
        self.assertIn("kimi", self.bun_projects())
        self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

    def test_a_formula_launcher_follows_a_relinked_opt_prefix_after_upgrade(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        original = self.write_command("kimi", record["floor"])
        self.install()
        launcher = self.home / ".local/bin/kimi"
        self.assertIn(str(self.formula_command("kimi")), launcher.read_text())

        self.write_package(record, "9.9.9")
        self.write_command("kimi", "9.9.9")
        original.unlink()
        result = subprocess.run([launcher, "--version"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "9.9.9")

        self.install()
        self.assertEqual(self.state()["kimi"], f"homebrew|9.9.9|{record['floor']}")
        if sys.platform == "darwin":
            status = self.status()
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("last apply: homebrew 9.9.9", status.stdout)
            self.assertIn(f"live: installed | provider: homebrew | version: 9.9.9 | command: kimi | path: {launcher}",
                          status.stdout)

    def test_the_selected_update_recovers_a_removed_cask_executable(self):
        record = homebrew_record("codex")
        self.write_package(record, record["floor"])
        original = self.write_command("codex", record["floor"], record["diagnostic"])
        self.install(selection="codex")
        launcher = self.home / ".local/bin/codex"
        self.assertIn(str(original.resolve()), launcher.read_text())

        self.write_package(record, "9.9.9")
        replacement = self.write_command("codex", "9.9.9", record["diagnostic"])
        original.unlink()
        stale = self.root / "earlier tools"
        self.write_tool(stale / "codex", "#!/bin/sh\nprintf 'codex-cli 9.9.9\\n'\n")
        self.assertNotEqual(subprocess.run([launcher, "--version"], capture_output=True,
                                           timeout=10).returncode, 0)

        self.install(selection="codex", extra_path=(stale,), update=True)
        self.assertIn(f"upgrade --cask {record['package']}", self.brew_calls())
        self.assertFalse(any(call.startswith("install ") for call in self.brew_calls()))
        self.assertIn(str(replacement.resolve()), launcher.read_text())
        self.assertNotIn(str(stale / "codex"), launcher.read_text())
        self.assertEqual(self.state()["codex"], f"homebrew|9.9.9|{record['floor']}")
        if sys.platform == "darwin":
            status = self.status("codex")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("last apply: homebrew 9.9.9", status.stdout)
            self.assertIn("live: installed | provider: homebrew | version: 9.9.9", status.stdout)

    def test_a_device_without_homebrew_falls_back_to_the_frozen_bun_project(self):
        record = homebrew_record("kimi")
        self.write_command("kimi", record["floor"])
        self.install(homebrew=False)
        self.assertIn("kimi", self.bun_projects())
        self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

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
            self.assertNotIn(str(self.formula_command("kimi")), launcher)
        self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

    def test_the_deployment_never_installs_or_upgrades_a_homebrew_package(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        self.install()
        for call in self.brew_calls():
            self.assertTrue(call.startswith(("list ", "--")), call)
            self.assertNotIn("install", call)
            self.assertNotIn("upgrade", call)

    def test_every_agent_homebrew_ships_resolves_through_its_package(self):
        for name in ("kimi", "pi", "opencode", "claude", "codex"):
            record = homebrew_record(name)
            with self.subTest(agent=name):
                self.write_package(record, record["floor"])
                # The package exposes one executable; the catalog may name
                # more than one command for it.
                binary = self.write_command(record["commands"][0], record["floor"], record["diagnostic"])
                self.install(selection=name)
                self.assertNotIn(name, self.bun_projects())
                expected = self.formula_command(name) if record["kind"] == "formula" else binary.resolve()
                for command in record["commands"]:
                    self.assertIn(str(expected), self.launcher(command))
                    self.assertIn(str(expected), self.bun_launcher(command))
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
        self.assertEqual(self.state()["kimi"], f"bun|8.8.8|{bun_version('kimi')}")

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
        self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

    def test_the_managed_launchers_are_never_adopted_as_a_provider(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        # The device's own command is the managed launcher, not an installer copy.
        self.write_tool(self.home / ".local/bin/kimi", "#!/bin/sh\n# Managed by dotfiles; device state.\n")
        self.write_tool(self.home / ".bun/bin/kimi", "#!/bin/sh\n# Managed by dotfiles; device state.\n")
        self.install()
        self.assertIn("kimi", self.bun_projects())
        self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

    def test_a_foreign_platform_or_architecture_never_adopts_the_host_package(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        for target in ({"platform": "linux"}, {"native_platform": "linux"}, {"arch": "x86_64"}):
            with self.subTest(target=target):
                self.install(**target)
                self.assertIn("kimi", self.bun_projects())
                self.assertEqual(self.state()["kimi"], f"bun|{bun_version('kimi')}|{bun_version('kimi')}")

    def test_adoption_works_before_any_managed_bun_directory_exists(self):
        record = homebrew_record("kimi")
        self.write_package(record, record["floor"])
        self.write_command("kimi", record["floor"])
        shutil.rmtree(self.home / ".bun")
        self.install()
        self.assertEqual(self.state()["kimi"], f"homebrew|{record['floor']}|{record['floor']}")

    @unittest.skipUnless(sys.platform == "darwin", "live status selects the native provider chain")
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

    @unittest.skipUnless(sys.platform == "darwin", "live status selects the native provider chain")
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
        self.assertIn("last apply: unavailable", line)
        self.assertIn("installed", line)
        self.assertIn("provider: unverified | version: 9.9.9", line)
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
        self.assertIn("last apply: bun 8.8.8", line)
        self.assertIn("live: installed | provider: bun | version: 8.8.8", line)


if __name__ == "__main__":
    unittest.main()
