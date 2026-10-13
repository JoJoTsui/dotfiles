"""Device history actions; only explicitly selected native histories are read.

Native adapters may invoke this file with the managed Python and the canonical
HOME/XDG/ATUIN roots. Atuin itself owns shell parsing, filtering and encryption.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid


class HistoryError(Exception):
    pass


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally repeats unknown values, including accidental
        # password/key flags. Keep invalid argv out of logs as well.
        raise HistoryError("invalid command or arguments; use --help. Credentials are accepted only at hidden terminal prompts")


def reject_symlinks(path):
    home = Path(os.environ["HOME"])
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise HistoryError(f"history state path is a symlink or junction: {component}")
        if component == home:
            break  # macOS /tmp and /var have ordinary system aliases.


def validate_roots():
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "ATUIN_CONFIG_DIR", "ATUIN_DATA_DIR"):
        path = Path(os.environ[name])
        if not path.is_absolute():
            raise HistoryError(f"{name} must be an absolute path")
        reject_symlinks(path)
    config = Path(os.environ["ATUIN_CONFIG_DIR"]) / "config.toml"
    reject_symlinks(config)
    for name in ("meta.db", "history.db", "records.db", "key", "session", "host_id"):
        reject_symlinks(Path(os.environ["ATUIN_DATA_DIR"]) / name)
    if config.is_file():
        settings = tomllib.loads(config.read_text())
        if os.name == "nt":
            logs = settings.get("logs", {})
            if logs.get("enabled", True) or any(logs.get(child, {}).get("enabled", False) for child in ("search", "daemon", "ai")):
                raise HistoryError("native history file logging must be disabled before running Atuin")
        for name in ("db_path", "record_store_path", "key_path", "meta.db_path"):
            environment_name = "ATUIN_META__DB_PATH" if name == "meta.db_path" else "ATUIN_" + name.upper()
            setting_value = settings.get("meta", {}).get("db_path") if name == "meta.db_path" else settings.get(name)
            value = os.environ.get(environment_name, setting_value)
            if value:
                candidate = Path(os.path.expandvars(os.path.expanduser(value)))
                reject_symlinks(candidate)
                if os.name == "nt" and Path(os.environ["HOME"]) not in candidate.parents:
                    raise HistoryError("native history write path is outside the designated home")


def run_atuin(atuin, arguments, *, env=None):
    result = subprocess.run([str(atuin), *arguments], env=env, capture_output=True,
                            text=True, check=False)
    if result.returncode:
        # Native parse errors can contain command text. Keep migration output
        # limited to the action and status; never echo rejected history.
        raise HistoryError(f"Atuin {arguments[0]} failed (exit {result.returncode})")
    return result.stdout


def configured_path(atuin, setting):
    value = run_atuin(atuin, ["config", "get", "--resolved", setting]).strip()
    path = Path(value)
    if not path.is_absolute():
        raise HistoryError(f"Atuin {setting} must resolve to an absolute path")
    reject_symlinks(path)
    return path


def default_sources():
    home = Path(os.environ["HOME"])
    config = Path(os.environ["XDG_CONFIG_HOME"])
    nu_config = Path(os.environ.get("APPDATA", str(config))) if os.name == "nt" else config
    return {"bash": home / ".bash_history", "zsh": home / ".zsh_history",
            "nu": nu_config / "nushell/history.txt", "nu-db": nu_config / "nushell/history.sqlite3"}


def status(atuin):
    # Atuin doctor also enumerates every process and mounted disk. Read only
    # the local activation metadata so status stays fast and works offline.
    meta_db = configured_path(atuin, "meta.db_path")
    for path in (meta_db, Path(str(meta_db) + "-wal"), Path(str(meta_db) + "-shm")):
        reject_symlinks(path)
    authenticated = False
    last_sync = "no last sync"
    if meta_db.is_file():
        try:
            with sqlite3.connect(meta_db.absolute().as_uri() + "?mode=ro", uri=True, timeout=1) as connection:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'")}
                if "meta" in tables:
                    authenticated = connection.execute(
                        "SELECT 1 FROM meta WHERE key IN ('session', 'hub_session') LIMIT 1").fetchone() is not None
                    if authenticated:
                        row = connection.execute(
                            "SELECT value FROM meta WHERE key = 'last_sync_time'").fetchone()
                        if row:
                            last_sync = row[0]
        except sqlite3.Error as error:
            raise HistoryError("Atuin activation metadata is unavailable") from error
    # Atuin 18.23 migrates this legacy file into meta.db when its own store is
    # first opened. Recognize it without opening the store or reading its token.
    if not authenticated and (Path(os.environ["ATUIN_DATA_DIR"]) / "session").is_file():
        authenticated = True
    if not authenticated:
        print("history: sync pending activation; local history works offline")
        print("use dotfiles-history first-device or dotfiles-history join")
    elif not configured_path(atuin, "key_path").is_file():
        print("history: activation incomplete; encryption key missing")
        print("join with the same account and key using dotfiles-history join")
    else:
        print("history: activation configured; local history is available offline")
        print(f"last recorded sync: {last_sync}; run dotfiles-history sync to verify current sync")


@contextmanager
def private_terminal():
    # Atuin hides passwords but its encryption-key prompt normally echoes.
    # Hide all activation input and restore the caller's terminal afterwards.
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetConsoleMode.restype = wintypes.BOOL
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetConsoleMode.restype = wintypes.BOOL
        try:
            descriptor = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdin.fileno()))
            output = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdout.fileno()))
        except (OSError, ValueError):
            raise HistoryError("device activation requires an interactive Windows console; credentials are never CLI arguments") from None
        original = wintypes.DWORD()
        output_mode = wintypes.DWORD()
        if not kernel.GetConsoleMode(descriptor, ctypes.byref(original)) or not kernel.GetConsoleMode(output, ctypes.byref(output_mode)):
            raise HistoryError("device activation requires an interactive Windows console; redirected input/output is rejected")
        if not kernel.SetConsoleMode(descriptor, original.value & ~0x0004):  # ENABLE_ECHO_INPUT
            raise HistoryError("cannot mask Windows console input; activation was not started")
        try:
            yield
        finally:
            if not kernel.SetConsoleMode(descriptor, original.value):
                raise HistoryError("cannot restore the original Windows console input mode")
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise HistoryError("device activation requires an interactive terminal; credentials are never CLI arguments")
    import termios
    descriptor = sys.stdin.fileno()
    original = termios.tcgetattr(descriptor)
    hidden = list(original)
    hidden[3] &= ~termios.ECHO
    termios.tcsetattr(descriptor, termios.TCSANOW, hidden)
    try:
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSANOW, original)


def activate_device(atuin, action):
    print("Use the same Atuin account on every device. Keep its encryption key in a private backup.", flush=True)
    if action == "join":
        print("Supply the existing device's key at the hidden prompt; never paste it into a shell command.", flush=True)
    with private_terminal():
        process = subprocess.Popen([str(atuin), "register" if action == "first-device" else "login"])
        try:
            result = process.wait()
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
    if result:
        raise HistoryError(f"{action} failed (exit {result}); local history remains available")
    status(atuin)
    print("History migration is optional. Run dotfiles-history import to choose each shell separately.")


def sync_history(atuin):
    result = subprocess.run([str(atuin), "sync"], check=False)
    if result.returncode:
        raise HistoryError(f"sync failed (exit {result.returncode}); local history remains available offline")


def import_nu_file(atuin, kind, source, database, environment):
    """Parse only the selected file; never call Windows Known Folder importers.

    Pin18.23 quirks are deliberate: LF-terminated text lines, literal CR bytes,
    lossy SQLite text, signed session hex, and unscaled duration_ms.
    The native CLI creates the schema/default origin in unauthenticated staging.
    """
    run_atuin(atuin, ["history", "start", "--", "dotfiles-import-schema-seed"], env=environment)
    with sqlite3.connect(database) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(history)")]
        expected = {"id", "timestamp", "duration", "exit", "command", "cwd", "session", "hostname",
                    "deleted_at", "author", "intent", "shell", "author_kind"}
        if set(columns) != expected:
            raise HistoryError("Atuin history schema differs from the verified Nu-file adapter")
        template = dict(zip(columns, connection.execute("SELECT * FROM history LIMIT 1").fetchone()))
        connection.execute("DELETE FROM history")
        entries = []
        if kind == "nu":
            lines = source.read_bytes().split(b"\n")[:-1]
            timestamp = time.time_ns() - min(max(len(lines) - 1, 0), 0xFFFFFFFF) * 1_000_000
            for line in lines:
                current = timestamp
                timestamp += 1_000_000
                try:
                    command = line.decode("utf-8").replace("<\\n>", "\n")
                except UnicodeDecodeError:
                    continue
                entries.append({"timestamp": current, "command": command, "cwd": "unknown", "exit": -1,
                                "duration": -1, "shell": "nu", "deleted_at": None, "intent": None, "author_kind": None})
        else:
            def text(value):
                return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
            with sqlite3.connect(source.absolute().as_uri() + "?mode=ro", uri=True) as original:
                with sqlite3.connect(":memory:") as snapshot:
                    original.backup(snapshot)
                    rows = snapshot.execute("SELECT command_line, start_timestamp, session_id, hostname, cwd, "
                                            "duration_ms, exit_status FROM history ORDER BY start_timestamp").fetchall()
            for command, milliseconds, session, hostname, cwd, duration, exit_status in rows:
                timestamp = milliseconds * 1_000_000
                if not -(1 << 63) <= timestamp < (1 << 63):
                    timestamp = 0
                entries.append({"timestamp": timestamp, "command": text(command), "cwd": text(cwd),
                                "exit": exit_status, "duration": duration, "session": format(session & ((1 << 64) - 1), "x"),
                                "hostname": text(hostname) + ":" + template["author"], "shell": "nu",
                                "deleted_at": None, "intent": None, "author_kind": None})
        placeholders = ",".join("?" for _ in columns)
        names = ",".join('"' + name + '"' for name in columns)
        for values in entries:
            # Fresh UUIDv7 IDs match the importer's identity policy; source Nu
            # row IDs are not Atuin history identities.
            random = uuid.uuid4().int
            identity = ((time.time_ns() // 1_000_000) << 80) | (7 << 76) | (((random >> 64) & 0xFFF) << 64)
            identity |= (2 << 62) | (random & ((1 << 62) - 1))
            entry = dict(template, **values, id=uuid.UUID(int=identity).hex)
            connection.execute(f"INSERT INTO history ({names}) VALUES ({placeholders})", [entry[name] for name in columns])


def import_history(atuin, kind, source):
    if kind is None:
        print("Choose an explicit one-time import: dotfiles-history import FORMAT [--file PATH]")
        for name, path in default_sources().items():
            print(f"{name}: {'available' if path.is_file() else 'not found'} ({path})")
        print("Nothing imported. Nu text and SQLite use different importers; select each needed format.")
        return
    portable_nu = kind in ("nu-file", "nu-db-file") or (os.name == "nt" and kind in ("nu", "nu-db"))
    kind = {"nu-file": "nu", "nu-db-file": "nu-db"}.get(kind, kind)
    if portable_nu and not source:
        raise HistoryError("portable Nu migration requires an explicit --file; native Known Folder import is never invoked")
    data = configured_path(atuin, "data_dir")
    imports = data / "dotfiles-imports"
    reject_symlinks(imports)
    imports.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = imports / f"{kind}.json"
    reject_symlinks(marker)
    if marker.exists():
        print(f"history: {kind} already imported; no changes")
        return
    source = Path(source) if source else default_sources()[kind]
    if not source.is_file():
        raise HistoryError(f"history file not found for {kind}; select --file PATH")
    lock = imports / f"{kind}.lock"
    reject_symlinks(lock)
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise HistoryError(f"another {kind} import is running; check {lock} before retrying") from None
    try:
        if marker.exists():
            print(f"history: {kind} already imported; no changes")
            return
        version = run_atuin(atuin, ["--version"]).strip()
        if version.split()[:2] != ["atuin", "18.23.0"]:
            raise HistoryError("migration requires the verified Atuin 18.23.0 pin")
        config_file = Path(os.environ["ATUIN_CONFIG_DIR"]) / "config.toml"
        settings = tomllib.loads(config_file.read_text())
        with tempfile.TemporaryDirectory(prefix=".import-", dir=data) as temporary:
            staging = Path(temporary)
            stage_config = staging / ".config"
            stage_atuin = stage_config / "atuin"
            stage_data = staging / "data"
            stage_atuin.mkdir(parents=True)
            stage_data.mkdir()
            # Only filters travel into staging, never auth, service headers,
            # device paths, daemon settings or credentials.
            filters = "".join(f"{key} = {json.dumps(settings[key], ensure_ascii=False)}\n"
                              for key in ("history_filter", "cwd_filter") if key in settings)
            (stage_atuin / "config.toml").write_text(
                'auto_sync = false\nupdate_check = false\nsecrets_filter = true\n'
                'sync_address = "http://127.0.0.1:1"\n' + filters +
                '[logs]\nenabled = false\n[logs.search]\nenabled = false\n'
                '[logs.daemon]\nenabled = false\n[logs.ai]\nenabled = false\n'
                '[daemon]\nenabled = false\nautostart = false\n')
            stage_env = {key: value for key, value in os.environ.items() if not key.startswith("ATUIN_")}
            stage_env.update(HOME=str(staging), XDG_CONFIG_HOME=str(stage_config),
                             XDG_DATA_HOME=str(staging / ".local/share"),
                             XDG_CACHE_HOME=str(staging / ".cache"),
                             ATUIN_CONFIG_DIR=str(stage_atuin), ATUIN_DATA_DIR=str(stage_data),
                             ATUIN_SESSION="0123456789abcdef0123456789abcdef")
            if os.name == "nt":
                stage_env.update(USERPROFILE=str(staging), APPDATA=str(staging / "AppData/Roaming"),
                                 LOCALAPPDATA=str(staging / "AppData/Local"))
            for key in ("ATUIN_HISTORY_FILTER", "ATUIN_CWD_FILTER"):
                if key in os.environ:
                    stage_env[key] = os.environ[key]
            stage_env["HISTFILE"] = str(source.absolute())
            importer = kind
            if portable_nu:
                import_nu_file(atuin, kind, source, stage_data / "history.db", stage_env)
            elif kind in ("nu", "nu-db"):
                # The pinned Nu importers ignore HISTFILE and use BaseDirs.
                # Relocate a selected snapshot into that isolated native path.
                nu_config = (staging / "Library/Application Support/nushell"
                             if sys.platform == "darwin" else stage_config / "nushell")
                nu_config.mkdir(parents=True)
                if kind == "nu":
                    shutil.copyfile(source, nu_config / "history.txt")
                else:
                    importer = "nu-hist-db"
                    uri = source.absolute().as_uri() + "?mode=ro"
                    with sqlite3.connect(uri, uri=True) as original:
                        with sqlite3.connect(nu_config / "history.sqlite3") as snapshot:
                            original.backup(snapshot)
            if not portable_nu:
                run_atuin(atuin, ["import", importer], env=stage_env)
            run_atuin(atuin, ["history", "prune"], env=stage_env)
            # The pinned importer bypasses should_save; pruning in unauthenticated
            # staging keeps rejected commands out of both device DB and record WAL.
            # Preserve native timestamps/session/exit metadata rather than record
            # old commands as if they had just run. Schema drift fails closed.
            run_atuin(atuin, ["history", "list", "--format", "{uuid}"])
            destination = configured_path(atuin, "db_path")
            with sqlite3.connect(destination) as connection:
                connection.execute("ATTACH DATABASE ? AS migration", (str(stage_data / "history.db"),))
                local_columns = [row[1] for row in connection.execute("PRAGMA main.table_info(history)")]
                imported_columns = [row[1] for row in connection.execute("PRAGMA migration.table_info(history)")]
                if local_columns != imported_columns or not {"id", "command", "timestamp", "deleted_at"}.issubset(local_columns):
                    raise HistoryError("Atuin history schema differs from the verified migration schema")
                columns = ", ".join('"' + name.replace('"', '""') + '"' for name in local_columns)
                before = connection.total_changes
                connection.execute(f"INSERT OR IGNORE INTO main.history ({columns}) "
                                   f"SELECT {columns} FROM migration.history WHERE deleted_at IS NULL")
                imported = connection.total_changes - before
            # Accepted entries are now local. Persist the one-time marker before
            # building records, so a record-store error cannot duplicate imports.
            marker.write_text(json.dumps({"format": kind, "accepted": imported}) + "\n")
        run_atuin(atuin, ["history", "init-store"], env=dict(os.environ, ATUIN_AUTO_SYNC="false"))
        print(f"history: imported {imported} filtered {kind} entries; original file unchanged")
    finally:
        lock.rmdir()


def main():
    os.umask(0o077)
    parser = PrivateArgumentParser(prog="dotfiles-history")
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser("import", help="explicit one-time native-shell history migration")
    migrate.add_argument("format", nargs="?", choices=("bash", "zsh", "nu", "nu-db", "nu-file", "nu-db-file"))
    migrate.add_argument("--file", help="explicit source file; default is the selected shell's native file")
    commands.add_parser("status", help="offline activation status; no credentials are displayed")
    commands.add_parser("first-device", help="explicit first-account registration with hidden terminal input")
    commands.add_parser("join", help="join the same account using its existing encryption key")
    commands.add_parser("sync", help="explicit encrypted sync; local history is kept on failure")
    commands.add_parser("check", help="check history write paths without touching history or credentials")
    arguments = parser.parse_args()
    validate_roots()
    os.environ.setdefault("ATUIN_SESSION", uuid.uuid4().hex)
    atuin = Path(os.environ["PIXI_HOME"]) / ("bin/atuin.exe" if os.name == "nt" else "bin/atuin")
    if not atuin.is_file():
        raise HistoryError("managed Atuin is not installed")
    if arguments.command == "import":
        import_history(atuin, arguments.format, arguments.file)
    elif arguments.command == "status":
        status(atuin)
    elif arguments.command in ("first-device", "join"):
        activate_device(atuin, arguments.command)
    elif arguments.command == "sync":
        sync_history(atuin)


if __name__ == "__main__":
    try:
        main()
    except (HistoryError, OSError, ValueError, sqlite3.Error) as error:
        print(f"dotfiles-history: {error}", file=sys.stderr)
        raise SystemExit(1)
