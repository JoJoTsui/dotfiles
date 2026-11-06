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

    def test_jsonc_configs_and_generated_metadata_fingerprints_retain_exact_bytes(self):
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
            self.assertNotEqual(first, native_linux.snapshot_fingerprint(trampoline, home))

    def test_strict_snapshot_keeps_executable_bytes_and_skills_but_excludes_generated_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            metadata = home / ".pixi/bin/trampoline_configuration/nu.json"
            skill = home / ".minimax/skills/example/SKILL.md"
            for path in (metadata, skill):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            with mock.patch.object(native_linux, "source_managed_paths", return_value=set()), \
                    mock.patch.object(native_linux, "snapshot_fingerprint", return_value={"sha256": "fixture"}):
                snapshot = native_linux.snapshot(home, {"packages": [{"exposed": {"nu": "nu"}}], "agentPackages": []})
            self.assertNotIn(str(metadata.relative_to(home)), snapshot)
            self.assertIn(".pixi/bin/nu", snapshot)
            self.assertIn(str(skill.relative_to(home)), snapshot)
            executable = home / ".pixi/bin/nu"
            executable.write_bytes(b"first executable bytes")
            first = native_linux.snapshot_fingerprint(executable, home)
            executable.write_bytes(b"changed executable bytes")
            self.assertNotEqual(first, native_linux.snapshot_fingerprint(executable, home))

    def trampoline_fixture(self, home):
        registry = home / ".pixi/manifests/pixi-global.toml"
        registry.parent.mkdir(parents=True)
        registry.write_text('version = 1\n[envs.nushell]\nexposed = { nu = "nu" }\n')
        executable = home / ".pixi/envs/nushell/bin/nu"
        executable.parent.mkdir(parents=True)
        executable.write_text("synthetic executable")
        executable.chmod(0o755)
        metadata = home / ".pixi/bin/trampoline_configuration/nu.json"
        metadata.parent.mkdir(parents=True)
        values = {"exe": str(executable), "env": {"NU_LIB_DIRS": "initial"}, "path_diff": "initial-path"}
        metadata.write_text(json.dumps(values))
        plan = {"packages": [{"environment": "nushell", "exposed": {"nu": "nu"}}]}
        return metadata, values, plan

    def test_generated_activation_changes_are_captured_without_requiring_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            metadata, values, plan = self.trampoline_fixture(home)
            key = str(metadata.relative_to(home))
            before = native_linux.trampoline_metadata(home, plan)
            values["env"]["NU_LIB_DIRS"] = "reapplied"
            values["path_diff"] = "reapplied-path"
            metadata.write_text(json.dumps(values))
            after = native_linux.trampoline_metadata(home, plan)
            self.assertEqual(after[key]["values"], values)
            self.assertNotEqual(before[key]["values"], after[key]["values"])
            self.assertNotEqual(before[key]["sha256"], after[key]["sha256"])

    def test_generated_metadata_rejects_wrong_owned_prefix_missing_and_nonexecutable_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            metadata, values, plan = self.trampoline_fixture(home)
            other = home / ".pixi/envs/other/bin/nu"
            other.parent.mkdir(parents=True)
            other.write_text("another environment")
            other.chmod(0o755)
            nonexecutable = home / ".pixi/envs/nushell/bin/no-execute"
            nonexecutable.write_text("not executable")
            nonexecutable.chmod(0o644)
            for target in (other, nonexecutable, nonexecutable.with_name("missing")):
                with self.subTest(target=target):
                    values["exe"] = str(target)
                    metadata.write_text(json.dumps(values))
                    with self.assertRaisesRegex(RuntimeError, "outside its owned prefix"):
                        native_linux.trampoline_metadata(home, plan)


class LinuxOwnedSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-owned-snapshot-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "device with spaces"
        self.source = self.root / "source"
        payload = self.source / "deployment/agent-payload/targets.tsv"
        payload.parent.mkdir(parents=True)
        payload.write_text("file|RTK.md|.agents/RTK.md\nfile|CLIENTS.md|.agents/CLIENTS.md\n"
                           "block|AGENTS.md|.codex/AGENTS.md\nretire|AGENTS.md|.retired/AGENTS.md\n"
                           "tree|skills|.agents/skills\n")
        clients = self.source / "deployment/client-settings/targets.tsv"
        clients.parent.mkdir(parents=True)
        clients.write_text("yaml|client.yaml|.caveman/caveman.yaml|client\n")
        self.source_patch = mock.patch.object(native_linux, "SOURCE", self.source)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.owned = tuple(str(Path(name)) for name in (
            ".config/atuin/config.toml", ".gitconfig", ".agents/RTK.md", ".agents/CLIENTS.md",
            ".codex/AGENTS.md", ".caveman/caveman.yaml", ".agents/skills/demo/SKILL.md"))
        for relative in self.owned:
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("original configuration\n")
        binary = self.home / ".local/bin/chezmoi"
        binary.parent.mkdir(parents=True)
        binary.write_text("fixture manager")
        query = mock.patch.object(native_linux.subprocess, "run", return_value=mock.Mock(
            stdout=b".config/atuin/config.toml\0.gitconfig\0"))
        self.query = query.start()
        self.addCleanup(query.stop)
        self.plan = {"packages": [], "agentPackages": []}

    def test_source_inventory_uses_the_isolated_boundary_and_lists_missing_targets(self):
        target = self.home / ".config/atuin/config.toml"
        target.unlink()
        self.assertIn(target, native_linux.source_managed_paths(self.home))
        arguments = self.query.call_args.args[0]
        for flag, expected in (("--source", self.source), ("--destination", self.home),
                               ("--config", self.home / ".config/chezmoi/chezmoi.toml"),
                               ("--cache", self.home / ".cache/chezmoi"),
                               ("--persistent-state", self.home / ".config/chezmoi/chezmoistate.boltdb")):
            self.assertEqual(arguments[arguments.index(flag) + 1], str(expected))
        self.assertEqual(arguments[-4:], ["managed", "--include=files", "--path-style=relative", "--nul-path-separator"])

    def test_changes_to_source_payload_and_merged_owned_configuration_change_snapshot(self):
        before = native_linux.snapshot(self.home, self.plan)
        self.assertTrue(set(self.owned).issubset(before))
        self.assertNotIn(str(Path(".retired/AGENTS.md")), before)
        for relative in self.owned:
            with self.subTest(path=relative):
                path = self.home / relative
                original = path.read_bytes()
                path.write_text("altered configuration\n")
                after = native_linux.snapshot(self.home, self.plan)
                self.assertNotEqual(before[relative], after[relative])
                path.write_bytes(original)

    def test_removed_source_owned_configuration_fails_instead_of_disappearing_from_snapshot(self):
        (self.home / ".config/atuin/config.toml").unlink()
        with self.assertRaises(RuntimeError) as caught:
            native_linux.snapshot(self.home, self.plan)
        self.assertIn(str(Path(".config/atuin/config.toml")), str(caught.exception))

    def test_owned_configuration_mode_changes_are_recorded(self):
        path = self.home / ".agents/RTK.md"
        path.chmod(0o600)
        before = native_linux.snapshot(self.home, self.plan)
        path.chmod(0o644)
        after = native_linux.snapshot(self.home, self.plan)
        self.assertNotEqual(before[str(Path(".agents/RTK.md"))], after[str(Path(".agents/RTK.md"))])

    def test_source_inventory_rejects_paths_outside_the_selected_home(self):
        for name in (b"../outside\0", b"/outside\0"):
            with self.subTest(name=name):
                self.query.return_value.stdout = name
                with self.assertRaisesRegex(RuntimeError, "invalid source-owned path"):
                    native_linux.source_managed_paths(self.home)


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

    def test_deterministic_environment_borrows_tools_without_device_state_or_install_opt_ins(self):
        tools = {
            "HOME": "/task/installed home", "PATH": "/task/installed home/.bun/bin:/usr/bin",
            "PIXI_HOME": "/task/installed home/.pixi", "BUN_INSTALL": "/task/installed home/.bun",
            "CARGO_HOME": "/task/installed home/.cargo", "RUSTUP_HOME": "/task/installed home/.rustup",
            "XDG_CONFIG_HOME": "/task/installed home/.config", "ATUIN_CONFIG_DIR": "/task/installed home/.config/atuin",
            "CODEX_HOME": "/task/installed home/.codex", "LD_LIBRARY_PATH": "/task/installed home/lib",
            "DOTFILES_TEST_NODE": "/task/installed home/.pixi/bin/node",
            "DOTFILES_TEST_ZSH": "/task/installed home/.pixi/bin/zsh",
            "DOTFILES_TEST_TOOL_HOME": "/task/installed home",
            "DOTFILES_TEST_ROLE": "remote-compute", "DOTFILES_TEST_PLATFORM": "linux",
            "DOTFILES_TEST_INSTALL": "1", "DOTFILES_TEST_AGENT_INSTALL": "1",
        }
        with mock.patch.dict(os.environ, tools, clear=True):
            environment = native_linux.deterministic_environment(Path("/task/control"), Path("/task/tmp"), tools)
        self.assertEqual(environment["HOME"], "/task/control")
        self.assertEqual(environment["PATH"], "/usr/bin:/bin:/usr/sbin:/sbin")
        self.assertEqual({name: value for name, value in environment.items() if name.startswith("DOTFILES_TEST_")},
                         {name: tools[name] for name in ("DOTFILES_TEST_NODE", "DOTFILES_TEST_ZSH", "DOTFILES_TEST_TOOL_HOME")})
        for name in ("PIXI_HOME", "BUN_INSTALL", "CARGO_HOME", "RUSTUP_HOME", "XDG_CONFIG_HOME",
                     "ATUIN_CONFIG_DIR", "CODEX_HOME", "LD_LIBRARY_PATH"):
            self.assertNotIn(name, environment)


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
