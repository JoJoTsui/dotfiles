"""The portable check calls each platform's own public adapter.

The plan fields both adapters share are compared, and the tool and step
selections stay with the adapter that owns them. A plan that came from the
wrong adapter is visible instead of passing as the platform's own.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import verify_portable

SOURCE = Path(__file__).resolve().parents[1]


def plan(**overrides):
    """A plan shaped like the public adapters' output."""
    value = {
        "platform": "windows", "role": "workstation", "arch": "x86_64",
        "profile": "windows-workstation", "mirror": "tuna",
        "source": str(SOURCE), "home": "/tmp/case/target-home",
        "agents": ["kimi", "codex"], "bundles": [],
        "packages": [{"environment": "git", "dependencies": {"git": "==2.56.0"}, "exposed": {"git": "git"}}],
        "bundlePackages": [],
        "agentPackages": [{"name": "kimi", "provider": "bun", "policy": "exact", "version": "1.6.0",
                           "commands": ["kimi"], "herdr": "kimi", "package": "@kimi-code/kimi",
                           "manager": "bun", "minimumNode": "22.19.0",
                           "lock": "deployment/agents/kimi/bun.lock"}],
        "settings": {"mode": "copy", "primaryShell": "nu", "secondaryShells": ["git-bash"],
                     "systemChanges": False, "loginShellChanges": False},
        "roots": {"config": "/tmp/case/target-home/.config", "data": "/tmp/case/target-home/.local/share",
                  "state": "/tmp/case/target-home/.local/state", "cache": "/tmp/case/target-home/.cache",
                  "pixi": "/tmp/case/target-home/.pixi", "bun": "/tmp/case/target-home/.bun"},
        "tools": sorted(verify_portable.COMMON_TOOLS) + ["chezmoi", "rustup", "hx", "jq", "bash", "sh"],
        "steps": ["install-managers", "apply-source", "install-common", "install-agents",
                  "install-magpie-cli", "prepare-shell"],
    }
    value.update(overrides)
    return value


class SharedPlanComparisonTests(unittest.TestCase):
    def test_two_plans_that_agree_have_no_shared_difference(self):
        self.assertEqual(verify_portable.shared_plan_differences(plan(), plan()), [])

    def test_a_shared_field_difference_is_named(self):
        second = plan(profile="windows-remote-compute")
        differences = verify_portable.shared_plan_differences(plan(), second)
        self.assertEqual(len(differences), 1)
        self.assertIn("profile", differences[0])

    def test_a_differing_agent_entry_is_named(self):
        second = plan()
        second["agentPackages"][0]["version"] = "1.5.0"
        differences = verify_portable.shared_plan_differences(plan(), second)
        self.assertEqual(len(differences), 1)
        self.assertIn("agentPackages.kimi", differences[0])

    def test_the_tool_list_and_the_steps_stay_with_their_adapter(self):
        # The native Windows adapter exposes Git Bash and installs the Magpie
        # CLI; the Unix adapter runs the shared-source steps. Neither list is
        # a shared field, so a difference in them is not a disagreement.
        second = plan(tools=["pixi", "zsh"], steps=["install-managers", "apply-source.skills"])
        self.assertEqual(verify_portable.shared_plan_differences(plan(), second), [])


class PlatformSelectionTests(unittest.TestCase):
    def test_a_unix_plan_carries_steps_the_windows_adapter_never_runs(self):
        unix_plan = plan(steps=list(verify_portable.POWERSHELL_STEPS) +
                         ["apply-source.skills", "magpie-apply"])
        with self.assertRaisesRegex(verify_portable.VerificationError, "another adapter's steps"):
            verify_portable.require_platform_steps(unix_plan, "windows")

    def test_a_windows_plan_carries_steps_the_unix_adapter_never_runs(self):
        with self.assertRaisesRegex(verify_portable.VerificationError, "another adapter's steps"):
            verify_portable.require_platform_steps(plan(), "linux")

    def test_each_adapter_must_run_its_own_deployment_steps(self):
        with self.assertRaisesRegex(verify_portable.VerificationError, "missing deployment steps"):
            verify_portable.require_platform_steps(plan(steps=["install-managers"]), "windows")

    def test_native_windows_claims_no_managed_zsh(self):
        with self.assertRaisesRegex(verify_portable.VerificationError, "must not claim a managed Zsh"):
            verify_portable.require_platform_tools(plan(tools=plan()["tools"] + ["zsh"]), "windows")

    def test_macos_claims_no_managed_bash(self):
        macos_plan = plan(platform="macos", profile="macos-workstation",
                           tools=sorted(verify_portable.COMMON_TOOLS) + ["zsh", "bash"],
                           steps=list(verify_portable.BASH_STEPS))
        with self.assertRaisesRegex(verify_portable.VerificationError, "must not claim a managed Bash"):
            verify_portable.require_platform_tools(macos_plan, "macos")


