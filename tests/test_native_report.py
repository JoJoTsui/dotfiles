"""The native report contract: checkout identity and scenario outcomes."""
import codecs
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import native_report

SOURCE = Path(__file__).resolve().parents[1]
WINDOWS_ADAPTER = Path(__file__).resolve().parent / "native" / "windows.ps1"


def powershell_runtime():
    """The PowerShell runtime the native Windows adapter needs."""
    for variable in ("DOTFILES_TEST_POWERSHELL", "DOTFILES_TEST_PWSH"):
        value = os.environ.get(variable)
        if value and Path(value).is_file():
            return str(Path(value))
    found = shutil.which("pwsh")
    return found


class ScenarioOutcomeTests(unittest.TestCase):
    def test_a_scenario_that_did_not_pass_states_its_reason(self):
        log = native_report.ScenarioLog()
        for outcome in (native_report.FAILED, native_report.SKIPPED, native_report.UNAVAILABLE):
            with self.subTest(outcome=outcome):
                with self.assertRaises(ValueError):
                    log.record("scenario", outcome)

    def test_an_unknown_outcome_is_rejected(self):
        log = native_report.ScenarioLog()
        with self.assertRaises(ValueError):
            log.record("scenario", "maybe")

    def test_a_recorded_scenario_keeps_its_reason_and_details(self):
        log = native_report.ScenarioLog()
        log.passed("installation")
        log.skipped("bundle exposure", reason="no bundle was selected")
        log.failed("reapplication", reason="a managed file changed")
        records = log.records
        self.assertEqual([record["outcome"] for record in records],
                         [native_report.PASSED, native_report.SKIPPED, native_report.FAILED])
        self.assertNotIn("reason", records[0])
        self.assertEqual(records[1]["reason"], "no bundle was selected")
        self.assertEqual(records[2]["reason"], "a managed file changed")
        self.assertEqual(log.counts(), {native_report.PASSED: 1, native_report.FAILED: 1,
                                        native_report.SKIPPED: 1, native_report.UNAVAILABLE: 0})


