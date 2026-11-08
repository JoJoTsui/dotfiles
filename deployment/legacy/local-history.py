"""Opt-in legacy Atuin storage: local SQLite, synchronous persistent snapshots.

Never open SQLite on the shared mount. Only immutable ZIP snapshots and the
original migration inputs live there. Keys/session files stay in place.
"""
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import zipfile

DATABASES = ('history.db', 'records.db', 'meta.db')


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path, data, mode=0o600):
    descriptor, temporary = tempfile.mkstemp(prefix='.history-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def inspect(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as connection:
        if connection.execute('pragma quick_check').fetchone()[0] != 'ok':
            raise ValueError('local history integrity check failed')
        # Authentication bytes are copied opaquely, never queried or reported.
        if path.name == 'meta.db':
            return {}
        tables = connection.execute("select name from sqlite_master where type='table'").fetchall()
        return {name: connection.execute('select count(*) from "' + name.replace('"', '""') + '"').fetchone()[0]
                for (name,) in tables}


class Store:
    def __init__(self, home, live, runtime, native):
        self.home, self.live = home.absolute(), live.resolve()
        self.runtime, self.native = runtime.absolute(), native.absolute()
        self.data = self.runtime / 'active'
        self.state = (home / '.local/state/dotfiles/history-local').resolve()
        self.original = (home / '.local/share/atuin').resolve()
        self.config = (home / '.config/atuin/config.toml').resolve()
        for path in (self.state, self.original, self.config):
            if not path.is_relative_to(self.live):
                raise ValueError('history paths escape the explicit legacy tree')
        if not (home / '.local/bin/atuin').resolve().is_relative_to(self.live):
            raise ValueError('Atuin launcher escapes the explicit legacy tree')
        if self.runtime.is_relative_to(self.live) or self.runtime.is_symlink():
            raise ValueError('active history must be on private notebook-local storage')
        # This adapter is Linux-only; do not silently place WAL on another
        # network filesystem supplied through --runtime.
        probe = self.runtime if self.runtime.exists() else self.runtime.parent
        kind = subprocess.check_output(['stat', '-f', '-c', '%T', str(probe)], text=True).strip()
        if kind not in ('overlayfs', 'tmpfs', 'ext2/ext3', 'ext4', 'xfs', 'btrfs'):
            raise ValueError('runtime filesystem is not a supported notebook-local filesystem')
        for path in (self.runtime, self.state):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
                raise ValueError('history runtime and snapshot directories must be private and owned by this user')
        if not self.native.is_file() or self.native == home / '.local/bin/atuin':
            raise ValueError('native Atuin must be a separate installed executable')
        for name in ('snapshot.0.zip', 'snapshot.1.zip', 'enabled.json'):
            if (self.state / name).is_symlink():
                raise ValueError('persistent history resources must be regular files')

    @property
    def archive(self):
        cache = self.runtime / 'snapshot.json'
        generation = json.loads(cache.read_text())['generation'] if cache.is_file() else 1
        return self.state / f'snapshot.{generation % 2}.zip'

    @contextmanager
    def lock(self):
        path = self.runtime / 'lock'
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def environment(self):
        settings = tomllib.loads(self.config.read_text())
        for key, value in (('db_path', settings.get('db_path')),
                           ('record_store_path', settings.get('record_store_path')),
                           ('meta.db_path', settings.get('meta', {}).get('db_path'))):
            if value:
                raise ValueError('explicit database path in Atuin config conflicts with local storage: ' + key)
        env = dict(os.environ, ATUIN_DATA_DIR=str(self.original), ATUIN_CONFIG_DIR=str(self.config.parent))
        env.update(ATUIN_DB_PATH=str(self.data / 'history.db'),
                   ATUIN_RECORD_STORE_PATH=str(self.data / 'records.db'),
                   ATUIN_META__DB_PATH=str(self.data / 'meta.db'))
        return env

    def snapshot(self):
        cache = self.runtime / 'snapshot.json'
        generation = (json.loads(cache.read_text())['generation'] if cache.is_file() else 0) + 1
        with tempfile.TemporaryDirectory(prefix='snapshot.', dir=self.runtime) as temporary:
            temporary = Path(temporary)
            manifest = {}
            for name in DATABASES:
                source, target = self.data / name, temporary / name
                if not source.exists():
                    continue
                if source.is_symlink():
                    raise ValueError('local history database must be a regular file')
                with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=2)) as incoming:
                    with closing(sqlite3.connect(target)) as outgoing:
                        incoming.backup(outgoing)
                        outgoing.execute('pragma journal_mode=delete')
                manifest[name] = dict(sha256=hashlib.sha256(target.read_bytes()).hexdigest(), rows=inspect(target))
            if not manifest:
                raise ValueError('refusing an empty history snapshot')
            target = temporary / 'snapshot.zip'
            with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('manifest.json', json.dumps(dict(schema=1, generation=generation, databases=manifest)))
                for name in manifest:
                    archive.write(temporary / name, name)
            # Fixed double-buffered slots avoid a Ceph directory fsync per
            # command (measured at 2-5 seconds). Never truncate the last committed
            # slot. A complete ZIP with hashes + an fsynced file is the commit;
            # restart chooses the newest complete generation, ignoring torn writes.
            slot = self.state / f'snapshot.{generation % 2}.zip'
            with slot.open('r+b') as stream, target.open('rb') as incoming:
                stream.truncate(0)
                shutil.copyfileobj(incoming, stream)
                stream.flush()
                os.fsync(stream.fileno())
            atomic_write(cache, json.dumps(dict(generation=generation)).encode())
            return manifest

    def unpack(self, temporary, archive_path=None):
        archive_path = archive_path or self.archive
        if not archive_path.is_file():
            raise ValueError('persistent history snapshot is missing; original databases retained')
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            names = manifest['databases']
            if manifest.get('schema') != 1 or not names or set(names) - set(DATABASES) or not isinstance(manifest.get('generation'), int):
                raise ValueError('invalid history snapshot manifest')
            for name, expected in names.items():
                payload = archive.read(name)
                if hashlib.sha256(payload).hexdigest() != expected['sha256']:
                    raise ValueError('history snapshot checksum mismatch')
                target = temporary / name
                target.write_bytes(payload)
                target.chmod(0o600)
                if inspect(target) != expected['rows']:
                    raise ValueError('history snapshot row completeness mismatch')
        return manifest['generation']

    def restore(self):
        valid = []
        for slot in range(2):
            archive = self.state / f'snapshot.{slot}.zip'
            if not archive.is_file() or not archive.stat().st_size:
                continue
            try:
                with tempfile.TemporaryDirectory(prefix='verify.', dir=self.runtime) as temporary:
                    generation = self.unpack(Path(temporary), archive)
                valid.append((generation, archive))
            except (ValueError, KeyError, zipfile.BadZipFile, sqlite3.Error):
                print('local history: incomplete snapshot slot ignored; retained generation will be verified', file=sys.stderr)
        if not valid:
            raise ValueError('no complete persistent history snapshot; original databases retained')
        generation, archive = max(valid)
        with tempfile.TemporaryDirectory(prefix='restore.', dir=self.runtime) as temporary:
            temporary = Path(temporary)
            self.unpack(temporary, archive)
            if self.data.exists():
                raise ValueError('unprepared local history exists; refusing to overwrite it')
            (temporary / 'ready').write_bytes(b'1\n')
            os.replace(temporary, self.data)
            atomic_write(self.runtime / 'snapshot.json', json.dumps(dict(generation=generation)).encode())

    def prepare(self):
        if self.data.is_symlink():
            raise ValueError('active history directory must be a regular directory')
        if not (self.data / 'ready').is_file():
            self.restore()
        for name in DATABASES:
            path = self.data / name
            if any((self.data / (name + suffix)).is_symlink() for suffix in ('', '-wal', '-shm')):
                raise ValueError('active database resources must be regular files')
            if path.exists():
                inspect(path)
        if not self.archive.is_file():
            raise ValueError('persistent history snapshot is missing')
        self.environment()

    def migrate(self, script):
        enabled = self.state / 'enabled.json'
        self.environment()
        wrapper = self.home / '.local/bin/atuin'
        command = ['python3', str(script.resolve()), '--home', str(self.home), '--live-root', str(self.live),
                   '--runtime', str(self.runtime), '--native', str(self.native), 'run', '--']
        launcher = ('#!/bin/sh\nexec ' + shlex.join(command) + ' "$@"\n').encode()
        if wrapper.is_symlink() or (wrapper.exists() and wrapper.read_bytes() != launcher):
            raise ValueError('existing local Atuin launcher; refusing to replace it')
        # New shell hooks now wait on our local lock while migration completes.
        # A failed migration leaves a fail-closed launcher and the originals.
        atomic_write(wrapper, launcher, 0o755)
        for slot in range(2):
            path = self.state / f'snapshot.{slot}.zip'
            if not path.exists():
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        sync_directory(self.state)
        if enabled.exists():
            self.prepare()
        elif self.data.exists():
            if not (self.data / 'ready').is_file():
                raise ValueError('existing unprepared runtime; original databases retained')
            self.snapshot()
        else:
            self.seed()
        marker = dict(schema=1, live_root=str(self.live), runtime=str(self.runtime), native=str(self.native))
        atomic_write(enabled, (json.dumps(marker, indent=2) + '\n').encode())

    def seed(self):
        with tempfile.TemporaryDirectory(prefix='migration.', dir=self.runtime) as temporary:
            temporary = Path(temporary)
            before = {}
            for name in DATABASES:
                for suffix in ('', '-wal', '-shm'):
                    source = self.original / (name + suffix)
                    if source.is_symlink():
                        raise ValueError('original database resources must be regular files')
                    if source.exists():
                        stat = source.stat()
                        before[source] = (stat.st_size, stat.st_mtime_ns)
                        # The SHM index is derived; SQLite recreates it locally.
                        if suffix != '-shm':
                            shutil.copy2(source, temporary / source.name)
            for source, expected in before.items():
                stat = source.stat()
                if (stat.st_size, stat.st_mtime_ns) != expected:
                    raise ValueError('original history changed during migration; retry when idle')
            found = [name for name in DATABASES if (temporary / name).exists()]
            if not found:
                raise ValueError('no original history database; refusing implicit initialization')
            active = temporary / 'active'
            active.mkdir(mode=0o700)
            for name in found:
                expected = inspect(temporary / name)
                # SQLite backup folds committed WAL frames into one clean file.
                with closing(sqlite3.connect((temporary / name).as_uri() + '?mode=ro', uri=True)) as source:
                    with closing(sqlite3.connect(active / name)) as target:
                        source.backup(target)
                (active / name).chmod(0o600)
                if inspect(active / name) != expected:
                    raise ValueError('migration row completeness mismatch; original data retained')
            (active / 'ready').write_bytes(b'1\n')
            os.replace(active, self.data)
            self.snapshot()

    def run(self, arguments):
        if os.environ.get('DOTFILES_ATUIN_ISOLATED') == '1':
            data = Path(os.environ.get('ATUIN_DATA_DIR', str(self.original))).resolve()
            if data == self.original or data == self.data:
                raise ValueError('isolated import must use a separate database')
            return subprocess.call([str(self.native), *arguments])
        with self.lock():
            if not (self.state / 'enabled.json').is_file():
                raise ValueError('local history migration has not completed')
            self.prepare()
        env = self.environment()
        # Static CLI helpers neither open the stores nor need a snapshot.
        static = arguments and arguments[0] in ('--version', '-V', '--help', '-h', 'init', 'uuid', 'config', 'completions', 'gen-completions')
        if static:
            return subprocess.call([str(self.native), *arguments], env=env)
        # Do not hold the snapshot lock across the picker: other panes must
        # continue recording while a human keeps a history UI open.
        interrupted = signal.signal(signal.SIGINT, lambda *_: None)
        try:
            start = arguments[:2] == ['history', 'start']
            if start:
                process = subprocess.run([str(self.native), *arguments], env=env, stdout=subprocess.PIPE)
                status = process.returncode
            else:
                status = subprocess.call([str(self.native), *arguments], env=env)
            with self.lock():
                self.snapshot()
            if start:
                sys.stdout.buffer.write(process.stdout)
                sys.stdout.buffer.flush()
        finally:
            signal.signal(signal.SIGINT, interrupted)
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--live-root', type=Path, required=True)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--native', type=Path)
    parser.add_argument('action', choices=('migrate', 'prepare', 'check', 'run'))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        marker = args.home / '.local/state/dotfiles/history-local/enabled.json'
        saved = json.loads(marker.read_text()) if marker.is_file() else {}
        if saved and saved.get('live_root') != str(args.live_root.resolve()):
            raise ValueError('history marker belongs to a different legacy tree')
        runtime = args.runtime or Path(saved.get('runtime', f'/tmp/dotfiles-atuin-{os.getuid()}'))
        native = args.native or Path(saved.get('native', str(args.home / '.pixi/bin/atuin')))
        store = Store(args.home, args.live_root, runtime, native)
        if args.action == 'run':
            arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
            return store.run(arguments)
        with store.lock():
            if args.action == 'migrate':
                store.migrate(Path(__file__))
            elif args.action == 'prepare':
                store.prepare()
            else:
                if not (store.data / 'ready').is_file() or not store.archive.is_file():
                    raise ValueError('local history is not prepared; run the link-home preparation')
                store.prepare()
            if args.action != 'migrate':
                with tempfile.TemporaryDirectory(prefix='check.', dir=store.runtime) as temporary:
                    store.unpack(Path(temporary))
        print('local history: ready; persistent snapshot available')
        return 0
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile, KeyError, subprocess.SubprocessError) as error:
        # Database/config values and native command arguments are private.
        print(f'local history: {type(error).__name__}; operation failed; data retained', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
