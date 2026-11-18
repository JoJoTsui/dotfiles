"""The public Magpie lifecycle must not affect a device-owned process."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

if __package__:
    from .fixtures.magpie_engine import install_engine_shim
else:
    from fixtures.magpie_engine import install_engine_shim

SOURCE = Path(__file__).resolve().parents[1]
COMMAND = SOURCE / "dot_local/bin/executable_dotfiles-magpie"
ENGINE = SOURCE / "deployment/magpie.sh"
PID_FILE = ".local/state/dotfiles/magpie/gateway/gateway.pid"


class MagpieProcessSafetyTests(unittest.TestCase):
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

    def fingerprint(self, pid):
        """The engine's own identity of a process (the value stored at start)."""
        script = ("source " + repr(str(ENGINE)) + "\n"
                  "magpie_process_fingerprint " + str(pid) + "\n")
        result = subprocess.run(["/bin/bash", "-c", script], capture_output=True,
                                text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), "the process has no fingerprint")
        return result.stdout.strip()

    def test_install_does_not_follow_a_preexisting_download_symlink(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-download-") as temporary:
            home = Path(temporary)
            cache = home / ".cache/dotfiles/magpie"
            cache.mkdir(parents=True)
            sentinel = home / "device-file"
            sentinel.write_text("preserve device data", encoding="utf-8")
            predictable = cache / "magpie-cli-0.1.4404-linux-amd64.part"
            predictable.symlink_to(sentinel)
            unrelated = cache / "unrelated-cache-entry"
            unrelated.write_text("keep me", encoding="utf-8")
            tools = home / "tools"
            tools.mkdir()
            curl_log = home / "curl-output"
            curl = tools / "curl"
            curl.write_text(
                "#!/bin/sh\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = -o ]; then shift; output=$1; fi\n"
                "  shift\n"
                "done\n"
                "printf '%s\\n' \"$output\" > \"$MAGPIE_TEST_CURL_LOG\"\n"
                "printf bad-payload > \"$output\"\n", encoding="utf-8")
            curl.chmod(0o755)
            catalog = home / "releases.tsv"
            catalog.write_text("magpie|0.1.4404|linux-amd64|https://example.invalid/asset|"
                               + "0" * 64 + "\n", encoding="utf-8")
            environment = self.base_environment(
                home, PATH=f"{tools}:/usr/bin:/bin", DEPLOY_ARCH="x86_64",
                MAGPIE_RELEASE_CATALOG=str(catalog),
                MAGPIE_TEST_CURL_LOG=str(curl_log))
            result = self.run_command("install", environment)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve device data")
            # The predictable cache path and unrelated entries are left alone.
            self.assertTrue(predictable.is_symlink())
            self.assertTrue(os.path.samefile(predictable, sentinel))
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me")
            # The download went to a private, unique location, not the cache.
            output = Path(curl_log.read_text(encoding="utf-8").strip())
            self.assertTrue(output.name)
            self.assertNotEqual(output, predictable)
            self.assertNotEqual(output.parent, cache)
            self.assertTrue(output.parent.name.startswith("magpie-download."))

    def test_stop_does_not_kill_an_unrelated_process_from_a_stale_pid_file(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-pid-") as temporary:
            home = Path(temporary)
            pid_file = home / PID_FILE
            pid_file.parent.mkdir(parents=True)
            other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            try:
                # A stale pid file has no ownership fingerprint. Stop must fail
                # closed, not signal a process it cannot prove it started.
                pid_file.write_text(str(other.pid) + "\n", encoding="utf-8")
                result = self.run_command("stop", self.base_environment(home))
                self.assertIsNone(other.poll(), "a stale Magpie PID killed an unrelated process")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("is stopped", result.stdout)
            finally:
                if other.poll() is None:
                    other.terminate()
                other.wait(timeout=10)

    def test_stop_does_not_signal_unrelated_process_from_gateway_backup_pid(self):
        """A device-owned backup PID record is never read, signalled, or removed."""
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-backup-pid-") as temporary:
            home = Path(temporary)
            pid_file = home / PID_FILE
            pid_file.parent.mkdir(parents=True)
            other = subprocess.Popen(["/bin/sleep", "60"])
            try:
                # A real process with its real start fingerprint: exactly the
                # shape the old gateway*.pid scan mistook for an owned gateway.
                content = "%s\n%s\n" % (other.pid, self.fingerprint(other.pid))
                backup = pid_file.parent / "gateway-backup.pid"
                backup.write_text(content, encoding="utf-8")
                # No canonical gateway.pid exists, so there is nothing to stop.
                result = self.run_command("stop", self.base_environment(home))
                self.assertIsNone(
                    other.poll(), "stop signalled an unrelated process named by gateway-backup.pid")
                self.assertTrue(backup.is_file(), "stop removed gateway-backup.pid")
                self.assertEqual(backup.read_text(encoding="utf-8"), content,
                                 "stop rewrote gateway-backup.pid")
                self.assertNotIn("is stopped", result.stdout)
            finally:
                if other.poll() is None:
                    other.terminate()
                other.wait(timeout=10)

    def test_malformed_gateway_backup_pid_does_not_block_stop(self):
        """A malformed unrelated PID file cannot block stopping an owned gateway."""
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-malformed-backup-") as temporary:
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
                owned_pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
                backup = pid_file.parent / "gateway-backup.pid"
                original = "not-a-pid\nnot-a-fingerprint\n"
                backup.write_text(original, encoding="utf-8")
                result = self.run_command("stop", environment)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("the gateway process %s is stopped" % owned_pid, result.stdout)
                self.assertFalse(pid_file.exists())
                self.assertEqual(backup.read_text(encoding="utf-8"), original,
                                 "stop rewrote the malformed backup PID file")
            finally:
                if pid_file.is_file():
                    recorded = pid_file.read_text(encoding="utf-8").splitlines()
                    if recorded and recorded[0].isdigit():
                        try:
                            os.kill(int(recorded[0]), 9)
                        except ProcessLookupError:
                            pass

    def test_start_records_ownership_and_stop_stops_only_that_process(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-owned-") as temporary:
            home = Path(temporary)
            tools = home / "tools"
            tools.mkdir()
            marker = home / "ready-marker"
            cli = tools / "magpie-fake"
            cli.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  --version) echo 'magpie 0.1.4404' ;;\n"
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
                self.assertTrue(pid_file.is_file())
                lines = pid_file.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(lines), 2, "start must record a pid and an ownership token")
                self.assertTrue(lines[0].isdigit())
                self.assertEqual(lines[1], self.fingerprint(int(lines[0])))
                stopped = self.run_command("stop", environment)
                self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
                self.assertIn("the gateway process %s is stopped" % lines[0], stopped.stdout)
                self.assertFalse(pid_file.exists())
            finally:
                if pid_file.is_file():
                    recorded = pid_file.read_text(encoding="utf-8").splitlines()
                    if recorded and recorded[0].isdigit():
                        try:
                            os.kill(int(recorded[0]), 9)
                        except ProcessLookupError:
                            pass

    def test_start_keeps_the_record_of_a_live_unready_gateway(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-unready-") as temporary:
            home = Path(temporary)
            cli = home / "magpie-fake"
            cli.write_text(
                '#!/bin/sh\ncase "$1" in\n'
                '  status) printf \'{"running":false}\\n\' ;;\n'
                '  serve) exec sleep 60 ;;\n'
                'esac\n', encoding="utf-8")
            cli.chmod(0o755)
            environment = self.base_environment(
                home, MAGPIE_CLI_BIN=str(cli), MAGPIE_START_ATTEMPTS="1")
            pid_file = home / PID_FILE
            recorded = set()
            try:
                first = self.run_command("start", environment)
                self.assertNotEqual(first.returncode, 0)
                first_record = pid_file.read_text(encoding="utf-8")
                recorded.add(int(first_record.splitlines()[0]))
                second = self.run_command("start", environment)
                second_record = pid_file.read_text(encoding="utf-8")
                recorded.add(int(second_record.splitlines()[0]))
                self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertEqual(second_record, first_record,
                                 "start replaced the record of a live unready process")
            finally:
                for pid in recorded:
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass

    def test_stop_does_not_claim_stopped_when_the_process_survives(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-stubborn-") as temporary:
            home = Path(temporary)
            pid_file = home / PID_FILE
            pid_file.parent.mkdir(parents=True)
            stubborn = subprocess.Popen(
                [sys.executable, "-c",
                 "import signal, sys, time\n"
                 "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                 "print('ready', flush=True)\n"
                 "time.sleep(60)"],
                stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(stubborn.stdout.readline().strip(), "ready")
                pid_file.write_text(
                    "%s\n%s\n" % (stubborn.pid, self.fingerprint(stubborn.pid)), encoding="utf-8")
                result = self.run_command("stop", self.base_environment(home, MAGPIE_STOP_ATTEMPTS="1"))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("is stopped", result.stdout)
                self.assertIn("still running", result.stderr)
                self.assertIsNone(stubborn.poll(), "the surviving process must be left untouched")
                self.assertTrue(pid_file.exists(), "the pid file is kept for diagnosis")
            finally:
                if stubborn.poll() is None:
                    stubborn.kill()
                stubborn.wait(timeout=10)
                stubborn.stdout.close()


if __name__ == "__main__":
    unittest.main()
