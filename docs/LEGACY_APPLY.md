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
the Herdr config. The current legacy tree reports stale `nu-login`, stale Herdr
config, and a missing `dotfiles-host-up`; those are expected until an explicit
apply is approved.
