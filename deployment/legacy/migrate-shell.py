"""Adopt rehearsed shell resources on the explicitly trusted legacy tree."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

FILES = (
    '.zprofile', '.zshenv', '.zshrc', '.bash_logout',
    '.config/nushell/config.nu', '.config/nushell/env.nu',
    '.config/nushell/direnv.nu', '.config/nushell/micromamba.nu',
    '.config/nushell/proxy.nu', '.config/nushell/zoxide.nu',
    '.config/dotfiles/profile.json', '.config/dotfiles/nu-completions.json',
    '.config/dotfiles/pixi-global.toml', '.config/dotfiles/pixi-bundles.toml',
    '.local/bin/bat-modules', '.local/bin/dotfiles-agents',
    '.local/bin/dotfiles-history', '.local/bin/dotfiles-history-prepare',
    '.local/bin/dotfiles-shell-prepare',
    '.local/lib/dotfiles/completions.py', '.local/lib/dotfiles/history.py',
)
START = b'\n# DOTFILES_LEGACY_ENV_START\n'
END = b'# DOTFILES_LEGACY_ENV_END\n'


def managed_block(original, start, end, content):
    if start not in original:
        return original + start + content + end
    prefix, _, remaining = original.partition(start)
    _, found, suffix = remaining.partition(end)
    if not found:
        raise ValueError('legacy managed block has no closing marker')
    return prefix + start + content + end + suffix


def plan(rendered, home, live):
    changes = {}

    def target(relative):
        path = home / relative
        if '/' not in relative and not path.is_symlink():
            path = live / relative
        path = path.resolve()
        if not path.is_relative_to(live):
            raise ValueError(f'destination escapes live tree: {relative}')
        if path.exists() and not path.is_file():
            raise ValueError(f'file conflict: {relative}')
        return path

    def add(relative, data, mode=0o644):
        changes[target(relative)] = (data, mode)

    def normalized(path):
        return path.read_bytes().replace(str(rendered).encode(), str(home).encode())

    for relative in FILES:
        source = rendered / relative
        if not source.is_file():
            raise ValueError(f'rehearsed resource is missing: {relative}')
        add(relative, normalized(source), source.stat().st_mode & 0o777)
    for tree in ('.local/share/nushell/vendor/autoload', '.local/share/nushell/completions/nu-scripts'):
        root = rendered / tree
        if not root.is_dir():
            raise ValueError(f'prepared resource tree is missing: {tree}')
        for source in root.rglob('*'):
            if source.is_symlink():
                raise ValueError('prepared resources must be regular files')
            if source.is_file():
                add(str(source.relative_to(rendered)), normalized(source), source.stat().st_mode & 0o777)

    # Preserve opaque device environment bytes; append only rendered public
    # defaults and helpers. Environment values never enter diagnostics or repo.
    target('.env_core')
    original = (home / '.env_core').read_bytes()
    bridge = (b'export DOTFILES_COMMON_BIN="$HOME/.pixi/bin"\n'
              b'export MAMBA_EXE="$DOTFILES_COMMON_BIN/micromamba"\n')
    add('.env_core', managed_block(original, START, END, bridge + normalized(rendered / '.env_core') + b'\n'),
        (home / '.env_core').stat().st_mode & 0o777)
    target('.bashrc')
    bashrc = home / '.bashrc'
    wt_hook = next(line for line in normalized(rendered / '.bashrc').splitlines()
                   if b'wt" config shell init bash' in line)
    add('.bashrc', managed_block(bashrc.read_bytes(), b'\n# DOTFILES_LEGACY_WT_START\n',
                                b'# DOTFILES_LEGACY_WT_END\n', wt_hook + b'\n'),
        bashrc.stat().st_mode & 0o777)

    legacy = home / '.config/dotfiles/legacy-env.nu'
    target('.config/dotfiles/legacy-env.nu')
    if not legacy.exists():
        add('.config/dotfiles/legacy-env.nu', (home / '.config/nushell/env.nu').read_bytes(), 0o600)
    local = home / '.config/dotfiles/env.local.nu'
    target('.config/dotfiles/env.local.nu')
    marker = b'# DOTFILES_LEGACY_NU_BRIDGE\n'
    if not local.exists() or marker not in local.read_bytes():
        previous = b''
        if local.exists():
            add('.config/dotfiles/env.previous.nu', local.read_bytes(), 0o600)
            previous = b'source env.previous.nu\n'
        add('.config/dotfiles/env.local.nu', marker +
            b'$env.JOEY = ($env.JOEY? | default ($nu.home-dir | path join "joey"))\n'
            b'$env.JSHELL = ($env.JSHELL? | default ($env.JOEY | path join "SHELL"))\n'
            b'source legacy-env.nu\n' + previous +
            b'$env.DOTFILES_COMMON_BIN = ($nu.home-dir | path join ".pixi" "bin")\n'
            b'$env.MAMBA_EXE = ($env.DOTFILES_COMMON_BIN | path join "micromamba")\n', 0o600)

    # These are the two extra imports in the audited legacy config; retain
    # them in the existing device hook instead of rebuilding resources at login.
    hook = home / '.config/dotfiles/nu.local.nu'
    target('.config/dotfiles/nu.local.nu')
    content = hook.read_bytes() if hook.exists() else b''
    for command in ('btm', 'curl'):
        extra = live / 'CLIs/nushell/nu_scripts/custom-completions' / command / f'{command}-completions.nu'
        if extra.is_file() and str(extra).encode() not in content:
            content += f'\nsource {json.dumps(str(extra))}\n'.encode()
    if content:
        add('.config/dotfiles/nu.local.nu', content, 0o600)
    return changes


def apply(changes, state):
    state.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='shell.', dir=state))
    journal = []
    for path, (data, mode) in changes.items():
        if path.is_file() and path.read_bytes() == data and path.stat().st_mode & 0o777 == mode:
            continue
        saved = backup / str(len(journal))
        if path.exists():
            shutil.copy2(path, saved)
            saved.chmod(0o600)
        journal.append(dict(path=str(path), backup=str(saved) if saved.exists() else 'NEW',
                            mode=path.stat().st_mode & 0o777 if path.exists() else None))
        (backup / 'restore.json').write_text(json.dumps(journal, indent=2) + '\n')
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='.shell-migration-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return len(journal), backup


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rendered-home', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--live-root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    changes = plan(args.rendered_home.resolve(), args.home, args.live_root.resolve())
    if args.apply:
        state = (args.live_root.resolve() / '.local/state/dotfiles/host-alignment').resolve()
        if not state.is_relative_to(args.live_root.resolve()):
            raise ValueError('recovery state escapes live tree')
        count, backup = apply(changes, state)
        print(f'legacy shell: {count} files changed; private recovery journal: {backup}')
    else:
        print(f'legacy shell: {len(changes)} destinations validated; no changes applied')