class AdapterAvailabilityTests(unittest.TestCase):
    def test_the_windows_adapter_needs_a_powershell_runtime(self):
        with mock.patch.object(verify_portable, "powershell_executable", return_value=None):
            self.assertIsNone(verify_portable.powershell_executable())
            comparison = verify_portable.compare_public_adapters(Path("/nonexistent"))
        self.assertEqual(comparison["outcome"], "skipped")
        self.assertIn("PowerShell", comparison["reason"])

    def test_a_missing_powershell_runtime_leaves_the_windows_plan_unrun(self):
        with mock.patch.object(verify_portable, "powershell_executable", return_value=None):
            with tempfile.TemporaryDirectory(prefix="dotfiles-plan-") as temporary:
                root = Path(temporary)
                case = verify_portable.case_directory(root)
                with self.assertRaises(verify_portable.VerificationError):
                    verify_portable.powershell_plan(case, "windows", "x86_64", "workstation")


class LocalLayerAcceptanceTests(unittest.TestCase):
    """The local layer is accepted only after every check it owns passed."""

    def matrix(self):
        return {"matrixCells": 1, "plans": 1, "bundleOutcomes": 0,
                "scenarios": [{"name": "linux-x86_64-workstation public plan", "outcome": "passed"}],
                "skipped": []}

    def test_a_failed_catalog_check_leaves_the_local_layer_unaccepted(self):
        report = {}
        failed = subprocess.CompletedProcess([], 1, "", "the catalog is inconsistent")
        with mock.patch.object(verify_portable, "verify_local_matrix", return_value=self.matrix()), \
             mock.patch.object(verify_portable, "compare_public_adapters",
                               return_value={"name": "public adapter comparison", "outcome": "passed"}), \
             mock.patch.object(verify_portable, "invoke", return_value=failed):
            with self.assertRaises(verify_portable.VerificationError):
                verify_portable.verify_local(report)
        self.assertEqual(report["local"]["status"], "failed")
        self.assertFalse(report["local"]["acceptance"])
        self.assertIn("catalog", report["local"]["failure"])

    def test_a_passed_local_layer_is_accepted_after_its_checks(self):
        report = {}
        matrix = self.matrix()
        passed = subprocess.CompletedProcess([], 0, "ok", "")
        with mock.patch.object(verify_portable, "verify_local_matrix", return_value=matrix), \
             mock.patch.object(verify_portable, "compare_public_adapters",
                               return_value={"name": "public adapter comparison", "outcome": "passed"}), \
             mock.patch.object(verify_portable, "invoke", return_value=passed), \
             mock.patch.object(verify_portable, "run_suite"):
            verify_portable.verify_local(report)
        self.assertEqual(report["local"]["status"], "passed")
        self.assertTrue(report["local"]["acceptance"])
        self.assertEqual(report["local"]["versionCatalog"], "passed")
        self.assertEqual(report["local"]["skillPins"], "passed")
        self.assertEqual(report["local"]["testSuite"], "passed")

    def test_the_failed_report_keeps_the_local_layer_failed(self):
        report = {"local": {"status": "running"}}
        verify_portable.record_failure(report, verify_portable.VerificationError("the catalog is inconsistent"))
        self.assertEqual(report["local"]["status"], "failed")
        self.assertFalse(report["local"]["acceptance"])
        self.assertEqual(report["status"], "failed")
        self.assertIn("catalog", report["failure"])


class PublicPlanTests(unittest.TestCase):
    """The public Unix adapter renders the plan the portable check reads."""

    def test_the_unix_adapter_plan_carries_the_shared_fields(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-plan-") as temporary:
            root = Path(temporary)
            case = verify_portable.case_directory(root)
            rendered = verify_portable.bash_plan(case, "linux", "x86_64", "workstation")
        self.assertEqual(rendered["platform"], "linux")
        self.assertEqual(rendered["profile"], "linux-workstation")
        verify_portable.require_shared_plan(rendered, "linux", "x86_64", "workstation")
        verify_portable.require_platform_tools(rendered, "linux")
        verify_portable.require_platform_steps(rendered, "linux")

    def test_a_plan_is_json_the_check_can_read(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-plan-") as temporary:
            root = Path(temporary)
            case = verify_portable.case_directory(root)
            rendered = verify_portable.bash_plan(case, "macos", "aarch64", "remote-compute")
        self.assertIsInstance(json.loads(json.dumps(rendered)), dict)
        verify_portable.require_platform_tools(rendered, "macos")


if __name__ == "__main__":
    unittest.main()
