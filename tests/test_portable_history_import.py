"""Explicit-file history migration observed through the public CLI and Atuin."""
import json
import os
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pins import common_pin

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
        self.profile = self.home / '.config/dotfiles/profile.json'
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text(json.dumps({'atuinVersion': common_pin('atuin')}))
        self.module = self.home / '.local/lib/dotfiles/history.py'
        self.module.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / 'dot_local/lib/dotfiles/history.py', self.module)
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
        if os.name == 'nt':
            shutil.copyfile(ATUIN, binary)
            binary.chmod(0o755)
        else:
            # Borrow the installed prefix so relative ELF/Mach-O libraries resolve.
            binary.symlink_to(Path(ATUIN).resolve())
        self.atuin = binary

    def history(self, *arguments):
        return subprocess.run([PYTHON, str(self.module), *arguments],
                              env=self.env, capture_output=True, text=True, timeout=60)

    def search(self, token):
        return subprocess.run([str(self.atuin), 'search', '--cmd-only', '--search-mode', 'fulltext', token],
                              env=self.env, capture_output=True, text=True, timeout=30)

    def test_import_reads_deployed_pin_and_checks_actual_version(self):
        selected = self.root / 'selected-history.txt'
        selected.write_text('echo deployed-pin-token\n')
        self.profile.write_text(json.dumps({'atuinVersion': '99.1.0'}))
        result = self.history('import', 'nu-file', '--file', str(selected))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('verified Atuin 99.1.0 pin', result.stderr)
        self.assertFalse((self.home / '.local/share/atuin/history.db').exists())
        self.assertFalse((self.home / '.local/share/atuin/dotfiles-imports/nu.json').exists())
        self.assertEqual(selected.read_text(), 'echo deployed-pin-token\n')
        self.profile.write_text(json.dumps({'atuinVersion': common_pin('atuin')}))
        result = self.history('import', 'nu-file', '--file', str(selected))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('deployed-pin-token', self.search('deployed-pin-token').stdout)

    def test_import_rejects_missing_or_malformed_deployed_pin(self):
        selected = self.root / 'selected-history.txt'
        selected.write_text('echo unverified-pin-token\n')
        for metadata in (None, 'not JSON', '[]', '{}', '{"atuinVersion": null}',
                         '{"atuinVersion": 18}', '{"atuinVersion": ""}',
                         '{"atuinVersion": "not a version"}'):
            with self.subTest(metadata=metadata):
                if metadata is None:
                    self.profile.unlink()
                else:
                    self.profile.write_text(metadata)
                result = self.history('import', 'nu-file', '--file', str(selected))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('deployed Atuin version', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertFalse((self.home / '.local/share/atuin/history.db').exists())
                self.assertFalse((self.home / '.local/share/atuin/dotfiles-imports/nu.json').exists())
                self.assertEqual(selected.read_text(), 'echo unverified-pin-token\n')

    def test_non_migration_commands_do_not_require_deployed_pin(self):
        self.profile.unlink()
        for arguments in (('check',), ('status',), ('import',)):
            with self.subTest(command=arguments):
                result = self.history(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / '.local/share/atuin/history.db').exists())

    def nu_source(self, directory, kind, token):
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / ('history.txt' if kind == 'nu' else 'history.sqlite3')
        if kind == 'nu':
            source.write_text(f'echo {token}\n')
        else:
            with closing(sqlite3.connect(source)) as connection:
                with connection:
                    connection.execute('CREATE TABLE history(id INTEGER, command_line BLOB, start_timestamp INTEGER, '
                                       'session_id INTEGER, hostname BLOB, cwd BLOB, duration_ms INTEGER, exit_status INTEGER, more_info BLOB)')
                    connection.execute('INSERT INTO history VALUES(1, ?, 1700000000123, 1, ?, ?, 42, 0, ?)',
                                       (f'echo {token}'.encode(), b'fixture-host', b'/fixture', b''))
        return source

    def assert_default_nu_imports(self, directory):
        for kind in ('nu', 'nu-db'):
            with self.subTest(format=kind):
                token = f'default-{kind}-token'
                source = self.nu_source(directory, kind, token)
                original = source.read_bytes()
                imported = self.history('import', kind)
                self.assertEqual(imported.returncode, 0, imported.stderr)
                self.assertIn(f'imported 1 filtered {kind} entries', imported.stdout)
                self.assertIn(token, self.search(token).stdout)
                self.assertEqual(source.read_bytes(), original)

    @unittest.skipUnless(sys.platform == 'darwin', 'native macOS history discovery')
    def test_macos_nu_defaults_import_the_only_native_history(self):
        self.assert_default_nu_imports(self.home / 'Library/Application Support/nushell')

    @unittest.skipUnless(os.name == 'posix', 'Windows Nu migration requires explicit --file')
    def test_nu_defaults_import_the_only_xdg_history(self):
        self.assert_default_nu_imports(self.home / '.config/nushell')

    @unittest.skipUnless(sys.platform == 'darwin', 'native macOS history discovery')
    def test_macos_explicit_nu_file_selects_one_of_two_default_histories(self):
        for kind in ('nu', 'nu-db'):
            with self.subTest(format=kind):
                selected = self.nu_source(self.home / 'Library/Application Support/nushell', kind, f'selected-{kind}-token')
                other = self.nu_source(self.home / '.config/nushell', kind, f'unselected-{kind}-token')
                originals = {path: path.read_bytes() for path in (selected, other)}
                ambiguous = self.history('import', kind)
                self.assertNotEqual(ambiguous.returncode, 0)
                self.assertIn('select --file PATH', ambiguous.stderr)
                imported = self.history('import', kind, '--file', str(selected))
                self.assertEqual(imported.returncode, 0, imported.stderr)
                self.assertIn(f'imported 1 filtered {kind} entries', imported.stdout)
                self.assertIn(f'echo selected-{kind}-token', self.search(f'selected-{kind}-token').stdout)
                self.assertEqual(self.search(f'unselected-{kind}-token').stdout, '')
                for path, original in originals.items():
                    self.assertEqual(path.read_bytes(), original)

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
        with closing(sqlite3.connect(selected)) as connection:
            with connection:
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
