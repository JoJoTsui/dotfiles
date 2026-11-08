"""WAL-index recovery preserves committed history and refuses unrelated errors."""
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('history_recovery', SOURCE / 'deployment/legacy/recover-history.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class HistoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='history-wal-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        original = self.root / 'original.db'
        connection = sqlite3.connect(original)
        connection.execute('pragma journal_mode=wal')
        connection.execute('pragma wal_autocheckpoint=0')
        connection.execute('create table history(id integer primary key, command text)')
        connection.executemany('insert into history(command) values(?)', [('synthetic one',), ('synthetic two',)])
        connection.commit()
        self.database = self.root / 'history.db'
        for suffix in ('', '-wal', '-shm'):
            shutil.copy2(Path(str(original) + suffix), Path(str(self.database) + suffix))
        connection.close()
        self.state = self.root / 'recovery'

    def test_protocol_recovery_keeps_wal_history_and_private_backup(self):
        inspect = recovery.inspect

        def stale_index_once(path):
            if path == self.database and not self.state.exists():
                raise sqlite3.OperationalError('locking protocol')
            return inspect(path)

        authentication = self.root / 'key'
        authentication.write_bytes(b'authentication fixture remains unchanged')
        before = authentication.stat()
        with mock.patch.object(recovery, 'inspect', stale_index_once):
            self.assertTrue(recovery.recover(self.database, self.state, repair=True))
        self.assertEqual(inspect(self.database)['history'], 2)
        journal = next(self.state.glob('wal-index.*/recovery.json'))
        saved = json.loads(journal.read_text())
        self.assertEqual(saved['expected_rows'], saved['verified_rows'])
        self.assertIn('history.db-wal', saved['original_sha256'])
        self.assertEqual(journal.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(authentication.read_bytes(), b'authentication fixture remains unchanged')
        self.assertEqual(authentication.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertFalse(recovery.recover(self.database, self.state, repair=True))

    def test_no_repair_without_explicit_authority(self):
        with mock.patch.object(recovery, 'inspect', side_effect=sqlite3.OperationalError('locking protocol')):
            with self.assertRaisesRegex(ValueError, 'authorized --repair'):
                recovery.recover(self.database, self.state)
        self.assertFalse(self.state.exists())

    def test_run_excludes_authentication_database(self):
        data = self.root / '.local/share/atuin'
        data.mkdir(parents=True)
        shutil.copy2(self.database, data / 'history.db')
        (data / 'meta.db').write_bytes(b'authentication fixture')
        with mock.patch.object(recovery, 'recover', return_value=False) as recover:
            self.assertEqual(recovery.run(self.root, self.root, repair=True), 0)
        recover.assert_called_once_with(
            data / 'history.db', self.root / '.local/state/dotfiles/history-recovery', repair=True)

    def test_busy_database_is_not_repaired(self):
        before = {p.name:p.read_bytes() for p in self.root.glob('history.db*')}
        with mock.patch.object(recovery, 'inspect', side_effect=sqlite3.OperationalError('database is locked')):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'database is locked'):
                recovery.recover(self.database, self.state, repair=True)
        self.assertFalse(self.state.exists())
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.glob('history.db*')})

    def test_sidecar_symlink_is_rejected_before_database_open(self):
        sidecar = Path(str(self.database) + '-shm')
        sidecar.unlink()
        sidecar.symlink_to(self.root / 'outside')
        with mock.patch.object(recovery, 'inspect') as inspect:
            with self.assertRaisesRegex(ValueError, 'regular files'):
                recovery.recover(self.database, self.state, repair=True)
            inspect.assert_not_called()
