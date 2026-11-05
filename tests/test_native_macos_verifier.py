"""Native-verifier safety checks without installation or live device state."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import native_macos


class NativeVerifierTimeoutTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "process-group cleanup requires POSIX")
    def test_timeout_stops_a_writing_grandchild_with_redirected_output(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-verifier-timeout-") as temporary:
            root = Path(temporary)
            heartbeat = root / "heartbeat"
            child_pid = root / "child.pid"
            parent_pid = root / "parent.pid"
            grandchild = root / "writer.py"
            grandchild.write_text(
                "import os, pathlib, signal, sys, time\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "pathlib.Path(sys.argv[2]).write_text(str(os.getpid()))\n"
                "while True:\n"
                "    with open(sys.argv[1], 'ab', buffering=0) as stream:\n"
                "        stream.write(b'heartbeat\\n')\n"
                "    time.sleep(0.02)\n")
            parent = root / "parent.py"
            parent.write_text(
                "import os, pathlib, subprocess, sys, time\n"
                "pathlib.Path(sys.argv[4]).write_text(str(os.getpid()))\n"
                "subprocess.Popen([sys.executable, *sys.argv[1:4]],\n"
                "                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "time.sleep(300)\n")

            def cleanup_processes():
                # Cleanup also runs if the timeout assertion or heartbeat check
                # fails, before TemporaryDirectory removes a writer's paths.
                for path, kill in ((parent_pid, os.killpg), (child_pid, os.kill)):
                    if path.exists():
                        try:
                            kill(int(path.read_text()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass

            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    native_macos.run(
                        [sys.executable, str(parent), str(grandchild),
                         str(heartbeat), str(child_pid), str(parent_pid)],
                        env=dict(os.environ), cwd=root, timeout=1)
                self.assertTrue(child_pid.is_file(), "the grandchild must have started")
                self.assertGreater(heartbeat.stat().st_size, 0)
                # Allow pending exit handling to finish, then prove that an
                # orphan is not still writing after the verifier returns.
                time.sleep(0.1)
                stopped_size = heartbeat.stat().st_size
                time.sleep(0.2)
                self.assertEqual(heartbeat.stat().st_size, stopped_size,
                                 "timed-out descendants must stop writing")
            finally:
                cleanup_processes()

    def test_nonpositive_install_timeout_is_rejected_before_creating_fixtures(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-verifier-cli-") as temporary:
            root = Path(temporary)
            environment = dict(os.environ, RUNNER_TEMP=str(root))
            for value in ("0", "-1"):
                with self.subTest(timeout=value):
                    result = subprocess.run(
                        [sys.executable, str(Path(native_macos.__file__).resolve()),
                         "--arch", "aarch64", "--role", "workstation",
                         "--report", str(root / "report.json"),
                         "--install-timeout", value],
                        env=environment, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("--install-timeout must be positive", result.stderr)
                    self.assertEqual(list(root.iterdir()), [])


@unittest.skipUnless(shutil.which("git"), "source identity requires Git")
class NativeVerifierSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-verifier-source-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        home = self.root / "home"
        home.mkdir()
        scratch = self.root / "tmp"
        scratch.mkdir()
        # Exercise real Git while keeping device configuration/global ignores
        # outside these disposable repositories.
        environment = {
            "HOME": str(home), "PATH": os.environ.get("PATH", os.defpath),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "LC_ALL": "C", "TMPDIR": str(scratch),
        }
        isolation = patch.dict(os.environ, environment, clear=True)
        isolation.start()
        self.addCleanup(isolation.stop)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Verifier Fixture")
        self.git("config", "user.email", "verifier@example.invalid")
        (self.source / ".gitignore").write_text("private/\n*.token\n")
        (self.source / "managed.txt").write_text("committed configuration\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "fixture")

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-C", str(self.source), *arguments], stderr=subprocess.PIPE,
            text=True, timeout=10)

    def test_identity_distinguishes_tracked_edits_and_untracked_source(self):
        clean = native_macos.source_state(self.source)
        self.assertEqual(clean["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertFalse(clean["working_tree_dirty"])
        self.assertRegex(clean["source_sha256"], r"^[0-9a-f]{64}$")

        tracked = self.source / "managed.txt"
        original = tracked.read_bytes()
        tracked.write_text("changed configuration\n")
        edited = native_macos.source_state(self.source)
        self.assertEqual(edited["commit"], clean["commit"])
        self.assertTrue(edited["working_tree_dirty"])
        self.assertNotEqual(edited["source_sha256"], clean["source_sha256"])
        tracked.write_bytes(original)
        self.assertEqual(native_macos.source_state(self.source), clean)

        untracked = self.source / "new-source.txt"
        untracked.write_text("uncommitted source also deploys\n")
        added = native_macos.source_state(self.source)
        self.assertEqual(added["commit"], clean["commit"])
        self.assertTrue(added["working_tree_dirty"])
        self.assertNotEqual(added["source_sha256"], clean["source_sha256"])
        untracked.unlink()
        self.assertEqual(native_macos.source_state(self.source), clean)

    def test_ignored_private_files_do_not_enter_source_identity(self):
        clean = native_macos.source_state(self.source)
        secret = self.source / "device.token"
        secret.write_text("synthetic private value\n")
        secret.chmod(0)
        self.addCleanup(secret.chmod, 0o600)
        private = self.source / "private"
        private.mkdir()
        (private / "settings").write_text("synthetic private configuration\n")
        self.assertEqual(native_macos.source_state(self.source), clean)
        secret.chmod(0o600)
        secret.write_text("a different private value must not affect evidence\n")
        (private / "settings").write_text("changed private configuration\n")
        self.assertEqual(native_macos.source_state(self.source), clean)

    @unittest.skipUnless(os.name == "posix", "fixture uses POSIX symlinks")
    def test_outside_symlink_contents_are_not_read_but_link_text_is_identified(self):
        outside = self.root / "outside-device-config"
        outside.write_text("synthetic private device configuration\n")
        link = self.source / "linked-resource"
        link.symlink_to(outside)
        self.git("add", "linked-resource")
        self.git("commit", "--quiet", "-m", "linked source fixture")
        original = native_macos.source_state(self.source)
        self.assertFalse(original["working_tree_dirty"])

        outside.write_text("changed content outside the selected source\n")
        outside.chmod(0)
        self.addCleanup(outside.chmod, 0o600)
        self.assertEqual(native_macos.source_state(self.source), original)

        link.unlink()
        link.symlink_to(self.root / "different-missing-device-config")
        retargeted = native_macos.source_state(self.source)
        self.assertTrue(retargeted["working_tree_dirty"])
        self.assertEqual(retargeted["commit"], original["commit"])
        self.assertNotEqual(retargeted["source_sha256"], original["source_sha256"])


if __name__ == "__main__":
    unittest.main()
