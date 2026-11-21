# Legacy apply

The public `bootstrap.sh` is not operable against the legacy T9K home. Its
state-root guard rejects the home's symlinked `.local`, `.config`, `.codex`,
`.cache`, and similar entries, and the agent-payload/client-settings validators
reject symlink ancestors. Running it anyway would write through the symlinks
into the live tree and could replace device-owned files.

`deployment/legacy/apply.sh` is the targeted alternative. It applies only the
files listed in `deployment/legacy/apply.tsv`:

- agent-stack executables: health, `codex-herdr`, the managed resume command the
  Herdr launcher reaches for, the hook installer, the host-up command,
  `nu-login`, the Herdr status helper, and the custom Codex resume hook;
- the shared history action helper, whose legacy opt-in routes through the
  local-storage launcher;
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

The global integration adapter records the observed Herdr integration state of
the kind it manages in `~/.local/state/dotfiles/herdr.tsv`, the same record
the public deployment writes, so the health check can report the live state on
a legacy host. The observation needs the status helper, so a host installs the
agent stack with this adapter before the integration adapter records the
state; without the helper the adapter names the gap and leaves the record
alone. A row of another owner stays untouched, and a replaced record reaches
the recovery journal.

`--groups agent` selects only the agent-stack files; `--groups config` selects
the Herdr config. `--groups all` (the default when the flag is absent) selects
every manifest group. `--targets` narrows either selection to comma-separated
target paths from the manifest; unknown targets fail before any writes. An
unknown group name also fails before any write, so a mistyped group is never a
silent no-op. The membership check reads only the manifest's file records: a
blank or comment line, such as the manifest's own header, names no group and
no target, so naming one fails like any other unknown selection. A name is
compared literally, so a spelling such as `\141gent` is unknown rather than a
decoded `agent`. An explicit `--groups` or `--targets` selection must carry
names: an empty selection or an empty comma-separated member is refused
instead of selecting everything, while the absent flag still selects
everything. For a focused restart repair on a legacy home, use:

```bash
bash deployment/legacy/apply.sh --check --targets .local/bin/dotfiles-agent-health,.local/bin/dotfiles-host-up,.config/herdr/config.toml
```

Use the same selection with `--dry-run` or an authorized `--apply`. Keep the
legacy `nu-login` until its shared environment is migrated: the managed wrapper
requires `_dotfiles_can_start_nu`, which older live `.env_core` files lack.

## Incremental deployment on the legacy T9K host

The legacy host is not a chezmoi home: its entries are symlinks into the live
tree, so the public bootstrap refuses it. The incremental deployment is the
set of explicit adapters, in this order:

```bash
# 1. The repo-owned agent stack, the history helper, and the Herdr config.
bash deployment/legacy/apply.sh --check
bash deployment/legacy/apply.sh --dry-run
bash deployment/legacy/apply.sh --apply

# 2. The approved global agent policy: instructions, skills, client settings.
bash deployment/legacy/agent-integrations.sh --check
bash deployment/legacy/agent-integrations.sh --apply

# 3. The T9K job automation.
bash deployment/legacy/agent-integrations.sh --t9k-jobs --check
bash deployment/legacy/agent-integrations.sh --t9k-jobs --dry-run
bash deployment/legacy/agent-integrations.sh --t9k-jobs --apply

# 4. The symlink topology of the home.
bash deployment/legacy/link-home.sh --check
bash deployment/legacy/link-home.sh --dry-run
bash deployment/legacy/link-home.sh --apply
```

The order matters in one place: the integration adapter records the observed
Herdr integration state, and the observation needs the status helper that the
first adapter installs. Every other adapter is independent, and each one is
safe to run again.

Two constraints belong to this host:

- The proxy launcher stays the live tree's own `with-proxy`. It does not know
  the `--if-available` option, so the Codex launcher asks the launcher before
  it uses the option and keeps the plain proxied route when it cannot answer.
  That launch depends on the proxy stack, so the narrow health check keeps
  the proxy readiness for such a launcher.
- The shell startup files are links into the live tree. The tree holds the
  managed bytes, so a link carries the current configuration, and the
  rehearsed shell migration replaces them with the rendered resources it
  prepares. Linking them is the last step, not a repair.

## Incremental T9K jobs

Use the explicit T9K job mode on the existing symlink-managed T9K host.
The default live root is the parent of this checkout. Use `--home` and
`--live-root` for a disposable rehearsal or a different legacy layout.

```bash
bash deployment/legacy/agent-integrations.sh --t9k-jobs --check
bash deployment/legacy/agent-integrations.sh --t9k-jobs --dry-run
bash deployment/legacy/agent-integrations.sh --t9k-jobs --apply
```

