"""Notebook-local SQLite survives loss of the runtime through durable snapshots."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / 'deployment/legacy/local-history.py'
spec = importlib.util.spec_from_file_location('local_history', SCRIPT)
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


class LocalHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='local-history-test-',
                                                dir=os.environ.get('DOTFILES_TEST_PERSISTENT_ROOT'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home, self.live = (self.root / name for name in ('home', 'live'))
        runtime = tempfile.TemporaryDirectory(prefix='local-history-runtime-')
        self.addCleanup(runtime.cleanup)
        self.runtime = Path(runtime.name)
        self.home.mkdir()
        self.live.mkdir()
        for name in ('.config', '.local'):
            (self.live / name).mkdir()
            (self.home / name).symlink_to(self.live / name)
        (self.home / '.local/bin').mkdir()
        config = self.home / '.config/atuin'
        config.mkdir()
        (config / 'config.toml').write_text('auto_sync = false\nupdate_check = false\n')
        original = self.home / '.local/share/atuin'
        original.mkdir(parents=True)
        self.writers = []
        for name in storage.DATABASES:
            connection = sqlite3.connect(original / name)
            connection.execute('pragma journal_mode=wal')
            connection.execute('pragma wal_autocheckpoint=0')
            connection.execute('create table items(id integer primary key, value text)')
            connection.executemany('insert into items(value) values(?)', [('synthetic first',), ('synthetic second',)])
            connection.commit()
            self.writers.append(connection)
            self.addCleanup(connection.close)
        (original / 'key').write_bytes(b'opaque key fixture')
        self.original = original
        self.native = self.root / 'native-atuin'
        self.native.write_text('''#!/usr/bin/env python3
import os, sqlite3, sys
if sys.argv[1:] == ['--version']:
    print('atuin fixture')
else:
    with sqlite3.connect(os.environ['ATUIN_DB_PATH']) as connection:
        connection.execute('insert into items(value) values(?)', ('synthetic new',))
    print('native result')
''')
        self.native.chmod(0o755)
        self.store = storage.Store(self.home, self.live, self.runtime, self.native)
        self.env = dict(os.environ, HOME=str(self.home))

    def migrate(self):
        with self.store.lock():
            self.store.migrate(SCRIPT)

    def run_wrapper(self, *arguments):
        return subprocess.run([str(self.home / '.local/bin/atuin'), *arguments],
                              env=self.env, capture_output=True, text=True, timeout=15)

    def test_committed_wal_and_opaque_metadata_survive_runtime_loss(self):
        original_bytes = {p.name:p.read_bytes() for p in self.original.iterdir()}
        self.migrate()
        self.assertEqual(storage.inspect(self.store.data / 'history.db')['items'], 2)
        result = self.run_wrapper('write')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(storage.inspect(self.store.data / 'history.db')['items'], 3)
        shutil.rmtree(self.runtime)
        restarted = storage.Store(self.home, self.live, self.runtime, self.native)
        with restarted.lock():
            restarted.prepare()
        self.assertEqual(storage.inspect(restarted.data / 'history.db')['items'], 3)
        self.assertEqual(storage.inspect(restarted.data / 'records.db')['items'], 2)
        with sqlite3.connect(restarted.data / 'meta.db') as connection:
            self.assertEqual(connection.execute('select count(*) from items').fetchone()[0], 2)
        self.assertEqual(original_bytes, {p.name:p.read_bytes() for p in self.original.iterdir()})
        self.assertEqual(self.store.archive.stat().st_mode & 0o777, 0o600)
        with zipfile.ZipFile(self.store.archive) as archive:
            self.assertEqual(set(archive.namelist()), {'manifest.json', *storage.DATABASES})

    def test_repeated_migration_preserves_runtime_and_wrapper(self):
        self.migrate()
        self.assertEqual(self.run_wrapper('write').returncode, 0)
        self.migrate()
        self.assertEqual(storage.inspect(self.store.data / 'history.db')['items'], 3)

    def test_snapshot_failure_does_not_acknowledge_history_start(self):
        self.migrate()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(self.store, 'snapshot', side_effect=OSError):
            with self.assertRaises(OSError):
                self.store.run(['history', 'start', 'synthetic'])
        self.assertEqual(storage.inspect(self.store.data / 'history.db')['items'], 3)
        with zipfile.ZipFile(self.store.archive) as archive:
            saved = json.loads(archive.read('manifest.json'))
        self.assertEqual(saved['databases']['history.db']['rows']['items'], 2)

    def test_corrupt_snapshot_does_not_restore_empty_or_partial_data(self):
        self.migrate()
        self.store.archive.write_bytes(b'broken archive')
        shutil.rmtree(self.store.data)
        with self.assertRaisesRegex(ValueError, 'no complete persistent'):
            self.store.prepare()
        self.assertFalse(self.store.data.exists())

    def test_unprepared_runtime_is_never_overwritten(self):
        self.migrate()
        (self.store.data / 'ready').unlink()
        before = (self.store.data / 'history.db').read_bytes()
        with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
            self.store.prepare()
        self.assertEqual(before, (self.store.data / 'history.db').read_bytes())

    def test_interrupted_next_slot_keeps_last_acknowledged_snapshot(self):
        self.migrate()
        self.assertEqual(self.run_wrapper('write').returncode, 0)
        # Generation 2 is acknowledged in slot 0. Simulate a restart while
        # generation 3 is replacing the inactive slot 1.
        (self.store.state / 'snapshot.1.zip').write_bytes(b'interrupted write')
        shutil.rmtree(self.runtime)
        restarted = storage.Store(self.home, self.live, self.runtime, self.native)
        restarted.prepare()
        self.assertEqual(storage.inspect(restarted.data / 'history.db')['items'], 3)

    def test_conflicting_launcher_is_preserved(self):
        wrapper = self.home / '.local/bin/atuin'
        wrapper.write_text('personal launcher')
        with self.assertRaisesRegex(ValueError, 'refusing to replace'):
            self.migrate()
        self.assertEqual(wrapper.read_text(), 'personal launcher')

    def test_database_path_override_fails_closed(self):
        (self.home / '.config/atuin/config.toml').write_text('db_path = "/elsewhere/history.db"\n')
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            self.migrate()
        self.assertFalse(self.store.archive.exists())

    def test_shared_filesystem_is_rejected_for_active_database(self):
        with mock.patch.object(storage.subprocess, 'check_output', return_value='ceph\n'):
            with self.assertRaisesRegex(ValueError, 'notebook-local filesystem'):
                storage.Store(self.home, self.live, self.root / 'other-runtime', self.native)

    def test_runtime_symlink_is_rejected(self):
        other = self.root / 'other'
        other.mkdir()
        self.runtime.rmdir()
        self.runtime.symlink_to(other)
        self.addCleanup(self.runtime.unlink)
        with self.assertRaisesRegex(ValueError, 'private notebook-local'):
            storage.Store(self.home, self.live, self.runtime, self.native)

    def test_concurrent_panes_persist_every_completed_write(self):
        self.migrate()
        processes = [subprocess.Popen([str(self.home / '.local/bin/atuin'), 'write'],
                                     env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(4)]
        try:
            for process in processes:
                _, error = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, error)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
        shutil.rmtree(self.store.data)
        self.store.prepare()
        self.assertEqual(storage.inspect(self.store.data / 'history.db')['items'], 6)

    @unittest.skipUnless(os.environ.get('DOTFILES_TEST_TOOL_HOME'), 'requires installed Atuin')
    def test_real_atuin_repeated_writes_survive_notebook_runtime_loss(self):
        native = Path(os.environ['DOTFILES_TEST_TOOL_HOME']) / '.pixi/envs/atuin/bin/atuin'
        if not native.is_file():
            self.skipTest('installed native Atuin unavailable')
        self.native = native
        # The unit fixture's opaque bytes are deliberately not an Atuin key.
        # Let the native tool create its own key in this isolated test home.
        (self.original / 'key').unlink()
        self.store = storage.Store(self.home, self.live, self.runtime, native)
        self.migrate()
        for _ in range(40):
            result = self.run_wrapper('history', 'start', 'echo synthetic-persistence-regression')
            self.assertEqual(result.returncode, 0, result.stderr)
            identifier = result.stdout.strip()
            result = self.run_wrapper('history', 'end', '--exit', '0', identifier)
            self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(self.store.data / 'history.db') as connection:
            expected = connection.execute('select count(*) from history').fetchone()[0]
        self.assertEqual(expected, 40)
        shutil.rmtree(self.runtime)
        self.runtime.mkdir(mode=0o700)
        result = self.run_wrapper('--version')
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(self.store.data / 'history.db') as connection:
            restored = connection.execute('select count(*) from history').fetchone()[0]
        self.assertEqual(restored, expected)


if __name__ == '__main__':
    unittest.main()
