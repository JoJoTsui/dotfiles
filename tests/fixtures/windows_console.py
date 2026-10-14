"""Actual Windows-console probes of public shell/history commands.

Run in a child created with CREATE_NEW_CONSOLE. Only synthetic loopback accounts
and selected temporary homes are used. Reports contain no console transcript,
password, key, commands containing test secrets, or history database.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from atuin_sync import AtuinSyncFixture


class Coord(ctypes.Structure):
    _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]


class Rect(ctypes.Structure):
    _fields_ = [('Left', ctypes.c_short), ('Top', ctypes.c_short), ('Right', ctypes.c_short), ('Bottom', ctypes.c_short)]


class BufferInfo(ctypes.Structure):
    _fields_ = [('size', Coord), ('cursor', Coord), ('attributes', wintypes.WORD), ('window', Rect), ('maximum', Coord)]


class Character(ctypes.Union):
    _fields_ = [('UnicodeChar', wintypes.WCHAR), ('AsciiChar', ctypes.c_char)]


class KeyEvent(ctypes.Structure):
    _fields_ = [('down', wintypes.BOOL), ('repeat', wintypes.WORD), ('key', wintypes.WORD),
                ('scan', wintypes.WORD), ('character', Character), ('control', wintypes.DWORD)]


class Event(ctypes.Union):
    _fields_ = [('key', KeyEvent), ('padding', ctypes.c_byte * 16)]


class InputRecord(ctypes.Structure):
    _fields_ = [('kind', wintypes.WORD), ('event', Event)]


class Console:
    def __init__(self):
        import msvcrt
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        # Python Popen may forward its parent's redirected standard handles
        # even with CREATE_NEW_CONSOLE. Open this owned console explicitly and
        # publish its handles before launching public wrappers/clients.
        self.streams = (open('CONIN$', 'r', encoding='utf-8'),
                        open('CONOUT$', 'w', encoding='utf-8', buffering=1),
                        open('CONOUT$', 'w', encoding='utf-8', buffering=1))
        self.kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
        self.kernel.SetStdHandle.restype = wintypes.BOOL
        handles = [wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno())) for stream in self.streams]
        for identifier, handle in zip((-10, -11, -12), handles):
            if not self.kernel.SetStdHandle(identifier & 0xFFFFFFFF, handle):
                raise RuntimeError('cannot attach the owned native console handles')
        sys.stdin, sys.stdout, sys.stderr = self.streams
        self.input, self.output = handles[:2]
        self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetConsoleMode.restype = wintypes.BOOL
        self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.SetConsoleMode.restype = wintypes.BOOL
        self.kernel.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(BufferInfo)]
        self.kernel.GetConsoleScreenBufferInfo.restype = wintypes.BOOL
        self.kernel.ReadConsoleOutputCharacterW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, Coord, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.ReadConsoleOutputCharacterW.restype = wintypes.BOOL
        self.kernel.WriteConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(InputRecord), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.WriteConsoleInputW.restype = wintypes.BOOL
        self.kernel.FillConsoleOutputCharacterW.argtypes = [wintypes.HANDLE, wintypes.WCHAR, wintypes.DWORD, Coord, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.FillConsoleOutputCharacterW.restype = wintypes.BOOL
        self.kernel.SetConsoleCursorPosition.argtypes = [wintypes.HANDLE, Coord]
        self.kernel.SetConsoleCursorPosition.restype = wintypes.BOOL
        self.original = self.mode()
        if not self.kernel.SetConsoleMode(self.input, self.original | 0x0004):
            raise RuntimeError('cannot establish the owned console fixture')
        self.original |= 0x0004

    def mode(self):
        mode = wintypes.DWORD()
        if not self.kernel.GetConsoleMode(self.input, ctypes.byref(mode)):
            raise RuntimeError('native console input is unavailable')
        return mode.value

    def text(self):
        info = BufferInfo()
        if not self.kernel.GetConsoleScreenBufferInfo(self.output, ctypes.byref(info)):
            raise RuntimeError('native console output is unavailable')
        count = min(info.size.X * info.size.Y, 120000)
        text = ctypes.create_unicode_buffer(count + 1)
        read = wintypes.DWORD()
        if not self.kernel.ReadConsoleOutputCharacterW(self.output, text, count, Coord(0, 0), ctypes.byref(read)):
            raise RuntimeError('cannot observe the owned native console')
        return text[:read.value]

    def clear(self):
        count = len(self.text())
        written = wintypes.DWORD()
        self.kernel.FillConsoleOutputCharacterW(self.output, ' ', count, Coord(0, 0), ctypes.byref(written))
        self.kernel.SetConsoleCursorPosition(self.output, Coord(0, 0))

    def type(self, value):
        characters = value + '\r'
        records = (InputRecord * (2 * len(characters)))()
        for index, character in enumerate(characters):
            for transition in (0, 1):
                record = records[2 * index + transition]
                record.kind = 1
                record.event.key.down = transition == 0
                record.event.key.repeat = 1
                record.event.key.key = 13 if character == '\r' else 0
                record.event.key.character.UnicodeChar = character
        written = wintypes.DWORD()
        if not self.kernel.WriteConsoleInputW(self.input, records, len(records), ctypes.byref(written)) or written.value != len(records):
            raise RuntimeError('cannot send synthetic native-console input')

    def wait(self, process, prompt, start=0):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            text = self.text()
            location = text.lower().find(prompt.lower(), start)
            if location >= 0:
                return location + len(prompt)
            if process.poll() is not None:
                raise RuntimeError(f'native client ended (exit {process.returncode}) before its expected console prompt {prompt!r}')
            time.sleep(0.05)
        raise RuntimeError('native console prompt timed out')


def stop_tree(process):
    if process.poll() is None:
        subprocess.run(['taskkill.exe', '/T', '/F', '/PID', str(process.pid)], capture_output=True, timeout=15)
        process.wait(timeout=10)


def environment(home, tool_home):
    env = {name: value for name, value in os.environ.items() if not name.startswith(('ATUIN_', 'XDG_', 'DOTFILES_'))}
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / 'AppData/Roaming'),
               LOCALAPPDATA=str(home / 'AppData/Local'), XDG_CONFIG_HOME=str(home / '.config'),
               XDG_DATA_HOME=str(home / '.local/share'), XDG_STATE_HOME=str(home / '.local/state'),
               XDG_CACHE_HOME=str(home / '.cache'), ATUIN_CONFIG_DIR=str(home / '.config/atuin'),
               ATUIN_DATA_DIR=str(home / '.local/share/atuin'), PIXI_HOME=str(home / '.pixi'),
               ATUIN_SESSION='0123456789abcdef0123456789abcdef')
    env['_ZO_DATA_DIR'] = str(home / '.local/share/zoxide')
    env['PATH'] = ';'.join(str(tool_home / item) for item in ('.bun/bin', '.local/bin', '.pixi/bin')) + ';' + env['PATH']
    return env


def shell_command(executable, rcfile):
    return ([str(executable), '--noprofile', '--rcfile', str(rcfile).replace('\\', '/'), '-i'])


def interactive_bash(executable, rcfile, token, navigation, log, workdir, env):
    """Drive the managed interactive Bash and capture its output.

    Upstream documents MSYS2's Windows-console interop as reliable only for
    plain character streams and "a lottery" for line editing, and the managed
    wrapper starts this shell with --login rather than as a raw console shell.
    A native piped probe therefore exercises the same interactive rcfile, the
    same managed binaries and the same shared history and navigation hooks,
    without depending on that console support. Only command output is captured.
    """
    commands = ('echo NATIVE_SHELL_READY\n'
                'echo ' + token + '\n'
                "cd '" + str(navigation).replace('\\', '/').replace("'", "'\\''") + "'\n"
                "logs --print '" + str(log).replace('\\', '/') + "'\n"
                'exit\n')
    return subprocess.run(shell_command(executable, rcfile), input=commands,
                          capture_output=True, text=True, timeout=120, cwd=workdir, env=env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    tool_home = Path(args.home)
    source = Path(args.source)
    report = Path(args.report)
    phases = []
    phase = 'console allocation'
    try:
        console = Console()
        with AtuinSyncFixture() as service:
            password = 'synthetic-native-password-\u96ea'
            username = 'synthetic-native-console'
            key = None
            for name, action, prompts in (
                ('first', 'first-device', [('username:', username), ('email:', 'synthetic@example.invalid'), ('password:', password)]),
                ('joined', 'join', None),
                ('failed', 'join', None),
            ):
                phase = name + ' console activation'
                home = report.parent / ('console-device-' + name)
                for relative in ('AppData/Roaming', 'AppData/Local'):
                    (home / relative).mkdir(parents=True, exist_ok=True)
                (home / '.config/atuin').mkdir(parents=True)
                (home / '.pixi/bin').mkdir(parents=True)
                config = (source / 'dot_config/atuin/config.toml').read_text()
                (home / '.config/atuin/config.toml').write_text(config.replace('https://api.atuin.sh', service.address).replace('auto_sync = true', 'auto_sync = false'))
                shutil.copyfile(tool_home / '.pixi/bin/atuin.exe', home / '.pixi/bin/atuin.exe')
                env = environment(home, tool_home)
                phase = name + ' sync endpoint verification'
                resolved = subprocess.run([str(home / '.pixi/bin/atuin.exe'), 'config', 'get', '--resolved', 'sync_address'],
                                          env=env, capture_output=True, text=True, timeout=15)
                actual_address = resolved.stdout.strip().strip('"').rstrip('/')
                if resolved.returncode:
                    raise RuntimeError(f'Atuin sync endpoint query failed (exit {resolved.returncode}): {resolved.stderr.strip()[:160]}')
                if actual_address != service.address:
                    raise RuntimeError(f'Atuin did not resolve the synthetic loopback endpoint: {actual_address[:160]!r}')
                console.clear()
                process = subprocess.Popen([sys.executable, str(source / 'dot_local/lib/dotfiles/history.py'), action], env=env)
                try:
                    if prompts is None:
                        # Atuin 18.23 uses its legacy flow for a custom sync_address (Hub needs
                        # api.atuin.sh/hub.atuin.sh), which asks for the username and password
                        # before the encryption key; the rejected-key retry prompt follows it.
                        prompts = [('username:', username if name == 'joined' else 'unknown-user'),
                                   ('password:', password if name == 'joined' else 'synthetic-wrong-password'),
                                   ('encryption key [blank', 'invalid-key'), ('please try again', None),
                                   ('encryption key [blank', key)]
                    cursor = 0
                    for prompt, value in prompts:
                        phase = f'{name} console activation ({prompt})'
                        cursor = console.wait(process, prompt, cursor)
                        if console.mode() & 0x0004:
                            raise RuntimeError('activation input echo remained enabled')
                        if value is not None:
                            console.type(value)
                    result = process.wait(timeout=45)
                    if (result == 0) != (name != 'failed'):
                        raise RuntimeError('native account fixture returned the wrong completion state')
                    text = console.text()
                    if password in text or (key and key in text):
                        raise RuntimeError('synthetic activation input was echoed')
                    if console.mode() != console.original:
                        raise RuntimeError('native input mode was not restored after child completion')
                    if name == 'first':
                        key_result = subprocess.run([str(home / '.pixi/bin/atuin.exe'), 'key', '--base64'], env=env,
                                                    capture_output=True, text=True, timeout=15)
                        if key_result.returncode:
                            raise RuntimeError('cannot retrieve the synthetic device key')
                        key = key_result.stdout.strip()
                        begun = subprocess.run([str(home / '.pixi/bin/atuin.exe'), 'history', 'start', '--', 'echo windows-device-one-shared-token'],
                                               env=env, capture_output=True, text=True, timeout=15)
                        if begun.returncode:
                            raise RuntimeError('native history recording failed')
                        ended = subprocess.run([str(home / '.pixi/bin/atuin.exe'), 'history', 'end', '--exit', '0', begun.stdout.strip()],
                                              env=env, capture_output=True, text=True, timeout=15)
                        synced = subprocess.run([sys.executable, str(source / 'dot_local/lib/dotfiles/history.py'), 'sync'],
                                               env=env, capture_output=True, text=True, timeout=30)
                        if ended.returncode or synced.returncode or not service.records:
                            raise RuntimeError('native encrypted sync failed')
                        if 'windows-device-one-shared-token' in str(service.records) or not all(
                                record['data']['data'].startswith('v4.local.') for record in service.records.values()):
                            raise RuntimeError('native sync did not use encrypted record envelopes')
                    elif name == 'joined':
                        synced = subprocess.run([sys.executable, str(source / 'dot_local/lib/dotfiles/history.py'), 'sync'],
                                               env=env, capture_output=True, text=True, timeout=30)
                        shared = subprocess.run([str(home / '.pixi/bin/atuin.exe'), 'search', '--cmd-only', 'windows-device-one-shared-token'],
                                               env=env, capture_output=True, text=True, timeout=15)
                        if synced.returncode or shared.returncode or 'windows-device-one-shared-token' not in shared.stdout:
                            raise RuntimeError('joined native device did not share the encrypted history')
                    phases.append(name)
                finally:
                    stop_tree(process)
        phase = 'native interactive shells'
        env = environment(tool_home, tool_home)
        env['DOTFILES_SECONDARY_SHELL'] = '1'
        navigation = tool_home / 'windows-navigation'
        navigation.mkdir()
        log = tool_home / 'native-console.log'
        log.write_text('2026-10-13 INFO native-tailspin-token\n')
        for shell in ('nu', 'bash'):
            phase = 'native interactive shells (' + shell + ')'
            executable = (tool_home / '.pixi/bin/nu.exe' if shell == 'nu' else
                          tool_home / '.local/share/dotfiles/git-bash/bin/bash.exe')
            token = 'native-console-' + shell + '-history-token'
            if shell == 'nu':
                console.clear()
                process = subprocess.Popen([str(executable), '--interactive'], cwd=tool_home, env=env)
                try:
                    time.sleep(1)
                    console.type("echo NATIVE_SHELL_READY")
                    console.wait(process, 'NATIVE_SHELL_READY')
                    console.type('echo ' + token)
                    console.wait(process, token)
                    console.type('cd ' + json.dumps(str(navigation)))
                    console.type('logs --print ' + json.dumps(str(log)))
                    console.wait(process, 'native-tailspin-token')
                    console.type('exit')
                    if process.wait(timeout=30):
                        raise RuntimeError('native interactive shell did not complete')
                finally:
                    stop_tree(process)
            else:
                interactive = interactive_bash(executable, tool_home / '.bashrc', token,
                                               navigation, log, tool_home, env)
                if interactive.returncode:
                    raise RuntimeError('interactive Bash did not complete (exit ' + str(interactive.returncode) + ')')
                for expected in ('NATIVE_SHELL_READY', token, 'native-tailspin-token'):
                    if expected not in interactive.stdout:
                        raise RuntimeError('interactive Bash did not produce ' + expected)
            search = subprocess.run([str(tool_home / '.pixi/bin/atuin.exe'), 'search', '--cmd-only', token],
                                     env=env, capture_output=True, text=True, timeout=15)
            if search.returncode or token not in search.stdout:
                raise RuntimeError('native interactive shell did not record in shared history')
            navigation_result = subprocess.run([str(tool_home / '.pixi/bin/zoxide.exe'), 'query', 'windows-navigation'],
                                               env=env, capture_output=True, text=True, timeout=15)
            if navigation_result.returncode or Path(navigation_result.stdout.strip()) != navigation:
                raise RuntimeError('native shell navigation did not reach managed zoxide')
            phases.append(shell + '-interactive-history-navigation-logs')
        report.write_text(json.dumps({'status': 'passed', 'native_console': True, 'checks': phases,
                                      'unicode_password': True, 'wrong_key_retry': True, 'mode_restored': True,
                                      'native_encrypted_two_device_sync': True}) + '\n')
        return 0
    except Exception as exc:
        detail = str(exc)
        for name in ('username', 'password', 'key'):
            secret = locals().get(name)
            if isinstance(secret, str) and secret:
                detail = detail.replace(secret, '<redacted>')
        report.write_text(json.dumps({'status': 'failed', 'native_console': True, 'phase': phase,
                                      'error': type(exc).__name__, 'detail': detail[:240]}) + '\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
