# Legacy apply

The public `bootstrap.sh` is not operable against the legacy T9K home. Its
state-root guard rejects the home's symlinked `.local`, `.config`, `.codex`,
`.cache`, and similar entries, and the agent-payload/client-settings validators
reject symlink ancestors. Running it anyway would write through the symlinks
into the live tree and could replace device-owned files.

`deployment/legacy/apply.sh` is the targeted alternative. It applies only the
files listed in `deployment/legacy/apply.tsv`:

- agent-stack executables: health, `codex-herdr`, the hook installer, the
  host-up command, `nu-login`, and the custom Codex resume hook;
- the Herdr config.

It deliberately excludes client settings, agent instruction blocks, shell rc,
authentication, `.caveman` runtime state, worktrees, and packages. Use
`link-home.sh` for the symlink topology and this adapter for the listed files.

```bash
bash deployment/legacy/apply.sh --check
bash deployment/legacy/apply.sh --dry-run
bash deployment/legacy/apply.sh --apply          # only with owner permission
```

`--check` reports `OK`, `DRIFT`, `MISSING`, `FOREIGN`, or `CONFLICT` and exits
nonzero on drift. `--dry-run` prints the planned writes and unified diffs.
`--apply` backs up an existing target as `<target>.bak.YYYYmmdd-HHMMSS`, writes a
temporary file in the resolved target directory, sets the manifest mode, and
renames atomically. It refuses symlink targets and any target that resolves
outside the live tree. It never creates missing parent directories.

`--groups agent` selects only the agent-stack files; `--groups config` selects
the Herdr config. `--targets` narrows either selection to comma-separated target
paths from the manifest; unknown targets fail before any writes. For a focused
restart repair on a legacy home, use:

```bash
bash deployment/legacy/apply.sh --check --targets .local/bin/dotfiles-agent-health,.local/bin/dotfiles-host-up,.config/herdr/config.toml
```

Use the same selection with `--dry-run` or an authorized `--apply`. Keep the
legacy `nu-login` until its shared environment is migrated: the managed wrapper
requires `_dotfiles_can_start_nu`, which older live `.env_core` files lack.

## Global agent integrations

`deployment/legacy/agent-integrations.sh` is a separate, explicit adapter for
the approved global integration policy. It does not run the public bootstrap.

```bash
# Once, before reboot: prepare reviewed source and the existing settings codec.
with-proxy bash deployment/legacy/agent-integrations.sh --fetch
bash deployment/legacy/agent-integrations.sh --check
# Apply only with owner authorization.
bash deployment/legacy/agent-integrations.sh --apply
```

`--apply` is offline. It stages all files before writing, reuses the public
instruction copier and settings codec, and confines canonical destinations to
the designated persistent live tree. It deploys the pinned official Graphify
skill/references and current managed instruction blocks. Personal text outside
owned blocks survives; the old standalone owned CodeGraph block is retired when
adopting the managed block. No upstream installer, project initialization, MCP
registration, or search-interception hook runs.

Serena MCP registrations are removed. Explicit Claude plugin-disable flags stay
false, since deleting them could enable an installed plugin. Other MCP servers,
providers, credentials, trust, and sessions are preserved. The 37 disabled
DeepMind skill directories move outside discovery; shared aliases are handled
once per physical entry. Packages and unrelated skills remain installed.

Recovery batches are private under
`~/.local/state/dotfiles/disabled-integrations/`. `files.*/restore.tsv` records
original paths, backups, and original modes; `NEW` marks a newly created file.
`skills.*/restore.tsv` records original relative discovery paths and the moved
directories. For an explicitly authorized rollback, revert the source policy
first, then restore the recorded resources and modes. Review `NEW` paths before
removing them. Rerunning the current policy intentionally disables restored
resources again. Interrupted applications retain their backups and can be retried.

`dotfiles-host-up up` invokes the adapter after Mihomo and before agent daemons.
Thus `link-home` reasserts the policy before the laptop starts Herdr. Missing
cached source or a policy failure stops preparation. Running clients retain
their existing skill catalogs until they restart; this adapter never restarts them.