`--check` reports drift and exits nonzero if updates are needed. `--dry-run`
lists the files the adapter would write. Both leave the live tree untouched.
With owner authorization, `--apply` installs `~/.local/bin/t9k-run-job`, the
kubeconfig and runbook under `~/.local/share/dotfiles/t9k-automation`, and a
separate managed T9K block in the supported clients' instruction files.
Personal instructions and the global agent policy block stay intact.

The mode uses the checkout offline and needs no Chezmoi, skill cache, or
cluster access. It stages the plan before writing, confines destinations to
the legacy live tree, and publishes files by atomic rename. A changed apply
prints its private recovery journal under
`~/.local/state/dotfiles/t9k-automation/`. The journal records each replaced
file and its prior mode, or marks a newly installed file as `NEW`.

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
The shared managed-skill inventory is recoverable state too, so it is backed up
and journaled once before its first change in an apply, and an unchanged
inventory is left alone. `skills.*/restore.tsv` records original relative
discovery paths and the moved directories. For an explicitly authorized rollback, revert the source policy
first, then restore the recorded resources and modes. Review `NEW` paths before
removing them. Rerunning the current policy intentionally disables restored
resources again. Interrupted applications retain their backups and can be retried.

### Skill ownership in the legacy tree

The adapter copies a selected skill as a unit and follows the public copy-root
ownership policy, so a device entry never loses to the deployment:

- a symlink at the skill path is preserved and reported; the adapter never
  follows it and never writes through it
- a regular file at the skill path is preserved and reported
- a directory the managed-skill inventory does not record is adopted when it
  already holds the pinned bytes, without a rewrite, and preserved and
  reported when its bytes differ
- a directory the inventory records belongs to the deployment, so the pinned
  copy replaces it and the bytes it no longer carries are gone

The inventory is the same record the public deployment writes,
`~/.local/state/dotfiles/managed-skills.tsv`. The adapter adds its own rows and
keeps every row of another owner. An owned directory is replaced as a unit,
and the replaced bytes are copied into the recovery batch before the change, so
the rollback still restores it. The inventory path is confined to the live tree
and checked before that ownership is read, so an inventory that is a symlink
out of the live tree is refused instead of authorizing an overwrite; a leaf
alias inside the live tree keeps its canonical path. The candidate is staged
beside the canonical destination and published there, so a failed copy leaves
the active owned skill in place. The inventory itself is journaled in the
recovery batch, so a rollback that withdraws a new skill also withdraws the row
that recorded it and a later apply does not overwrite a new device directory.
A preserved entry is reported once per physical
path, because a shared alias names one entry. A preserved entry is not drift:
`--check` reports it and stays green, because the deployment has nothing to
change there.

A copy the tree carried before the inventory existed is reported rather than
replaced. When it already holds the pinned bytes it is adopted, so a later
apply owns it; when the pinned bytes moved on, remove that directory
deliberately to take the new bytes.

`dotfiles-host-up up` invokes the adapter after Mihomo and before agent daemons.
Thus `link-home` reasserts the policy before the laptop starts Herdr. Missing
cached source or a policy failure stops preparation. Running clients retain
their existing skill catalogs until they restart; this adapter never restarts them.

The same adapter enforces the source-owned Claude, Codex and Kimi updater
controls without applying provider defaults or replacing device authentication.

## Rehearsed shell migration

`deployment/legacy/migrate-shell.py` accepts a separately rendered and tested
home through `--rendered-home`, plus explicit `--home` and `--live-root` paths.
Its default validates the complete fixed destination set without applying it;
`--apply` requires the same prior owner authorization as other legacy adapters.
Use both simulated profiles and the native shell checks before applying.

It copies prepared Nu modules, generated resources, helpers and desired-state
metadata. The old POSIX environment remains opaque and gets an idempotent
rendered managed block; the old Nu environment becomes a private device hook,
with its missing JOEY/JSHELL bootstrap supplied first. Extra btm/curl completion
imports and existing device hooks survive. Existing Bash startup customization,
Git settings, account state, credentials, history and proxy service layout stay
device-owned. It never starts a shell, service or agent itself.

Destinations and recovery state must resolve inside the explicit live tree.
Each changed file receives an atomic replacement and a private recovery entry
under `.local/state/dotfiles/host-alignment/shell.*/restore.json`, recording its
old bytes and mode or `NEW`. Link the new Zsh/logout top-level files afterward
with `link-home.sh --groups config --links-only`. This leaves strict public
copy-mode guards intact; ordinary shell/history preparation commands still
reject symlink homes. Regenerate their resources in an isolated home and use
this explicit adapter for the legacy tree.
