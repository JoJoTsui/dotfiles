"""Gateway lifecycle paths must preserve pre-existing device files."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

if __package__:
    from .fixtures.magpie_engine import install_engine_shim
else:
    from fixtures.magpie_engine import install_engine_shim

SOURCE = Path(__file__).resolve().parents[1]
COMMAND = SOURCE / "dot_local/bin/executable_dotfiles-magpie"
ENGINE = SOURCE / "deployment/magpie.sh"
LIFECYCLE = Path(".local/state/dotfiles/magpie/gateway")
PID_FILE = LIFECYCLE / "gateway.pid"
LOG_FILE = LIFECYCLE / "gateway.log"


class MagpieRuntimePathSafetyTests(unittest.TestCase):
    def run_command(self, command, environment):
        return subprocess.run(["/bin/bash", str(COMMAND), command], env=environment,
                              capture_output=True, text=True, timeout=30, check=False)

    def base_environment(self, home, **extra):
        # The command's guard resolves the platform and the account home
        # natively; a fake CLI under a synthetic HOME needs the test shim.
        shim = install_engine_shim(home, name="magpie-engine-shim.sh")
        environment = {"HOME": str(home), "PATH": "/usr/bin:/bin",
                       "DEPLOY_PLATFORM": "linux", "DOTFILES_MAGPIE_ENGINE": str(shim)}
        environment.update(extra)
        return environment

    def refusing_cli(self, home):
        """A CLI that never answers and records whether serve was attempted."""
        served = home / "served"
        cli = home / "magpie-fake"
        cli.write_text("#!/bin/sh\ncase \"$1\" in\n"
                       "  status) printf '{\"running\":false}\\n' ;;\n"
                       "  serve) printf served > \"$MAGPIE_SERVED\"; printf 'gateway output\\n' >&2; exit 1 ;;\n"
                       "esac\n", encoding="utf-8")
        cli.chmod(0o755)
        environment = self.base_environment(
            home, MAGPIE_CLI_BIN=str(cli), MAGPIE_SERVED=str(served),
            MAGPIE_START_ATTEMPTS="1")
        return environment, served

    def fingerprint(self, pid):
        """The engine's own identity of a process (the value stored at start)."""
        script = ("source " + repr(str(ENGINE)) + "\n"
                  "magpie_process_fingerprint " + str(pid) + "\n")
        result = subprocess.run(["/bin/bash", "-c", script], capture_output=True,
                                text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), "the process has no fingerprint")
        return result.stdout.strip()

    def test_start_does_not_append_through_a_device_log_symlink(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-log-") as temporary:
            home = Path(temporary)
            directory = home / LIFECYCLE
            directory.mkdir(parents=True)
            sentinel = home / "device-file"
            sentinel.write_text("preserve device data", encoding="utf-8")
            log = directory / "gateway.log"
            log.symlink_to(sentinel)
            environment, served = self.refusing_cli(home)
            result = self.run_command("start", environment)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("symlink", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve device data")
            self.assertTrue(log.is_symlink())
            self.assertFalse(served.exists(), "start ran serve through a device symlink")

    def test_start_does_not_write_through_a_device_pid_symlink(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-pid-") as temporary:
            home = Path(temporary)
            directory = home / LIFECYCLE
            directory.mkdir(parents=True)
            sentinel = home / "device-file"
            sentinel.write_text("preserve device data", encoding="utf-8")
            pid = directory / "gateway.pid"
            pid.symlink_to(sentinel)
            environment, served = self.refusing_cli(home)
            result = self.run_command("start", environment)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("symlink", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve device data")
            self.assertTrue(pid.is_symlink())
            self.assertFalse((directory / "gateway.log").exists())
            self.assertFalse(served.exists(), "start ran serve through a device symlink")

    def test_start_rejects_a_dangling_log_symlink(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-dangling-") as temporary:
            home = Path(temporary)
            directory = home / LIFECYCLE
            directory.mkdir(parents=True)
            target = home / "missing-target"
            log = directory / "gateway.log"
            log.symlink_to(target)
            environment, served = self.refusing_cli(home)
            result = self.run_command("start", environment)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("symlink", result.stderr)
            self.assertTrue(log.is_symlink())
            self.assertFalse(target.exists(), "start created the dangling link's target")
            self.assertFalse(served.exists(), "start ran serve through a dangling link")

    def test_start_rejects_a_symlinked_lifecycle_parent(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-parent-") as temporary:
            home = Path(temporary)
            (home / ".local").mkdir()
            device_state = home / "device-state"
            device_state.mkdir()
            state = home / ".local/state"
            state.symlink_to(device_state, target_is_directory=True)
            environment, served = self.refusing_cli(home)
            result = self.run_command("start", environment)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("symlink", result.stderr)
            self.assertTrue(state.is_symlink())
            self.assertEqual(list(device_state.iterdir()), [],
                             "start wrote through a symlinked lifecycle parent")
            self.assertFalse(served.exists(), "start ran serve through a device symlink")

    def test_stop_does_not_signal_or_remove_a_device_pid_symlink(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-stop-link-") as temporary:
            home = Path(temporary)
            directory = home / LIFECYCLE
            directory.mkdir(parents=True)
            other = subprocess.Popen(["/bin/sleep", "60"])
            try:
                content = "%s\n%s\n" % (other.pid, self.fingerprint(other.pid))
                sentinel = home / "device-pid-file"
                sentinel.write_text(content, encoding="utf-8")
                pid = directory / "gateway.pid"
                pid.symlink_to(sentinel)
                result = self.run_command("stop", self.base_environment(home))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("symlink", result.stderr)
                self.assertIsNone(other.poll(), "stop signalled a process named by a device symlink")
                self.assertTrue(pid.is_symlink())
                self.assertEqual(sentinel.read_text(encoding="utf-8"), content)
            finally:
                if other.poll() is None:
                    other.terminate()
                other.wait(timeout=10)

    def test_start_preserves_an_unrecognized_regular_pid_file(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-pid-regular-") as temporary:
            home = Path(temporary)
            directory = home / LIFECYCLE
            directory.mkdir(parents=True)
            # A regular pid file this deployment never wrote: a pid for a
            # process that does not exist and an ownership token we did not
            # record. Start must leave these device-owned bytes where they are.
            pid = directory / "gateway.pid"
            original = b"99999999\nnot-a-deployment-token\n"
            pid.write_bytes(original)
            environment, _served = self.refusing_cli(home)
            self.run_command("start", environment)
            self.assertTrue(pid.is_file(), "start removed an unrecognized regular pid file")
            self.assertFalse(pid.is_symlink())
            self.assertEqual(pid.read_bytes(), original,
                             "start replaced or rewrote an unrecognized regular pid file")
            extra_pids = [entry for entry in directory.iterdir()
                          if entry != pid and entry.name.startswith("gateway.")
                          and entry.name.endswith(".pid")]
            self.assertEqual(extra_pids, [], "start launched under a separate pid name")

    def test_start_preserves_an_unrecognized_regular_log_bytes(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-log-regular-") as temporary:
            home = Path(temporary)
            directory = home / LIFECYCLE
            directory.mkdir(parents=True)
            # A regular gateway log this deployment never wrote. Start must not
            # append the fake gateway's output to it or rewrite its bytes.
            log = directory / "gateway.log"
            original = b"device gateway log bytes\nsecond device line\n"
            log.write_bytes(original)
            environment, _served = self.refusing_cli(home)
            self.run_command("start", environment)
            self.assertTrue(log.is_file(), "start removed an unrecognized regular log file")
            self.assertFalse(log.is_symlink())
            self.assertEqual(log.read_bytes(), original,
                             "start appended to or rewrote an unrecognized regular log file")

    def test_stop_preserves_an_unrecognized_numeric_stale_pid_file(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-stale-pid-") as temporary:
            home = Path(temporary)
            directory = home / LIFECYCLE
            directory.mkdir(parents=True)
            # An out-of-range pid that names no process, so no signal can reach
            # an unrelated one. Stop must not delete a numeric stale pid file
            # merely because nothing answers to that pid.
            pid = directory / "gateway.pid"
            original = b"99999999\n"
            pid.write_bytes(original)
            self.run_command("stop", self.base_environment(home))
            self.assertTrue(pid.is_file(), "stop deleted an unrecognized numeric stale pid file")
            self.assertFalse(pid.is_symlink())
            self.assertEqual(pid.read_bytes(), original,
                             "stop rewrote an unrecognized numeric stale pid file")

    def test_restart_preserves_regular_log_and_keeps_canonical_pid(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-restart-") as temporary:
            home = Path(temporary)
            tools = home / "tools"
            tools.mkdir()
            marker = home / "ready-marker"
            cli = tools / "magpie-fake"
            cli.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  status)\n"
                "    if [ -f \"$MAGPIE_FAKE_READY\" ]; then\n"
                "      echo '{\"running\":true,\"gateway\":\"http://127.0.0.1:3425\"}'\n"
                "    else\n"
                "      echo '{\"running\":false}'\n"
                "    fi\n"
                "    ;;\n"
                "  serve) : > \"$MAGPIE_FAKE_READY\"; exec sleep 60 ;;\n"
                "  *) exit 0 ;;\n"
                "esac\n", encoding="utf-8")
            cli.chmod(0o755)
            environment = self.base_environment(
                home, MAGPIE_CLI_BIN=str(cli), MAGPIE_FAKE_READY=str(marker),
                MAGPIE_START_ATTEMPTS="1", MAGPIE_STOP_ATTEMPTS="1")
            directory = home / LIFECYCLE
            pid_file = directory / "gateway.pid"
            log = directory / "gateway.log"
            recorded = []
            try:
                first = self.run_command("start", environment)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                first_pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
                recorded.append(first_pid)
                # The first run's log is a regular file; mark its bytes so an
                # append or rewrite on restart is detectable.
                original = b"device gateway log bytes\n"
                log.write_bytes(original)
                stopped = self.run_command("stop", environment)
                self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
                self.assertFalse(pid_file.exists())
                self.assertEqual(log.read_bytes(), original)
                marker.unlink()  # force the restart to actually launch a process
                second = self.run_command("start", environment)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertIn("the gateway answers", second.stdout)
                self.assertTrue(pid_file.is_file())
                second_pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
                recorded.append(second_pid)
                self.assertNotEqual(second_pid, first_pid)
                self.assertEqual(log.read_bytes(), original,
                                 "restart rewrote or appended to the preserved log")
                fresh_logs = [entry for entry in directory.iterdir()
                              if entry != log and entry.name.startswith("gateway.")
                              and entry.name.endswith(".log")]
                self.assertEqual(len(fresh_logs), 1,
                                 "restart must append to one unique freshly created log")
                self.assertTrue(fresh_logs[0].is_file())
                # stop still finds the process through the canonical pid.
                second_stop = self.run_command("stop", environment)
                self.assertEqual(second_stop.returncode, 0,
                                 second_stop.stdout + second_stop.stderr)
                self.assertIn("the gateway process %s is stopped" % second_pid,
                              second_stop.stdout)
                self.assertFalse(pid_file.exists())
                self.assertEqual(log.read_bytes(), original)
            finally:
                for pid in recorded:
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass

    def test_start_and_stop_a_normal_gateway(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-normal-") as temporary:
            home = Path(temporary)
            tools = home / "tools"
            tools.mkdir()
            marker = home / "ready-marker"
            cli = tools / "magpie-fake"
            cli.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  status)\n"
                "    if [ -f \"$MAGPIE_FAKE_READY\" ]; then\n"
                "      echo '{\"running\":true,\"gateway\":\"http://127.0.0.1:3425\"}'\n"
                "    else\n"
                "      echo '{\"running\":false}'\n"
                "    fi\n"
                "    ;;\n"
                "  serve) : > \"$MAGPIE_FAKE_READY\"; exec sleep 60 ;;\n"
                "  *) exit 0 ;;\n"
                "esac\n", encoding="utf-8")
            cli.chmod(0o755)
            environment = self.base_environment(
                home, MAGPIE_CLI_BIN=str(cli), MAGPIE_FAKE_READY=str(marker),
                MAGPIE_START_ATTEMPTS="1", MAGPIE_STOP_ATTEMPTS="1")
            pid_file = home / PID_FILE
            try:
                started = self.run_command("start", environment)
                self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
                self.assertIn("the gateway answers", started.stdout)
                self.assertTrue(pid_file.is_file())
                recorded = pid_file.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(recorded), 2, "start must record a pid and an ownership token")
                self.assertTrue(recorded[0].isdigit())
                stopped = self.run_command("stop", environment)
                self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
                self.assertIn("the gateway process %s is stopped" % recorded[0], stopped.stdout)
                self.assertFalse(pid_file.exists())
            finally:
                if pid_file.is_file():
                    recorded = pid_file.read_text(encoding="utf-8").splitlines()
                    if recorded and recorded[0].isdigit():
                        try:
                            os.kill(int(recorded[0]), 9)
                        except ProcessLookupError:
                            pass


if __name__ == "__main__":
    unittest.main()
