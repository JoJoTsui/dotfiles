"""Recover restart-stale SQLite WAL indexes on the trusted legacy home."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

# Authentication (meta.db, key and session) stays outside this adapter.
DATABASES = ('history.db', 'records.db')


def inspect(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=0.2)) as connection:
        result = connection.execute('pragma quick_check').fetchone()[0]
        if result != 'ok':
            raise ValueError('history database integrity check failed')
        tables = connection.execute("select name from sqlite_master where type='table'").fetchall()
        return {name: connection.execute('select count(*) from "' + name.replace('"', '""') + '"').fetchone()[0]
                for (name,) in tables}


def recover(path, state, *, repair=False):
    for item in (path, path.with_name(path.name + '-wal'), path.with_name(path.name + '-shm')):
        if item.is_symlink():
            raise ValueError('history database resources must be regular files')
    try:
        inspect(path)
        return False
    except sqlite3.OperationalError as error:
        if str(error) != 'locking protocol':
            raise
    if not repair:
        raise ValueError('restart-stale history WAL index; run the authorized --repair preparation')
    sidecar = path.with_name(path.name + '-shm')
    if not sidecar.is_file():
        raise ValueError('locking protocol without a WAL index; automatic recovery withheld')
    state.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='wal-index.', dir=state))
    fingerprints = {}
    for item in (path, path.with_name(path.name + '-wal'), sidecar):
        if not item.exists():
            continue
        before = item.stat()
        saved = backup / item.name
        shutil.copy2(item, saved)
        saved.chmod(0o600)
        after = item.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('history changed during recovery backup; retry when idle')
        fingerprints[item.name] = hashlib.sha256(saved.read_bytes()).hexdigest()
    # Validate DB + WAL independently. The derived SHM index is deliberately
    # absent from this private copy; SQLite reconstructs it from the WAL.
    with tempfile.TemporaryDirectory(prefix='history-recovery-check-') as temporary:
        copied = Path(temporary) / path.name
        for suffix in ('', '-wal'):
            source = backup / (path.name + suffix)
            if source.exists():
                shutil.copy2(source, Path(str(copied) + suffix))
        expected = inspect(copied)
    journal = dict(database=str(path), original_sha256=fingerprints, expected_rows=expected,
                   operation='rebuild derived WAL shared-memory index; retain database, WAL and authentication')
    (backup / 'recovery.json').write_text(json.dumps(journal, indent=2) + '\n')
    os.replace(sidecar, backup / (sidecar.name + '.original'))
    actual = inspect(path)
    if any(actual.get(table, 0) < count for table, count in expected.items()):
        raise ValueError('history row completeness check failed; recovery backup retained')
    journal['verified_rows'] = actual
    (backup / 'recovery.json').write_text(json.dumps(journal, indent=2) + '\n')
    return True


def run(home, live, *, repair=False):
    data = (home / '.local/share/atuin').resolve()
    state = (home / '.local/state/dotfiles/history-recovery').resolve()
    if not data.is_relative_to(live) or not state.is_relative_to(live):
        raise ValueError('history paths escape the trusted live tree')
    repaired = 0
    for name in DATABASES:
        path = data / name
        if path.exists():
            if path.is_symlink():
                raise ValueError('history database must be a regular file')
            repaired += recover(path, state, repair=repair)
    return repaired


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--live-root', type=Path, required=True)
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    try:
        changed = run(args.home, args.live_root.resolve(), repair=args.repair)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f'legacy history: {error}\n')
    print(f'legacy history: ready; {changed} stale WAL indexes recovered')
