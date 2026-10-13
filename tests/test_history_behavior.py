"""Shared history behavior with synthetic data and separately writable homes."""
import os
from pathlib import Path
import select
import signal
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import time
import unittest
from fixtures.atuin_sync import AtuinSyncFixture

if os.name == "posix":
    import fcntl
    import pty
    import termios

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "native Windows history is verified by its own adapter")
class HistoryBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-history-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        tool_home = os.environ.get("DOTFILES_TEST_TOOL_HOME")
        if not self.chezmoi or not tool_home:
            self.skipTest("history execution requires chezmoi and DOTFILES_TEST_TOOL_HOME with pinned tools")
        self.tool_home = Path(tool_home)
        self.atuin = self.tool_home / ".pixi/envs/atuin/bin/atuin"
        if not self.atuin.is_file():
            self.skipTest("missing borrowed pinned Atuin")
        exposure = self.home / ".pixi/bin/atuin"
        exposure.parent.mkdir(parents=True)
        exposure.symlink_to(self.atuin)
        python = self.tool_home / ".pixi/envs/python/bin/python"
        if not python.is_file():
            self.skipTest("missing borrowed managed Python")
        (self.home / ".pixi/bin/python").symlink_to(python)
        self.shells = {}
        for name, environment in (("bash", "bash"), ("zsh", "zsh"), ("nu", "nushell")):
            binary = self.tool_home / ".pixi/envs" / environment / "bin" / name
            if not binary.is_file():
                self.skipTest(f"missing borrowed shell: {binary}")
            self.shells[name] = str(binary)
            (self.home / ".pixi/bin" / name).symlink_to(binary)
        self.env = {
            "HOME": str(self.home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color",
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "ATUIN_CONFIG_DIR": str(self.home / ".config/atuin"),
            "ATUIN_DATA_DIR": str(self.home / ".local/share/atuin"),
            "ATUIN_SESSION": "0123456789abcdef0123456789abcdef",
        }
        result = subprocess.run([
            "bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
            "--home", str(self.home), "--platform", os.environ.get("DOTFILES_TEST_PLATFORM", "linux"),
            "--role", os.environ.get("DOTFILES_TEST_ROLE", "workstation"), "--apply-only",
        ], env=dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi), cwd=SOURCE,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def history(self, *arguments, input=None):
        return subprocess.run([str(self.home / ".local/bin/dotfiles-history"), *arguments],
                              env=self.env, cwd=self.home, input=input,
                              capture_output=True, text=True, timeout=20)

    def atuin_command(self, *arguments):
        return subprocess.run([str(self.atuin), *arguments], env=self.env, cwd=self.home,
                              capture_output=True, text=True, timeout=20)

    def terminal(self, name, commands, *, arguments=None):
        primary, secondary = pty.openpty()
        fcntl.ioctl(secondary, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
        def terminal_session():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        process = subprocess.Popen(arguments or [self.shells[name]], env=self.env, cwd=self.home,
                                   stdin=secondary, stdout=secondary, stderr=secondary,
                                   preexec_fn=terminal_session)
        os.close(secondary)
        output = bytearray()
        def drain(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                readable, _, _ = select.select([primary], [], [], 0.05)
                if readable:
                    try:
                        chunk = os.read(primary, 65536)
                        output.extend(chunk)
                        if b"\x1b[6n" in chunk:
                            os.write(primary, b"\x1b[1;1R")
                    except OSError:
                        return
        try:
            drain(0.6)
            for command in commands:
                os.write(primary, (command + "\n").encode())
                drain(0.6)
            os.write(primary, b"exit\n")
            drain(0.4)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.fail(output.decode(errors="replace"))
            self.assertEqual(process.returncode, 0, output.decode(errors="replace"))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            os.close(primary)
        return output.decode(errors="replace")

    def setup_device(self, action, prompts):
        primary, secondary = pty.openpty()
        fcntl.ioctl(secondary, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
        def terminal_session():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        process = subprocess.Popen([str(self.home / ".local/bin/dotfiles-history"), action],
                                   env=self.env, cwd=self.home, stdin=secondary,
                                   stdout=secondary, stderr=secondary, preexec_fn=terminal_session)
        os.close(secondary)
        output = bytearray()
        pending = list(prompts)
        # Local registration derives the account key and starts a fresh client;
        # leave headroom for slower CI/compute hosts while keeping hangs bounded.
        deadline = time.monotonic() + 60
        try:
            while time.monotonic() < deadline:
                readable, _, _ = select.select([primary], [], [], 0.05)
                if readable:
                    try:
                        output.extend(os.read(primary, 65536))
                    except OSError:
                        break
                text = output.decode(errors="replace")
                if pending and pending[0][0] in text:
                    _, value = pending.pop(0)
                    os.write(primary, (value + "\n").encode())
                if process.poll() is not None:
                    break
            self.assertEqual(pending, [], output.decode(errors="replace"))
            self.assertEqual(process.poll(), 0, output.decode(errors="replace"))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            os.close(primary)
        return output.decode(errors="replace")

    def test_new_device_reports_pending_activation_without_importing_or_creating_credentials(self):
        native_history = self.home / ".bash_history"
        native_history.write_text("echo synthetic-existing-history\n")
        result = self.history("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pending activation", result.stdout)
        self.assertIn("local history", result.stdout)
        self.assertIn("first-device", result.stdout)
        self.assertIn("join", result.stdout)
        self.assertFalse((self.home / ".local/share/atuin/session").exists())
        self.assertFalse((self.home / ".local/share/atuin/key").exists())
        self.assertFalse((self.home / ".local/share/atuin/history.db").exists())
        self.assertEqual(native_history.read_text(), "echo synthetic-existing-history\n")

    def test_supported_shells_record_and_search_one_local_history_while_filtering_known_secrets(self):
        prepared = subprocess.run([str(self.home / ".local/bin/dotfiles-history-prepare")],
                                  env=self.env, cwd=self.home, capture_output=True, text=True, timeout=20)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        for name in ("bash", "zsh", "nu"):
            command = f"echo portable-{name}-history-token"
            synthetic_secret = "ghp_" + "A" * 36
            secret_command = f"echo filtered-{name}-token-{synthetic_secret}"
            self.terminal(name, [command, secret_command, "echo after-filter-check"])
        search = self.atuin_command("search", "--cmd-only", "--search-mode", "fulltext", "portable-")
        self.assertEqual(search.returncode, 0, search.stderr)
        for name in ("bash", "zsh", "nu"):
            self.assertIn(f"echo portable-{name}-history-token", search.stdout)
        excluded = self.atuin_command("search", "--cmd-only", "--search-mode", "fulltext", "filtered-")
        self.assertEqual(excluded.returncode, 1, excluded.stderr)  # Atuin's no-match status
        self.assertEqual(excluded.stderr, "")
        self.assertEqual(excluded.stdout.strip(), "")
        settings = self.atuin_command("config", "get", "--resolved", "secrets_filter")
        self.assertEqual(settings.stdout.strip(), "true")
        state = self.history("status")
        self.assertIn("pending activation", state.stdout)

    def test_bash_migration_is_explicit_filtered_and_one_time(self):
        fixture = self.root / "bash-import.fixture"
        secret = "ghp_" + "B" * 36
        fixture.write_text(f"#1700000000\necho imported-bash-token\n#1700000001\necho excluded-import-{secret}\n")
        offered = self.history("import")
        self.assertEqual(offered.returncode, 0, offered.stderr)
        self.assertIn("bash", offered.stdout)
        self.assertIn("zsh", offered.stdout)
        self.assertIn("nu-db", offered.stdout)
        before = self.atuin_command("search", "--cmd-only", "imported-bash-token")
        self.assertEqual(before.stdout, "")
        imported = self.history("import", "bash", "--file", str(fixture))
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertNotIn(secret, imported.stdout + imported.stderr)
        self.assertIn("imported-bash-token", self.atuin_command("search", "--cmd-only", "imported-bash-token").stdout)
        timestamp = self.atuin_command("search", "--timezone", "+0", "--format", "{time}", "imported-bash-token")
        self.assertIn("2023-11-14", timestamp.stdout)
        excluded = self.atuin_command("search", "--cmd-only", "excluded-import-")
        self.assertEqual(excluded.stdout, "")
        fixture.write_text(fixture.read_text() + "echo added-after-first-import\n")
        repeated = self.history("import", "bash", "--file", str(fixture))
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn("already imported", repeated.stdout)
        self.assertEqual(self.atuin_command("search", "--cmd-only", "added-after-first-import").stdout, "")

    def test_each_other_shell_format_has_an_explicit_native_filtered_importer(self):
        secret = "ghp_" + "C" * 36
        zsh = self.root / "zsh-import.fixture"
        zsh.write_text(f": 1700000001:0;echo imported-zsh-token\n: 1700000002:0;echo excluded-zsh-{secret}\n")
        nu = self.root / "nu-import.fixture"
        nu.write_text(f"echo imported-nu-token<\\n>echo multiline-token\necho excluded-nu-{secret}\n")
        nu_db = self.root / "nu-sqlite.fixture"
        with sqlite3.connect(nu_db) as connection:
            connection.execute("CREATE TABLE history(id INTEGER, command_line BLOB, start_timestamp INTEGER, "
                               "session_id INTEGER, hostname BLOB, cwd BLOB, duration_ms INTEGER, "
                               "exit_status INTEGER, more_info BLOB)")
            for identifier, command in enumerate((b"echo imported-nu-db-token", f"echo excluded-nu-db-{secret}".encode()), 1):
                connection.execute("INSERT INTO history VALUES(?,?,?,?,?,?,?,?,?)",
                                   (identifier, command, 1700000003000, 1, b"synthetic", b"/synthetic", 100, 0, b""))
        for kind, path in (("zsh", zsh), ("nu", nu), ("nu-db", nu_db)):
            with self.subTest(format=kind):
                before = path.read_bytes()
                imported = self.history("import", kind, "--file", str(path))
                self.assertEqual(imported.returncode, 0, imported.stderr)
                self.assertNotIn(secret, imported.stdout + imported.stderr)
                self.assertEqual(path.read_bytes(), before)
                found = self.atuin_command("search", "--cmd-only", "--search-mode", "fulltext", f"imported-{kind}-token")
                self.assertEqual(found.returncode, 0, found.stderr)
                self.assertIn(f"imported-{kind}-token", found.stdout)
        self.assertIn("\necho multiline-token", self.atuin_command("search", "--cmd-only", "imported-nu-token").stdout)
        self.assertEqual(self.atuin_command("search", "--cmd-only", "excluded-").stdout, "")

    def test_first_and_joined_devices_exchange_encrypted_history_then_keep_working_offline(self):
        with AtuinSyncFixture() as server:
            self.env.update(ATUIN_SYNC_ADDRESS=server.address, ATUIN_AUTO_SYNC="false")
            config = self.home / ".config/atuin/config.toml"
            config.write_text(config.read_text().replace('sync_address = "https://api.atuin.sh"',
                                                        f'sync_address = "{server.address}"').replace("auto_sync = true", "auto_sync = false"))
            address = self.atuin_command("config", "get", "--resolved", "sync_address")
            self.assertEqual(address.returncode, 0, address.stderr)
            self.assertEqual(address.stdout.strip().rstrip("/"), server.address)
            password = "synthetic-password-only-for-loopback-test"
            output = self.setup_device("first-device", [
                ("username:", "synthetic-user"), ("email:", "synthetic@example.invalid"),
                ("password:", password),
            ])
            self.assertNotIn(password, output)
            state = self.history("status")
            self.assertEqual(state.returncode, 0, state.stderr)
            self.assertIn("activation configured", state.stdout)
            self.assertNotIn("pending activation", state.stdout)
            key = self.atuin_command("key", "--base64").stdout.strip()
            self.assertTrue(key)
            begun = self.atuin_command("history", "start", "--", "echo device-one-shared-token")
            self.assertEqual(begun.returncode, 0, begun.stderr)
            ended = self.atuin_command("history", "end", "--exit", "0", begun.stdout.strip())
            self.assertEqual(ended.returncode, 0, ended.stderr)
            synced = self.history("sync")
            self.assertEqual(synced.returncode, 0, synced.stderr)
            self.assertIn("Sync complete", synced.stdout)
            wire = str(server.records)
            self.assertNotIn("device-one-shared-token", wire)
            self.assertTrue(server.records)
            self.assertTrue(all(record["data"]["data"].startswith("v4.local.") for record in server.records.values()))
            original_home, original_env = self.home, self.env
            self.home = self.root / "joined-device"
            self.home.mkdir()
            self.env = {key: value.replace(str(original_home), str(self.home)) for key, value in original_env.items()}
            for name, binary in (("atuin", self.atuin), ("python", self.tool_home / ".pixi/envs/python/bin/python")):
                exposure = self.home / ".pixi/bin" / name
                exposure.parent.mkdir(parents=True, exist_ok=True)
                exposure.symlink_to(binary)
            deploy = subprocess.run(["bash", str(SOURCE / "bootstrap.sh"), "--home", str(self.home), "--apply-only"],
                                    env=dict(self.env, DOTFILES_CHEZMOI_BIN=self.chezmoi), cwd=SOURCE,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(deploy.returncode, 0, deploy.stderr)
            config = self.home / ".config/atuin/config.toml"
            config.write_text(config.read_text().replace('sync_address = "https://api.atuin.sh"',
                                                        f'sync_address = "{server.address}"').replace("auto_sync = true", "auto_sync = false"))
            address = self.atuin_command("config", "get", "--resolved", "sync_address")
            self.assertEqual(address.returncode, 0, address.stderr)
            self.assertEqual(address.stdout.strip().rstrip("/"), server.address)
            joined = self.setup_device("join", [("username:", "synthetic-user"), ("password:", password),
                                                 ("Please enter encryption key", key)])
            self.assertNotIn(password, joined)
            self.assertNotIn(key, joined)
            second_sync = self.history("sync")
            self.assertEqual(second_sync.returncode, 0, second_sync.stderr)
            self.assertIn("device-one-shared-token", self.atuin_command("search", "--cmd-only", "shared-token").stdout)
        # Stop the isolated service: search and new local recording still work.
        self.assertIn("device-one-shared-token", self.atuin_command("search", "--cmd-only", "shared-token").stdout)
        begun = self.atuin_command("history", "start", "--", "echo offline-shared-token")
        self.assertEqual(begun.returncode, 0, begun.stderr)
        ended = self.atuin_command("history", "end", "--exit", "0", begun.stdout.strip())
        self.assertEqual(ended.returncode, 0, ended.stderr)
        self.assertIn("offline-shared-token", self.atuin_command("search", "--cmd-only", "offline-shared-token").stdout)
        unavailable = self.history("sync")
        self.assertNotEqual(unavailable.returncode, 0)
        self.assertIn("activation configured", self.history("status").stdout)

    def test_device_setup_rejects_secret_arguments_without_echoing_them(self):
        secret = "synthetic-password-that-must-not-enter-output"
        rejected = self.history("join", "--password", secret)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn(secret, rejected.stdout + rejected.stderr)
        noninteractive = self.history("first-device")
        self.assertNotEqual(noninteractive.returncode, 0)
        self.assertIn("interactive terminal", noninteractive.stderr)

    def test_history_status_refuses_state_symlinks_before_writing_outside_the_device(self):
        outside = self.root / "other-device"
        outside.mkdir()
        sentinel = outside / "untouched"
        sentinel.write_text("other device state\n")
        data = self.home / ".local/share/atuin"
        data.parent.mkdir(parents=True, exist_ok=True)
        data.symlink_to(outside, target_is_directory=True)
        rejected = self.history("status")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("symlink", rejected.stderr)
        self.assertEqual(list(outside.iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main()
