"""The installer tier: catalog shape, plan reporting, and the install step.

Homebrew is adopted from the device. The tier never installs it, and a device
without it falls through to the package catalog.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
CATALOG = SOURCE / "deployment/installer-tools.tsv"


def catalog_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(line.split("|"))
    return rows


class InstallerCatalogTests(unittest.TestCase):
    def test_the_catalog_declares_the_ghostty_cask_for_macos(self):
        rows = {row[0]: row for row in catalog_rows(CATALOG)}
        self.assertIn("ghostty", rows)
        name, installer, kind, package, minimum, bundle, platforms = rows["ghostty"]
        self.assertEqual(name, "ghostty")
        self.assertEqual(installer, "homebrew")
        self.assertEqual(kind, "cask")
        self.assertEqual(package, "ghostty")
        self.assertRegex(minimum, r"^\d+\.\d+\.\d+$")
        self.assertEqual(bundle, "desktop")
        self.assertEqual(platforms, "macos")

    def test_every_row_names_a_known_bundle_and_platform(self):
        bundles = {row[0] for row in catalog_rows(SOURCE / "deployment/bundles.tsv")}
        seen = set()
        for row in catalog_rows(CATALOG):
            name, installer, kind, package, minimum, bundle, platforms = row
            with self.subTest(tool=name):
                self.assertNotIn(name, seen)
                seen.add(name)
                self.assertEqual(installer, "homebrew")
                self.assertIn(kind, ("formula", "cask"))
                self.assertTrue(package)
                self.assertRegex(minimum, r"^\d+\.\d+\.\d+$")
                self.assertIn(bundle, bundles | {"common"})
                self.assertTrue(platforms == "all" or platforms)

    def test_the_ghostty_configuration_is_managed_on_macos_only(self):
        template = SOURCE / "dot_config/ghostty/config.ghostty.tmpl"
        text = template.read_text(encoding="utf-8")
        # Ghostty resolves a built-in theme by its resource name.
        self.assertIn("theme = Catppuccin Mocha", text)
        self.assertIn("{{ .chezmoi.homeDir }}/.local/bin/nu-login", text)
        self.assertIn("{{ .chezmoi.homeDir }}/.config/ghostty/config.local.ghostty", text)
        # The include is created once and never overwritten, so the managed
        # configuration never reports a missing file.
        local = SOURCE / "dot_config/ghostty/create_config.local.ghostty"
        self.assertTrue(local.exists())
        self.assertIn("Device-local Ghostty tweaks", local.read_text(encoding="utf-8"))
        ignore = (SOURCE / ".chezmoiignore").read_text(encoding="utf-8")
        self.assertIn(".config/ghostty", ignore)


class InstallerPlanTests(unittest.TestCase):
    def plan(self, *arguments):
        home = tempfile.mkdtemp(prefix="dotfiles-installer-plan-")
        command = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", home,
                   "--plan", *arguments]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_the_tier_is_planned_for_its_bundle_and_platform(self):
        plan = self.plan("--platform", "macos", "--role", "workstation",
                         "--bundles", "desktop")
        self.assertEqual([entry["name"] for entry in plan["installerTools"] if entry["bundle"] == "desktop"], ["ghostty"])
        self.assertIn("nushell", [entry["name"] for entry in plan["installerTools"]])
        self.assertLess(plan["actions"].index("install-installer-tools"), plan["actions"].index("install-common"))
        self.assertEqual(plan["installerTools"][0]["installer"], "homebrew")

    def test_only_common_formulas_are_planned_without_a_bundle(self):
        plan = self.plan("--platform", "macos", "--role", "workstation")
        self.assertTrue(plan["installerTools"])
        self.assertEqual({entry["bundle"] for entry in plan["installerTools"]}, {"common"})

    def test_the_tier_is_absent_on_other_platforms(self):
        plan = self.plan("--platform", "linux", "--arch", "x86_64",
                         "--role", "workstation", "--bundles", "desktop")
        self.assertEqual(plan["installerTools"], [])

    def test_partial_modes_plan_no_installer_operations(self):
        for mode in ("--apply-only", "--agents-only"):
            plan = self.plan("--platform", "macos", "--role", "workstation", mode)
            self.assertEqual(plan["installerTools"], [])


class InstallerStepTests(unittest.TestCase):
    def run_step(self, *, homebrew=True, installed=None, account_home=None,
                 bundles="desktop", platform="macos"):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-installer-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        home = root / "home"
        home.mkdir()
        (root / "state").mkdir()
        log = root / "brew.log"
        marker = root / "installed"
        binary = root / "brew"
        if homebrew:
            binary.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> '{log}'\n"
                "case \"$*\" in\n"
                f"  'install --cask ghostty') printf '1.4.0\\n' > '{marker}' ;;\n"
                "esac\n"
                "case \"$*\" in\n"
                f"  'list --cask --versions ghostty') [ -f '{marker}' ] && printf 'ghostty %s\\n' \"$(cat '{marker}')\" ;;\n"
                "  *) exit 0 ;;\n"
                "esac\n")
            binary.chmod(0o755)
            if installed:
                marker.write_text(installed + "\n")
        script = root / "run.sh"
        catalog = root / "installer-tools.tsv"
        catalog.write_text("ghostty|homebrew|cask|ghostty|1.4.0|desktop|macos\n")
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{SOURCE}'\n"
            f"DEPLOY_PLATFORM='{platform}'\n"
            f"DEPLOY_HOME='{home}'\n"
            f"export XDG_STATE_HOME='{root / 'state'}'\n"
            f"export HOME='{home}'\n"
            "DEPLOY_BUNDLES_CSV='" + bundles + "'\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            "bundle_selected() { case \",$DEPLOY_BUNDLES_CSV,\" in *\",$1,\"*) return 0 ;; *) return 1 ;; esac; }\n"
            "detect_platform() { echo '" + platform + "'; }\n"
            f"native_account_value() {{ echo '{account_home or home}'; }}\n"
            f"source '{SOURCE}/deployment/installer.sh'\n"
            f"INSTALLER_CATALOG='{catalog}'\n"
            "install_installer_tools\n",
            encoding="utf-8")
        environment = dict(os.environ, PATH="/usr/bin:/bin")
        if homebrew:
            environment["DOTFILES_HOMEBREW_BIN"] = str(binary)
        result = subprocess.run(["/bin/bash", str(script)], capture_output=True,
                                text=True, timeout=120, env=environment)
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        state = root / "state" / "dotfiles" / "installer-tools.lock.tsv"
        recorded = state.read_text(encoding="utf-8").splitlines() if state.exists() else []
        return result, calls, recorded

    def test_a_malformed_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-installer-catalog-") as temporary:
            catalog = Path(temporary) / "installer-tools.tsv"
            catalog.write_text("ghostty|homebrew|cask|ghostty|1.4.0|desktop|macos\n"
                               "ghostty|homebrew|cask|ghostty|1.4.0|desktop|macos\n",
                               encoding="utf-8")
            script = Path(temporary) / "run.sh"
            script.write_text(
                "set -e\n"
                f"DEPLOY_SOURCE='{SOURCE}'\n"
                "fail() { echo \"$*\" >&2; exit 1; }\n"
                f"source '{SOURCE}/deployment/installer.sh'\n"
                f"validate_installer_catalog '{catalog}'\n",
                encoding="utf-8")
            result = subprocess.run(["/bin/bash", str(script)], capture_output=True,
                                    text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate installer catalog entry", result.stderr)

    def test_a_missing_cask_is_installed_and_recorded(self):
        result, calls, recorded = self.run_step(installed=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("install --cask ghostty", calls)
        self.assertEqual(recorded, ["ghostty|homebrew|1.4.0|1.4.0"])

    def test_an_installed_cask_is_recorded_without_installing(self):
        result, calls, recorded = self.run_step(installed="1.4.2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("install --cask ghostty", calls)
        self.assertEqual(recorded, ["ghostty|homebrew|1.4.2|1.4.0"])

    def test_a_version_below_the_minimum_fails_the_deployment(self):
        result, calls, recorded = self.run_step(installed="1.3.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("below the catalog minimum", result.stderr)
        self.assertEqual(recorded, [])

    def test_a_device_without_homebrew_falls_through(self):
        result, calls, recorded = self.run_step(homebrew=False, installed="1.4.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(recorded, [])
        self.assertIn("no Homebrew", result.stdout)

    def test_an_install_needs_the_real_account_home(self):
        result, calls, recorded = self.run_step(installed="", account_home="/nowhere")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("install --cask ghostty", calls)
        self.assertEqual(recorded, [])
        self.assertIn("real account home", result.stdout)

    def test_the_tier_is_skipped_without_its_bundle(self):
        result, calls, recorded = self.run_step(installed="1.4.0", bundles="bio")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(recorded, [])


if __name__ == "__main__":
    unittest.main()
