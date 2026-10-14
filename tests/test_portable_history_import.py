"""Explicit-file history migration observed through the public CLI and Atuin."""
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
ATUIN = os.environ.get('DOTFILES_TEST_ATUIN')
PYTHON = os.environ.get('DOTFILES_TEST_PYTHON')


@unittest.skipUnless(ATUIN and PYTHON, 'requires the actual pinned Atuin and managed Python')
class PortableHistoryImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dotfiles-history-file-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'device'
        self.config = self.home / '.config/atuin'
        self.config.mkdir(parents=True)
        shutil.copyfile(SOURCE / 'dot_config/atuin/config.toml', self.config / 'config.toml')
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(('ATUIN_', 'XDG_', 'DOTFILES_'))}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), APPDATA=str(self.home / 'AppData/Roaming'),
                        LOCALAPPDATA=str(self.home / 'AppData/Local'), XDG_CONFIG_HOME=str(self.home / '.config'),
                        XDG_DATA_HOME=str(self.home / '.local/share'), ATUIN_CONFIG_DIR=str(self.config),
                        ATUIN_DATA_DIR=str(self.home / '.local/share/atuin'), PIXI_HOME=str(self.home / '.pixi'),
                        ATUIN_SESSION='0123456789abcdef0123456789abcdef')
        if os.name == 'nt':
            # Native Atuin resolves its home through the Windows Known Folder for
            # the roaming profile, so the simulated home needs the standard AppData
            # directories just like the Windows console fixture creates them.
            for relative in ('AppData/Roaming', 'AppData/Local'):
                (self.home / relative).mkdir(parents=True, exist_ok=True)
        binary = self.home / ('.pixi/bin/atuin.exe' if os.name == 'nt' else '.pixi/bin/atuin')
        binary.parent.mkdir(parents=True)
        shutil.copyfile(ATUIN, binary)
        binary.chmod(0o755)
        self.atuin = binary

    def history(self, *arguments):
        return subprocess.run([PYTHON, str(SOURCE / 'dot_local/lib/dotfiles/history.py'), *arguments],
                              env=self.env, capture_output=True, text=True, timeout=60)

    def search(self, token):
        return subprocess.run([str(self.atuin), 'search', '--cmd-only', '--search-mode', 'fulltext', token],
                              env=self.env, capture_output=True, text=True, timeout=30)

    def test_explicit_nu_text_uses_only_selected_file_and_filters_before_activation(self):
        selected = self.root / 'selected-history.txt'
        secret = 'ghp_' + 'a' * 36
        original = (b'echo portable-lf<\\n>echo multiline\ninvalid-\xff\n' +
                    f'echo excluded-{secret}\n'.encode() + b'echo portable-cr\r\nunterminated-final')
        selected.write_bytes(original)
        imported = self.history('import', 'nu-file', '--file', str(selected))
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertNotIn(secret, imported.stdout + imported.stderr)
        found = self.search('portable-lf')
        self.assertEqual(found.returncode, 0, found.stderr)
        self.assertIn('echo portable-lf\necho multiline', found.stdout)
        self.assertEqual(self.search('invalid-').stdout, '')
        self.assertEqual(self.search('excluded-').stdout, '')
        self.assertEqual(self.search('unterminated-final').stdout, '')
        self.assertEqual(selected.read_bytes(), original)
        repeated = self.history('import', 'nu-file', '--file', str(selected))
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn('already imported', repeated.stdout)
        status = self.history('status')
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn('sync pending activation', status.stdout)

    def test_nu_sqlite_preserves_public_metadata_and_signed_session(self):
        selected = self.root / 'selected-history.sqlite3'
        secret = 'ghp_' + 'a' * 36
        with sqlite3.connect(selected) as connection:
            connection.execute('CREATE TABLE history(id INTEGER, command_line BLOB, start_timestamp INTEGER, '
                               'session_id INTEGER, hostname BLOB, cwd BLOB, duration_ms INTEGER, exit_status INTEGER, more_info BLOB)')
            connection.execute('INSERT INTO history VALUES(1, ?, 1700000000123, -1, ?, ?, 42, 7, ?)',
                               (b'echo portable-sqlite-\xff', b'fixture-host', b'/fixture/\xff', b'ignored'))
            connection.execute('INSERT INTO history VALUES(2, ?, 9223372036854775807, 2, ?, ?, 100, 0, ?)',
                               (b'echo corrupt-time-token', b'fixture-host', b'/fixture', b''))
            connection.execute('INSERT INTO history VALUES(3, ?, 1700000000124, 3, ?, ?, 100, 0, ?)',
                               (f'echo excluded-db-{secret}'.encode(), b'fixture-host', b'/fixture', b''))
        original = selected.read_bytes()
        imported = self.history('import', 'nu-db-file', '--file', str(selected))
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertEqual(selected.read_bytes(), original)
        self.assertNotIn(secret, imported.stdout + imported.stderr)
        environment = dict(self.env, ATUIN_SESSION='ffffffffffffffff')
        result = subprocess.run([str(self.atuin), 'search', '--filter-mode', 'session', '--shell', 'nu', '--timezone', '+0',
                                 '--format', '{time}|{directory}|{exit}|{duration}|{host}|{command}', 'portable-sqlite'],
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2023-11-14', result.stdout)
        self.assertIn('|/fixture/\ufffd|7|42ns|fixture-host|echo portable-sqlite-\ufffd', result.stdout)
        epoch = subprocess.run([str(self.atuin), 'search', '--timezone', '+0', '--format', '{time}', 'corrupt-time-token'],
                               env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(epoch.returncode, 0, epoch.stderr)
        self.assertIn('1970-01-01', epoch.stdout)
        self.assertEqual(self.search('excluded-db-').stdout, '')


if __name__ == '__main__':
    unittest.main()
