# Preview, backup, and recovery

Use these procedures on new/test hosts managed by the public bootstrap.
The legacy T9K live home is outside this deployment boundary: never run
Chezmoi init/apply against it. Validate changes in a disposable home first.

## Preview

```bash
bash bootstrap.sh --profile linux-workstation --home /path/to/managed-home --plan
```

The plan lists selectors and actions without writing or downloading. For an
already initialized managed home, Chezmoi's `diff` previews its source-owned
file changes without applying them:

```bash
target_home=/path/to/managed-home
chezmoi --source "$PWD" --destination "$target_home" \
  --config "$target_home/.config/chezmoi/chezmoi.toml" diff
```

Diff output may contain credentials from device files. Keep it private. It
does not preview bootstrap's client-setting merges, fetched payload copies,
package installation, or account/system opt-ins. To inspect those config
results, copy the relevant existing configuration to a disposable home and run
`--apply-only` there, then compare it locally. The public bootstrap accepts
uncommitted source changes.

## Back up configuration

Before changing an existing managed home, record `git rev-parse HEAD` and
save its current configuration. On Unix, this example archives only existing
configuration paths, including device-local hooks, outside the target home:

```bash
umask 077
backup_dir=$(mktemp -d /tmp/dotfiles-backup.XXXXXX)
set --
for path in .env_core .profile .bash_profile .bashrc .zshenv .zshrc .gitconfig \
  .condarc .cargo/config.toml .config .claude/settings.json .claude/CLAUDE.md \
  .claude.json .codex/config.toml .codex/AGENTS.md .kimi-code/config.toml \
  .kimi-code/tui.toml .kimi-code/mcp.json .agents .minimax/AGENTS.md \
  .pi/agent/settings.json .pi/agent/models-store.json .pi/agent/AGENTS.md \
  .qoder/AGENTS.md; do
  if [ -e "$target_home/$path" ]; then set -- "$@" "$path"; fi
done
tar -czf "$backup_dir/config.tar.gz" -C "$target_home" "$@"
git rev-parse HEAD > "$backup_dir/source-commit"
```

The archive can contain tokens and private instructions; retain it in private
storage before temporary-directory cleanup. This is a configuration snapshot,
not a backup of history, datasets, sessions, or installed packages. On Windows,
use a private backup directory and copy the corresponding configuration paths,
plus `AppData/Roaming/nushell`, `uv`, and `pip`; include native discovery copies
when restoring. Protect the backup with the current user's filesystem ACLs.

## Restore or roll back

Stop affected shells/clients before restoring their files. Inspect the archive
contents with `tar -tzf`, then restore into the same designated managed home:

```bash
tar -xzf "$backup_dir/config.tar.gz" -C "$target_home"
```

Restoring a snapshot replaces archived files but does not delete files created
after the snapshot. Compare those separately before removing them. Keep the
backup until shell startup and client settings work again. Avoid applying the
new source again until its failure is fixed, because it will overwrite restored
managed configuration.

For a source rollback, create a detached checkout at the recorded good commit,
validate it in fresh simulated homes, and run its public bootstrap against the
designated managed home. Review the diff first. Do not reset the current worktree
or discard uncommitted changes. `--apply-only` restores configuration ownership;
it does not downgrade installed tools, remove deselected bundles, activate an
account, or reverse explicit system/login-shell changes. Use the documented
tool-update process for package downgrades. System Bash opt-ins retain their
separate `.dotfiles.bak` backup.
