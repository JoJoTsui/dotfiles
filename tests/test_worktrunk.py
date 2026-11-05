"""Worktrunk wiring: the CLI, its skills, the shells, and the client plugins.

The deployment owns the `wt` command, the upstream skill bytes and the shell
integration. The per-client plugins are client state installed by the CLI.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


def catalog_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(line.split("|"))
    return rows


class WorktrunkCatalogTests(unittest.TestCase):
    def test_common_catalog_exposes_worktrunk_on_unix_hosts_only(self):
        rows = {row[0]: row for row in catalog_rows(SOURCE / "deployment/common-tools.tsv")}
        self.assertIn("worktrunk", rows)
        environment, specifications, exposures, targets = rows["worktrunk"]
        self.assertEqual(environment, "worktrunk")
        package, version = specifications.split("==")
        self.assertEqual(package, "worktrunk")
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(exposures, "wt=wt")
        # Native Windows resolves `wt` to Windows Terminal.
        self.assertEqual(targets, "unix")

    def test_skill_catalog_pins_both_worktrunk_skills(self):
        catalog = {row[0]: row for row in catalog_rows(SOURCE / "deployment/skills.tsv")}
        lock = {row[0]: row for row in catalog_rows(SOURCE / "deployment/skills.lock.tsv")}
        for name, path in (("worktrunk", "skills/worktrunk"),
                           ("wt-switch-create", "skills/wt-switch-create")):
            with self.subTest(skill=name):
                row = catalog[name]
                self.assertEqual(row[1], "git")
                self.assertEqual(row[2], "https://github.com/max-sixty/worktrunk")
                self.assertEqual(row[4], path)
                self.assertEqual(row[5], "auto")
                entry = lock[name]
                self.assertEqual(entry[1], "git")
                self.assertEqual(entry[2], row[2])
                self.assertEqual(len(entry[3]), 40)
                int(entry[3], 16)

    def test_shells_integrate_the_worktrunk_command(self):
        for name, shell in (("dot_bashrc", "bash"), ("dot_zshrc", "zsh")):
            with self.subTest(startup=name):
                text = (SOURCE / name).read_text(encoding="utf-8")
                # The managed binary is named directly: on native Windows `wt`
                # is Windows Terminal, and PATH lookup would find that.
                self.assertIn(f'"$PIXI_HOME/bin/wt" config shell init {shell}', text)
                self.assertNotIn("command -v wt", text)
        prepare = (SOURCE / "dot_local/bin/executable_dotfiles-shell-prepare").read_text(encoding="utf-8")
        self.assertIn('"$PIXI_HOME/bin/wt" config shell init nu', prepare)
        self.assertIn("wt.nu", prepare)
        targets = {row[0]: row for row in catalog_rows(SOURCE / "deployment/macos-targets.tsv")}
        self.assertIn(".local/share/nushell/vendor/autoload/wt.nu", targets)
        self.assertEqual(
            targets[".local/share/nushell/vendor/autoload/wt.nu"][1],
            "Library/Application Support/nushell/autoload/wt.nu")


@unittest.skipUnless(os.name == "posix", "POSIX shell execution")
class WorktrunkPluginTests(unittest.TestCase):
    def run_step(self, body, selection="claude,pi", wt_exit=0):
        with tempfile.TemporaryDirectory(prefix="dotfiles-worktrunk-") as temporary:
            root = Path(temporary)
            binary = root / "pixi" / "bin" / "wt"
            binary.parent.mkdir(parents=True)
            log = root / "wt.log"
            binary.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$WT_LOG\"\nexit " + str(wt_exit) + "\n")
            binary.chmod(0o755)
            script = root / "run.sh"
            script.write_text(
                "set -e\n"
                f"DEPLOY_SOURCE='{SOURCE}'\n"
                f"export PIXI_HOME='{root / 'pixi'}'\n"
                f"export WT_LOG='{log}'\n"
                f"export HOME='{root / 'home'}'\n"
                f"CLI_AGENTS='{selection}'\n"
                "CLI_AGENTS_SET=true\n"
                "fail() { echo \"$*\" >&2; exit 1; }\n"
                f"source '{SOURCE}/deployment/agents.sh'\n"
                + body,
                encoding="utf-8")
            result = subprocess.run(["/bin/bash", str(script)], capture_output=True,
                                    text=True, timeout=120)
            calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            return result, calls

    def test_selected_clients_receive_their_plugin(self):
        result, calls = self.run_step("install_worktrunk_plugins\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["config plugins claude install --yes",
                                  "config plugins pi install --yes"])

    def test_missing_clients_are_not_installed(self):
        result, calls = self.run_step("install_worktrunk_plugins\n", selection="codex,opencode")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["config plugins codex install --yes",
                                  "config plugins opencode install --yes"])

    def test_a_failing_plugin_install_ends_the_deployment(self):
        result, calls = self.run_step("install_worktrunk_plugins\n", wt_exit=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot install the worktrunk plugin", result.stderr)
        # Three attempts for the first client, then the deployment ends.
        self.assertEqual(len(calls), 3)