class FixtureScenarioOutcomeTests(unittest.TestCase):
    """The outcome a native fixture reported for one scenario."""

    def report(self, *lines):
        return "\n".join(lines) + "\n"

    def test_a_scenario_the_fixture_passed_is_passed(self):
        text = self.report(native_report.fixture_marker('native bundle exposure', native_report.FIXTURE_STARTED),
                           native_report.fixture_marker('native bundle exposure', native_report.PASSED))
        self.assertEqual(native_report.fixture_scenario_outcome(text, 'native bundle exposure'),
                         native_report.PASSED)

    def test_a_scenario_the_fixture_started_and_never_passed_failed(self):
        # The run stopped inside the scenario, so the scenario failed instead
        # of staying a scenario that was never reached.
        text = self.report(native_report.fixture_marker('native bundle exposure', native_report.FIXTURE_STARTED))
        self.assertEqual(native_report.fixture_scenario_outcome(text, 'native bundle exposure'),
                         native_report.FAILED)

    def test_a_scenario_the_fixture_never_started_was_never_reached(self):
        text = self.report(native_report.fixture_marker('native full-to-narrow agent state and status',
                                                         native_report.PASSED))
        self.assertIsNone(native_report.fixture_scenario_outcome(text, 'native bundle exposure'))

    def test_a_scenario_the_fixture_reported_as_failed_is_failed(self):
        text = self.report(native_report.fixture_marker('native targeted repair and preservation',
                                                         native_report.FAILED))
        self.assertEqual(native_report.fixture_scenario_outcome(text, 'native targeted repair and preservation'),
                         native_report.FAILED)

    def test_the_marker_names_the_scenario_and_its_transition(self):
        self.assertEqual(native_report.fixture_marker('native bundle exposure', native_report.FIXTURE_STARTED),
                         'native scenario native bundle exposure started')
        with self.assertRaises(ValueError):
            native_report.fixture_marker('native bundle exposure', 'maybe')

    def test_the_outcome_query_answers_from_the_fixture_report(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-fixture-report-") as temporary:
            log = Path(temporary) / "fixture.log"
            log.write_text(self.report(native_report.fixture_marker('native bundle exposure',
                                                                     native_report.FIXTURE_STARTED),
                                       native_report.fixture_marker('native bundle exposure',
                                                                     native_report.PASSED)),
                           encoding="utf-8")
            command = [sys.executable, str(SOURCE / "tests" / "native_report.py"),
                       "--fixture-outcome", "--log", str(log)]
            passed = subprocess.run(command + ["--scenario", "native bundle exposure"],
                                    capture_output=True, text=True, timeout=30)
            unreached = subprocess.run(command + ["--scenario", "native targeted repair and preservation"],
                                       capture_output=True, text=True, timeout=30)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(passed.stdout.strip(), native_report.PASSED)
        self.assertEqual(unreached.returncode, 0, unreached.stderr)
        self.assertEqual(unreached.stdout.strip(), native_report.SKIPPED)

    def test_the_outcome_query_reads_a_missing_report_as_never_reached(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-fixture-report-") as temporary:
            log = Path(temporary) / "absent.log"
            result = subprocess.run([sys.executable, str(SOURCE / "tests" / "native_report.py"),
                                     "--fixture-outcome", "--log", str(log),
                                     "--scenario", "native bundle exposure"],
                                    capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), native_report.SKIPPED)


class FixtureReportEncodingTests(unittest.TestCase):
    """The encoding a native runner wrote its fixture report in.

    Windows PowerShell 5.1 writes its Tee-Object log as UTF-16LE with a byte
    order mark, while a modern runner writes UTF-8. The report has to be read
    in the encoding it carries, or the fixture's own transitions stay
    unreadable and every scenario it reported looks like one it never
    reached.
    """

    def report(self, *transitions):
        return "\n".join(native_report.fixture_marker('native bundle exposure', transition)
                         for transition in transitions) + "\n"

    def query(self, log, scenario='native bundle exposure'):
        command = [sys.executable, str(SOURCE / "tests" / "native_report.py"),
                   "--fixture-outcome", "--log", str(log)]
        return subprocess.run(command + ["--scenario", scenario],
                              capture_output=True, text=True, timeout=30)

    def test_a_powershell_5_1_report_keeps_the_transition_it_states(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-fixture-encoding-") as temporary:
            log = Path(temporary) / "fixture.log"
            log.write_bytes(codecs.BOM_UTF16_LE +
                            self.report(native_report.FIXTURE_STARTED,
                                        native_report.PASSED).encode("utf-16-le"))
            passed = self.query(log)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(passed.stdout.strip(), native_report.PASSED)

    def test_a_powershell_5_1_report_states_a_scenario_it_started_and_never_passed(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-fixture-encoding-") as temporary:
            log = Path(temporary) / "fixture.log"
            log.write_bytes(codecs.BOM_UTF16_LE +
                            self.report(native_report.FIXTURE_STARTED).encode("utf-16-le"))
            started = self.query(log)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(started.stdout.strip(), native_report.FAILED)

    def test_a_modern_report_keeps_the_transition_it_states(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-fixture-encoding-") as temporary:
            log = Path(temporary) / "fixture.log"
            log.write_bytes(self.report(native_report.FIXTURE_STARTED,
                                        native_report.PASSED).encode("utf-8"))
            passed = self.query(log)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(passed.stdout.strip(), native_report.PASSED)

    def test_a_report_with_a_utf_8_mark_keeps_the_transition_it_states(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-fixture-encoding-") as temporary:
            log = Path(temporary) / "fixture.log"
            log.write_bytes(codecs.BOM_UTF8 +
                            self.report(native_report.FIXTURE_STARTED,
                                        native_report.PASSED).encode("utf-8"))
            passed = self.query(log)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(passed.stdout.strip(), native_report.PASSED)


class ReportStatusTests(unittest.TestCase):
    def records(self, *outcomes):
        log = native_report.ScenarioLog()
        for index, outcome in enumerate(outcomes):
            log.record(f"scenario-{index}", outcome,
                       reason=None if outcome == native_report.PASSED else "the scenario did not run")
        return log.records

    def test_an_unavailable_runner_is_not_a_pass(self):
        records = self.records(native_report.PASSED)
        self.assertEqual(native_report.status(records, native_execution=False), native_report.UNAVAILABLE)
        self.assertFalse(native_report.acceptance(records, native_execution=False))

    def test_a_run_without_a_passed_scenario_establishes_nothing(self):
        records = self.records(native_report.SKIPPED)
        self.assertEqual(native_report.status(records), native_report.UNAVAILABLE)
        self.assertFalse(native_report.acceptance(records))

    def test_a_failed_scenario_fails_the_run(self):
        records = self.records(native_report.PASSED, native_report.FAILED)
        self.assertEqual(native_report.status(records), native_report.FAILED)
        self.assertFalse(native_report.acceptance(records))

    def test_a_skipped_scenario_stays_visible_beside_a_pass(self):
        records = self.records(native_report.PASSED, native_report.SKIPPED)
        self.assertEqual(native_report.status(records), native_report.PASSED)
        self.assertTrue(native_report.acceptance(records))
        summary = native_report.summarize(records)
        self.assertEqual(summary["status"], native_report.PASSED)
        self.assertTrue(summary["acceptance"])
        self.assertEqual(summary["counts"][native_report.SKIPPED], 1)
        self.assertEqual(summary["scenarios"][1]["reason"], "the scenario did not run")


class GitCheckoutFixture(unittest.TestCase):
    """A committed checkout the report can identify."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-checkout-identity-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        home = self.root / "home"
        home.mkdir()
        environment = {
            "HOME": str(home), "PATH": os.environ.get("PATH", os.defpath),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "LC_ALL": "C", "TMPDIR": str(self.root),
        }
        isolation = mock.patch.dict(os.environ, environment, clear=True)
        isolation.start()
        self.addCleanup(isolation.stop)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Report Fixture")
        self.git("config", "user.email", "report@example.invalid")
        (self.source / ".gitignore").write_text("private/\n")
        (self.source / "managed.txt").write_text("committed configuration\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "fixture")

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-C", str(self.source), *arguments], stderr=subprocess.PIPE,
            text=True, timeout=10)


class CheckoutIdentityTests(GitCheckoutFixture):
    def test_the_identity_names_the_commit_and_the_tree(self):
        identity = native_report.checkout_identity(self.source)
        self.assertEqual(identity["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(identity["tree"], self.git("rev-parse", "HEAD^{tree}").strip())
        self.assertFalse(identity["working_tree_dirty"])
        self.assertRegex(identity["source_sha256"], r"^[0-9a-f]{64}$")

    def test_an_uncommitted_change_is_visible_in_the_identity(self):
        clean = native_report.checkout_identity(self.source)
        (self.source / "managed.txt").write_text("changed configuration\n")
        identity = native_report.checkout_identity(self.source)
        self.assertTrue(identity["working_tree_dirty"])
        self.assertNotEqual(identity["source_sha256"], clean["source_sha256"])

    def test_an_ignored_device_file_stays_out_of_the_identity(self):
        clean = native_report.checkout_identity(self.source)
        private = self.source / "private"
        private.mkdir()
        (private / "settings").write_text("synthetic private configuration\n")
        self.assertEqual(native_report.checkout_identity(self.source), clean)

    def test_an_unusable_checkout_is_reported_as_unknown(self):
        identity = native_report.establish_identity(self.root / "absent")
        self.assertEqual(identity["commit"], "unknown")
        self.assertIsNone(identity["working_tree_dirty"])
        self.assertEqual(identity["revision_status"], "unknown")
        self.assertFalse(native_report.identity_establishes_acceptance(identity))


class IdentityEstablishmentTests(GitCheckoutFixture):
    """The identity a run establishes before it starts testing."""

    def test_the_identity_names_the_revision_the_run_verified(self):
        identity = native_report.establish_identity(self.source)
        self.assertEqual(identity["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(identity["tree"], self.git("rev-parse", "HEAD^{tree}").strip())
        self.assertFalse(identity["working_tree_dirty"])
        self.assertEqual(identity["revision_source"], "git")
        self.assertEqual(identity["revision_status"], "verified")
        self.assertRegex(identity["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(native_report.identity_establishes_acceptance(identity))

    def test_the_identity_carries_the_declared_fields(self):
        identity = native_report.establish_identity(self.source)
        for field in native_report.IDENTITY_FIELDS:
            self.assertIn(field, identity)

    def test_the_expected_revision_is_confirmed_against_the_checkout(self):
        revision = self.git("rev-parse", "HEAD").strip()
        identity = native_report.establish_identity(self.source, revision)
        self.assertEqual(identity["revision_status"], "verified")
        self.assertTrue(native_report.identity_establishes_acceptance(identity))

    def test_a_revision_that_differs_from_the_checkout_is_mismatched(self):
        identity = native_report.establish_identity(self.source, "0" * 40)
        self.assertEqual(identity["revision_status"], "mismatched")
        self.assertFalse(native_report.identity_establishes_acceptance(identity))

    def test_a_transported_source_carries_the_revision_its_transport_supplied(self):
        transported = self.root / "transported"
        transported.mkdir()
        (transported / "managed.txt").write_text("committed configuration\n")
        identity = native_report.establish_identity(transported, "a" * 40)
        self.assertEqual(identity["commit"], "a" * 40)
        self.assertEqual(identity["tree"], "unknown")
        self.assertEqual(identity["revision_source"], "supplied")
        self.assertEqual(identity["revision_status"], "supplied")
        self.assertRegex(identity["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(native_report.identity_establishes_acceptance(identity))

    def test_a_source_without_a_revision_establishes_no_acceptance(self):
        transported = self.root / "transported"
        transported.mkdir()
        (transported / "managed.txt").write_text("committed configuration\n")
        identity = native_report.establish_identity(transported)
        self.assertEqual(identity["revision_status"], "unknown")
        self.assertFalse(native_report.identity_establishes_acceptance(identity))

    def test_a_transported_digest_ignores_runtime_bytecode(self):
        transported = self.root / "transported"
        transported.mkdir()
        (transported / "managed.txt").write_text("committed configuration\n")
        before = native_report.source_digest(transported)
        cache = transported / "__pycache__"
        cache.mkdir()
        (cache / "managed.cpython-313.pyc").write_bytes(b"cached bytecode\n")
        self.assertEqual(native_report.source_digest(transported), before)


class RequiredScenarioTests(unittest.TestCase):
    """A scenario the run must establish gates the acceptance."""

    def records(self, *outcomes):
        log = native_report.ScenarioLog()
        for index, outcome in enumerate(outcomes):
            log.record(f"scenario-{index}", outcome,
                       reason=None if outcome == native_report.PASSED else "the scenario did not run")
        return log.records

    def test_a_required_scenario_that_did_not_pass_withholds_acceptance(self):
        records = self.records(native_report.PASSED, native_report.SKIPPED)
        self.assertTrue(native_report.acceptance(records))
        self.assertFalse(native_report.acceptance(records, required=["scenario-1"]))
        summary = native_report.summarize(records, required=["scenario-1"])
        self.assertEqual(summary["required"]["unmet"], ["scenario-1"])
        self.assertEqual(summary["required"]["missing"], [])

    def test_a_required_scenario_the_run_never_reached_is_missing(self):
        records = self.records(native_report.PASSED)
        self.assertFalse(native_report.acceptance(records, required=["scenario-9"]))
        summary = native_report.summarize(records, required=["scenario-9"])
        self.assertEqual(summary["required"]["missing"], ["scenario-9"])

    def test_an_unknown_revision_withholds_acceptance(self):
        records = self.records(native_report.PASSED)
        identity = {"commit": "unknown", "revision_status": "unknown"}
        self.assertFalse(native_report.acceptance(records, identity=identity))


class NativeReportAssemblyTests(GitCheckoutFixture):
    """The collected facts become the report every adapter leaves."""

    def test_the_report_carries_the_checkout_the_scenarios_and_the_verdict(self):
        facts = {
            "source": str(self.source), "native_execution": True,
            "scenarios": [{"name": "native renderer preparation", "outcome": native_report.PASSED},
                          {"name": "known folder fallback", "outcome": native_report.SKIPPED,
                           "reason": "the disposable-home contract forbids it"}],
            "fields": {"platform": "windows", "role": "workstation"},
        }
        report = native_report.build_report(facts)
        self.assertEqual(report["checkout"]["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(report["platform"], "windows")
        self.assertEqual(report["status"], native_report.PASSED)
        self.assertTrue(report["acceptance"])
        self.assertEqual(report["counts"][native_report.SKIPPED], 1)
        self.assertEqual(report["scenarios"][1]["reason"], "the disposable-home contract forbids it")

    def test_a_fact_without_a_reason_is_not_usable(self):
        facts = {"source": str(self.source), "native_execution": True,
                 "scenarios": [{"name": "native renderer preparation", "outcome": native_report.FAILED}]}
        with self.assertRaisesRegex(ValueError, "needs a reason"):
            native_report.build_report(facts)

    def test_the_report_carries_the_identity_the_run_established(self):
        identity = native_report.establish_identity(self.source)
        facts = {"source": str(self.source), "native_execution": True, "identity": identity,
                 "required": ["native renderer preparation"],
                 "scenarios": [{"name": "native renderer preparation", "outcome": native_report.PASSED}],
                 "fields": {"platform": "windows"}}
        report = native_report.build_report(facts)
        self.assertEqual(report["checkout"]["commit"], identity["commit"])
        self.assertEqual(report["checkout"]["source_sha256"], identity["source_sha256"])
        self.assertTrue(report["acceptance"])
        self.assertEqual(report["required"]["unmet"], [])

    def test_a_source_that_changed_during_the_run_fails_the_report(self):
        identity = native_report.establish_identity(self.source)
        (self.source / "managed.txt").write_text("changed during the run\n")
        facts = {"source": str(self.source), "native_execution": True, "identity": identity,
                 "scenarios": [{"name": "native renderer preparation", "outcome": native_report.PASSED}]}
        report = native_report.build_report(facts)
        outcomes = {record["name"]: record["outcome"] for record in report["scenarios"]}
        self.assertEqual(outcomes["source remained unchanged"], native_report.FAILED)
        self.assertFalse(report["acceptance"])

    def test_a_required_scenario_that_did_not_pass_withholds_the_acceptance(self):
        facts = {"source": str(self.source), "native_execution": True,
                 "required": ["native targeted repair and preservation"],
                 "scenarios": [{"name": "native renderer preparation", "outcome": native_report.PASSED},
                               {"name": "native targeted repair and preservation",
                                "outcome": native_report.SKIPPED,
                                "reason": "the native deployment tests did not reach it"}]}
        report = native_report.build_report(facts)
        self.assertFalse(report["acceptance"])
        self.assertEqual(report["required"]["unmet"], ["native targeted repair and preservation"])


class IdentityCommandTests(GitCheckoutFixture):
    """The adapter establishes the identity before it starts testing."""

    def test_the_identity_command_prints_the_checkout_identity(self):
        result = subprocess.run([sys.executable, str(SOURCE / "tests" / "native_report.py"),
                                 "--identity", "--source", str(self.source)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        identity = json.loads(result.stdout)
        self.assertEqual(identity["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(identity["revision_status"], "verified")


@unittest.skipUnless(powershell_runtime(), "the native Windows adapter needs a PowerShell runtime")
class NativeWindowsReportTests(unittest.TestCase):
    """The native Windows adapter reports the checkout and every scenario."""

    def run_adapter(self, *arguments, environment=None):
        return subprocess.run([powershell_runtime(), "-NoLogo", "-NoProfile", "-NonInteractive",
                               "-File", str(WINDOWS_ADAPTER), *arguments],
                              capture_output=True, text=True, timeout=300,
                              env=environment or dict(os.environ))

    def failing_python(self, directory, *, identity_only=False):
        """A Python stand-in the report contract cannot finish with.

        Without `identity_only` every call fails. With it, the identity probe
        answers and the assembler fails, so the run knows its checkout but
        cannot assemble a report from it.
        """
        path = Path(directory) / "report-python"
        if identity_only:
            path.write_text(f'#!/bin/sh\ncase "$*" in\n'
                            f'  *--identity*) exec "{sys.executable}" "{SOURCE / "tests" / "native_report.py"}" "$@" ;;\n'
                            f'  *) exit 4 ;;\nesac\n')
        else:
            path.write_text("#!/bin/sh\nexit 4\n")
        path.chmod(0o755)
        return str(path)

    def test_the_adapter_script_parses(self):
        environment = dict(os.environ, DOTFILES_PARSE_TARGET=str(WINDOWS_ADAPTER))
        command = ("$tokens = $null; $errors = $null; "
                   "$null = [System.Management.Automation.Language.Parser]::ParseFile("
                   "$env:DOTFILES_PARSE_TARGET, [ref]$tokens, [ref]$errors); "
                   "if ($errors -and $errors.Count -gt 0) { "
                   "$errors | ForEach-Object { $_.Message }; exit 1 }; exit 0")
        result = subprocess.run([powershell_runtime(), "-NoLogo", "-NoProfile", "-NonInteractive",
                                 "-Command", command],
                                capture_output=True, text=True, timeout=120, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_foreign_runner_reports_the_checkout_and_no_acceptance(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-windows-report-") as temporary:
            report_directory = Path(temporary) / "report"
            result = self.run_adapter("-Role", "workstation",
                                       "-ReportDirectory", str(report_directory))
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((report_directory / "windows.json").read_text())
        revision = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"],
                                           text=True).strip()
        self.assertEqual(report["checkout"]["commit"], revision)
        self.assertRegex(report["checkout"]["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(report["acceptance"], "a foreign runner cannot establish acceptance")
        self.assertEqual(report["status"], native_report.UNAVAILABLE)
        scenarios = {record["name"]: record for record in report["scenarios"]}
        self.assertEqual(scenarios["checkout identity"]["outcome"], native_report.PASSED)
        self.assertEqual(scenarios["native runtime and architecture"]["outcome"],
                         native_report.UNAVAILABLE)
        self.assertIn("Windows", scenarios["native runtime and architecture"]["reason"])
        for name in ("native renderer preparation", "native windows deployment tests",
                     "native bundle exposure", "native full-to-narrow agent state and status",
                     "native targeted repair and preservation", "known folder fallback"):
            self.assertEqual(scenarios[name]["outcome"], native_report.SKIPPED, name)
            self.assertTrue(scenarios[name]["reason"], name)
        for record in report["scenarios"]:
            self.assertIn(record["outcome"], native_report.OUTCOMES)

    def test_the_apply_only_seed_never_claims_the_bundle_exposure(self):
        # The renderer preparation applies the source without installing a
        # bundle, so it cannot establish that the bundle is exposed.
        with tempfile.TemporaryDirectory(prefix="dotfiles-windows-report-") as temporary:
            report_directory = Path(temporary) / "report"
            result = self.run_adapter("-Role", "workstation", "-Bundles", "desktop",
                                       "-ReportDirectory", str(report_directory))
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((report_directory / "windows.json").read_text())
        scenarios = {record["name"]: record for record in report["scenarios"]}
        exposure = scenarios["native bundle exposure"]
        self.assertNotEqual(exposure["outcome"], native_report.PASSED,
                            "the apply-only renderer preparation cannot establish a bundle exposure")
        self.assertTrue(exposure["reason"])

    def assert_fresh_nonacceptance(self, report):
        """The report this run leaves replaces the verdict of an earlier run.

        A runner that could not execute natively establishes nothing about the
        target, so its report is unavailable; a native run whose report
        contract failed is failed.
        """
        self.assertFalse(report["acceptance"], "a stale acceptance must never survive a failed report")
        self.assertNotEqual(report["status"], "passed")
        self.assertIn("contract", report.get("reason", ""))
        self.assertTrue(report.get("scenarios"), "the fresh report names the scenarios this run observed")
        self.assertEqual(report["status"], "failed" if report.get("nativeExecution") else "unavailable")

    def test_a_preseeded_acceptance_does_not_survive_a_failed_contract(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-windows-report-") as temporary:
            report_directory = Path(temporary) / "report"
            report_directory.mkdir(parents=True)
            stale = report_directory / "windows.json"
            stale.write_text(json.dumps({"status": "passed", "acceptance": True}))
            environment = dict(os.environ, DOTFILES_TEST_PYTHON=self.failing_python(temporary))
            result = self.run_adapter("-Role", "workstation",
                                       "-ReportDirectory", str(report_directory), environment=environment)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(stale.read_text())
        self.assert_fresh_nonacceptance(report)

    def test_a_failed_assembler_publishes_no_stale_report(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-windows-report-") as temporary:
            report_directory = Path(temporary) / "report"
            report_directory.mkdir(parents=True)
            stale = report_directory / "windows.json"
            stale.write_text(json.dumps({"status": "passed", "acceptance": True}))
            environment = dict(os.environ, DOTFILES_TEST_PYTHON=self.failing_python(temporary, identity_only=True))
            result = self.run_adapter("-Role", "workstation",
                                       "-ReportDirectory", str(report_directory), environment=environment)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(stale.read_text())
        self.assert_fresh_nonacceptance(report)
        self.assertIn("contract", report["reason"])


if __name__ == "__main__":
    unittest.main()
