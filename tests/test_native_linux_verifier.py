"""Linux gate evidence cannot hide missing runtimes or unbounded children."""
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest import mock

import native_linux


class LinuxSuiteAuditTests(unittest.TestCase):
    def test_native_history_exclusions_are_named_and_other_required_skips_fail(self):
        summary = {"tests_run": 8, "successful": True, "skipped": [{
            "test": "test_portable_history_import.PortableHistoryImportTests.test_macos_nu_defaults_import_the_only_native_history",
            "reason": "native macOS history discovery"}]}
        audited = native_linux.audit_suite(summary)
        self.assertEqual(audited["skipped"][0]["classification"], "foreign-platform")
        self.assertEqual(audited["unexpected_skips"], 0)
        for identifier, reason in (
            ("test_codegraph.CodeGraphTests.test_managed_mcp_command_explores_only_an_explicitly_indexed_temporary_fixture",
             "requires the actual pinned CodeGraph CLI"),
            ("test_agent_payload.AgentPayloadTests.test_pinned_pi_resource_loader_reads_the_full_library_and_global_instructions",
             "requires the pinned Pi SDK module and managed Node"),
            ("test_portable_history_import.PortableHistoryImportTests.test_explicit_nu_text_uses_only_selected_file_and_filters_before_activation",
             "native macOS history discovery"),
        ):
            with self.subTest(test=identifier):
                with self.assertRaisesRegex(RuntimeError, "unexpected acceptance skips"):
                    native_linux.audit_suite({**summary, "skipped": [{"test": identifier, "reason": reason}]})

    def test_empty_failed_and_expected_failure_suites_cannot_pass(self):
        for summary in ({"tests_run": 0, "successful": True},
                        {"tests_run": 1, "successful": False},
                        {"tests_run": 1, "successful": True, "expected_failures": ["case"]}):
            with self.subTest(summary=summary), self.assertRaises(RuntimeError):
                native_linux.audit_suite(summary)

    def test_foreign_and_opt_in_scope_are_distinct(self):
        self.assertEqual(native_linux.classify_skip(
            "test_windows_deployment.WindowsBoundaryTests.test_plan",
            "set DOTFILES_TEST_POWERSHELL for the public Windows boundary"), "foreign-platform")
        self.assertEqual(native_linux.classify_skip(
            "test_package_resolution.PackageResolutionTests.test_resolve",
            "requires explicit isolated Pixi resolution for all supported targets"), "unselected-scope")
        self.assertEqual(native_linux.classify_skip(
            "test_shell_behavior.ShellBehaviorTests.test_shell", "missing borrowed shell: bash"), "unexpected")
        self.assertEqual(native_linux.classify_skip(
            "test_macos.MacOSProfileTests.test_native_verifier_reports_foreign_execution_as_unavailable",
            "this check exercises refusal on a foreign runtime"), "foreign-platform")
        self.assertEqual(native_linux.classify_skip(
            "test_wsl.WSLNativeBoundaryTests.test_disposable_distro_plan_pins_rootfs_and_never_provisions",
            "PowerShell parser/planning check requires DOTFILES_TEST_PWSH"), "foreign-platform")
        self.assertEqual(native_linux.classify_skip(
            "test_windows_deployment.WindowsBoundaryTests.test_normal_nu_startup_loads_the_rendered_environment_without_config_flags",
            "this local regression borrows the pinned Linux Nu executable"), "unexpected")

    def test_direct_suite_discovery_can_import_a_module_from_the_source_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "linux_gate_import_fixture.py").write_text("VALUE = 41\n")
            (root / "tests/test_linux_gate_import_scope.py").write_text(
                "import unittest\nfrom linux_gate_import_fixture import VALUE\n"
                "class SourceImportTests(unittest.TestCase):\n"
                "    def test_import(self): self.assertEqual(VALUE, 41)\n")
            destination = root / "suite.json"
            original_path = sys.path[:]
            try:
                with mock.patch.object(native_linux, "SOURCE", root), \
                        mock.patch.object(unittest, "defaultTestLoader", unittest.TestLoader()), \
                        mock.patch.object(sys, "stderr", io.StringIO()):
                    status = native_linux.suite_main("test_linux_gate_import_scope.py", destination)
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(destination.read_text())["tests_run"], 1)
            finally:
                sys.path[:] = original_path
                sys.modules.pop("linux_gate_import_fixture", None)
                sys.modules.pop("test_linux_gate_import_scope", None)


class LinuxSnapshotAndVersionTests(unittest.TestCase):
    def test_exact_first_line_version_tokens_reject_extensions_and_later_lines(self):
        for output in ("chezmoi version v2.73.3, commit abc", "2.73.3 (Client)"):
            self.assertTrue(native_linux.first_line_version_matches(output, "2.73.3"))
        for output in ("client 2.73.30", "client 2.73.3.1", "client 2.73.3-beta.1",
                       "client 2.73.3+build.1", "client v2.73.3rc1", "client unknown\n2.73.3"):
            with self.subTest(output=output):
                self.assertFalse(native_linux.first_line_version_matches(output, "2.73.3"))

    def test_jsonc_and_managed_json_keep_bytes_but_pixi_metadata_ignores_key_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            settings = home / "settings.json"
            contents = b'{\n// managed JSONC\n"value": 1\n}\n'
            settings.write_bytes(contents)
            self.assertEqual(native_linux.snapshot_fingerprint(settings, home)["sha256"],
                             hashlib.sha256(contents).hexdigest())
            settings.write_text('{"a":1,"b":2}')
            first = native_linux.snapshot_fingerprint(settings, home)
            settings.write_text('{"b":2,"a":1}')
            self.assertNotEqual(first, native_linux.snapshot_fingerprint(settings, home))
            trampoline = home / ".pixi/bin/trampoline_configuration/nu.json"
            trampoline.parent.mkdir(parents=True)
            trampoline.write_text('{"a":1,"b":2}')
            first = native_linux.snapshot_fingerprint(trampoline, home)
            trampoline.write_text('{"b":2, "a":1}\n')
            self.assertEqual(first, native_linux.snapshot_fingerprint(trampoline, home))

    def test_snapshot_enumerates_pixi_metadata_subdirectory_and_declared_minimax_skills(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            metadata = home / ".pixi/bin/trampoline_configuration/nu.json"
            skill = home / ".minimax/skills/example/SKILL.md"
            for path in (metadata, skill):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            with mock.patch.object(native_linux, "snapshot_fingerprint", return_value={"sha256": "fixture"}):
                snapshot = native_linux.snapshot(home, {"packages": [{"exposed": {"nu": "nu"}}], "agentPackages": []})
            self.assertIn(str(metadata.relative_to(home)), snapshot)
            self.assertIn(str(skill.relative_to(home)), snapshot)


class LinuxIsolationTests(unittest.TestCase):
    def test_cgroup_v2_quota_is_the_budget_and_not_the_visible_host_cpu_count(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(os, "cpu_count", return_value=14):
            root = Path(temporary)
            (root / "cpu.max").write_text("400000 100000\n")
            (root / "memory.max").write_text("8589934592\n")
            (root / "cpu.stat").write_text("nr_throttled 4\nthrottled_usec 123\n")
            resources = native_linux.resource_snapshot(root)
        self.assertEqual(resources["host_visible_cpus"], 14)
        self.assertEqual(resources["usable_cpus"], 4)
        self.assertEqual(resources["child_parallelism"], 3)
        self.assertEqual(resources["cgroup_memory_limit_bytes"], 8589934592)
        self.assertEqual(resources["cpu_stat"]["throttled_usec"], 123)

    def test_cgroup_v1_unlimited_sentinels_keep_the_explicit_task_grant(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(os, "cpu_count", return_value=14):
            root = Path(temporary)
            (root / "cpu").mkdir()
            (root / "memory").mkdir()
            (root / "cpu/cpu.cfs_quota_us").write_text("-1\n")
            (root / "cpu/cpu.cfs_period_us").write_text("100000\n")
            (root / "memory/memory.limit_in_bytes").write_text("9223372036854771712\n")
            resources = native_linux.resource_snapshot(root)
        self.assertIsNone(resources["cgroup_cpu_quota"])
        self.assertIsNone(resources["cgroup_memory_limit_bytes"])
        self.assertEqual(resources["usable_cpus"], 4)
        self.assertEqual(resources["child_parallelism"], 3)

    def test_existing_or_overlapping_home_is_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.mkdir()
            home = root / "home"
            artifacts = root / "artifacts"
            native_linux.validate_paths(home, artifacts, source)
            self.assertFalse(home.exists())
            self.assertFalse(artifacts.exists())
            home.mkdir()
            with self.assertRaisesRegex(RuntimeError, "fresh"):
                native_linux.validate_paths(home, artifacts, source)
            with self.assertRaisesRegex(RuntimeError, "source tree"):
                native_linux.validate_paths(source / "home", artifacts, source)
            with self.assertRaisesRegex(RuntimeError, "overlap"):
                native_linux.validate_paths(root / "other", root / "other/artifacts", source)

    def test_environment_drops_credentials_and_installed_prefixes(self):
        with mock.patch.dict(os.environ, {"GLM_API_TOKEN": "synthetic", "PIXI_HOME": "/old/pixi",
                                          "BASH_ENV": "/old/bash", "HTTP_PROXY": "http://example.invalid:9000"}, clear=True):
            environment = native_linux.clean_environment(Path("/task/home"), Path("/task/tmp"))
        self.assertNotIn("GLM_API_TOKEN", environment)
        self.assertNotIn("PIXI_HOME", environment)
        self.assertNotIn("BASH_ENV", environment)
        self.assertEqual(environment["HTTP_PROXY"], "http://example.invalid:9000")
        self.assertEqual(environment["HOME"], "/task/home")


@unittest.skipUnless(os.name == "posix", "Linux gate process groups require POSIX")
class LinuxCommandBoundsTests(unittest.TestCase):
    def test_verbose_output_is_bounded_and_keeps_the_failure_tail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = []
            log = root / "command.log"
            with mock.patch.object(native_linux, "LOG_LIMIT", 128):
                output = native_linux.run(
                    [sys.executable, "-c", "print('x' * 4096); print('last diagnostic')"],
                    env=dict(os.environ), cwd=root, timeout=10, log=log, records=records)
            self.assertIn("last diagnostic", output)
            self.assertLess(len(output.encode()), 129)
            self.assertLess(log.stat().st_size, 200)
            self.assertTrue(records[0]["log_truncated"])
            self.assertGreater(records[0]["output_bytes"], 4096)

    def test_timeout_stops_a_redirected_grandchild_that_ignores_term(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            heartbeat = root / "heartbeat"
            pid_file = root / "child.pid"
            child = ("import os,signal,time; from pathlib import Path; "
                     "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                     f"Path({str(pid_file)!r}).write_text(str(os.getpid())); "
                     f"target=Path({str(heartbeat)!r}); "
                     "exec('while True:\\n target.write_text(str(time.time()))\\n time.sleep(0.02)')")
            parent = ("import subprocess,sys,time; "
                      f"subprocess.Popen([sys.executable,'-c',{child!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                      "time.sleep(30)")
            records = []
            try:
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    native_linux.run([sys.executable, "-c", parent], env=dict(os.environ), cwd=root,
                                     timeout=1, log=root / "timeout.log", records=records)
                self.assertTrue(heartbeat.exists(), "fixture child never started")
                before = heartbeat.read_bytes()
                time.sleep(0.1)
                self.assertEqual(heartbeat.read_bytes(), before)
                self.assertTrue(records[0]["timed_out"])
            finally:
                if pid_file.exists():
                    try:
                        os.kill(int(pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
