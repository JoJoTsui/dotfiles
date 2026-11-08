# Shared shell history

Ordinary bootstrap installs pinned Atuin, enables interactive Bash/Zsh hooks,
and prepares its validated Nushell vendor-autoload resource. Hosted encrypted
sync, recognized-secret filtering, global search and search across all shells
are explicit defaults. Every device first has local history; installing the
integration does not authenticate an account. `dotfiles-history status` reports
pending activation or configured authentication and the last recorded sync.
It checks local diagnostic state without contacting a sync server.

## Activate devices deliberately

On the first device, run `dotfiles-history first-device` from an interactive
terminal. Atuin's hosted service uses its browser account flow. On another
device, run `dotfiles-history join` using the same account and encryption key.
Retrieve the existing key with `atuin key` in a private terminal and keep a
private backup. Paste it at the hidden join prompt, never into a shell command
or password/key flag. The wrapper hides activation input, restores terminal
echo afterwards, and rejects extra arguments without repeating their values.

Run `dotfiles-history sync` to verify a sync. A failed connection returns a
failure while local history remains usable. Configured authentication is not a
claim that the latest commands have reached the server. Atuin's own automatic
sync runs with new commands after activation, on the configured interval.

The canonical shell roots are `ATUIN_CONFIG_DIR=$XDG_CONFIG_HOME/atuin` and
`ATUIN_DATA_DIR=$XDG_DATA_HOME/atuin`, with guarded device overrides. Atuin's key,
history/record databases, and `meta.db` authentication remain device state and
are excluded from the chezmoi payload and git. The pinned version stores auth
in `meta.db`; checking only a legacy `session` file would misreport activation.
Status uses Atuin's secret-safe offline doctor instead of exposing those tokens.

`sync.records = true` explicitly selects encrypted record sync. Existing-device
rehearsal verifies that setting and the account endpoint against device choices
before replacing the managed configuration.

Atuin layers some environment settings before its config file. A config
value such as `sync_address` or `auto_sync` therefore takes precedence over the
same environment variable. The local sync tests set and verify their temporary
config address before activation; a different endpoint must be selected in the
effective config too. Data-directory resolution has its own earlier override
pass. Consult the pinned [settings loader](https://github.com/atuinsh/atuin/blob/v18.23.0/crates/atuin-client/src/settings.rs)
when changing these boundaries.

## Import selected histories once

`dotfiles-history import` reports available default files and supported formats
without opening or importing them. Select each needed source independently:

```text
dotfiles-history import bash --file /path/to/bash-history
dotfiles-history import zsh --file /path/to/zsh-history
dotfiles-history import nu --file /path/to/history.txt
dotfiles-history import nu-db --file /path/to/history.sqlite3
```

On macOS, Nu discovery checks both the configured XDG location and
`~/Library/Application Support/nushell`. A format can use its default when
exactly one source exists. If both locations contain that format, select
`--file PATH`; the helper does not choose between them. An explicit file also
supports custom Nu history locations.

The explicit format selects Atuin's native importer; Nu SQLite uses
`nu-hist-db`. The pinned Nu importers ignore `HISTFILE`, so the helper snapshots
only the selected file into isolated native discovery paths. SQLite backup
includes committed WAL contents. Close the shell or flush its native history
first when migrating an active device. Use `--file` for a custom Zsh history
location such as `.zhistory`.

Atuin's pinned import command bypasses normal filters. This helper imports into
private, unauthenticated staging with sync disabled, runs Atuin's own secret,
history and directory filters, then transfers accepted entries only. Native
timestamps, session and exit metadata survive. Rejected commands never enter
the device's history database or encrypted record WAL. The original file stays
unchanged. Each format has a device-local completion marker; rerunning that
format leaves history unchanged. If local record initialization fails after
accepted entries transfer, the failure is visible and `dotfiles-history sync`
can finish Atuin's automatic store initialization without importing again.

The transfer reads the catalog-owned Atuin pin rendered into
`$XDG_CONFIG_HOME/dotfiles/profile.json` as `atuinVersion`. Migration requires
this deployed metadata and refuses other versions
and unequal native history schemas. This small SQLite transfer is needed to
retain metadata because the public command-text export cannot do so. An Atuin
update must rerun migration and encrypted sync tests before changing this pin.

## Native-shell limits

Atuin's built-in filter recognizes known credential patterns; it cannot detect
every possible secret. This filter controls Atuin recording and migration.
Bash, Zsh and Nushell can also retain their own native history, with their own
filter rules. Atuin does not retroactively sanitize those files, terminal
scrollback or application logs. A shell's native-history setting is not proof
that Atuin excluded a command, or the reverse.

Only shell command history is shared. Coding-agent conversations, sessions,
credentials and trust data are not imported. This deployment does not enable
agent history hooks or command-output capture.

## Legacy restart recovery

Atuin's SQLite WAL stores repeatedly failed on this notebook's Ceph mount:
even a fresh synthetic store failed during repeated command cycles. The
`locking protocol` / connection-pool timeout caused approximately three seconds
of delay **before** command output and prevented Up/Ctrl-R history search.
Rebuilding the shared-memory index gave temporary relief but did not fix it.
The older `recover-history.py` remains an explicit fallback for unmigrated
legacy homes; it is not the migrated host's storage strategy.

The authorized migration uses `deployment/legacy/local-history.py`:

```bash
python3 -B deployment/legacy/local-history.py \
  --home "$HOME" --live-root /t9k/mnt/joey/SHELL migrate
```

It installs a regular `~/.local/bin/atuin` launcher, ahead of Pixi on the managed
PATH. The native Pixi executable is retained. Active `history.db`, `records.db`,
and `meta.db` live in private `/tmp/dotfiles-atuin-<uid>/active` storage. Their
paths are passed through Atuin's supported environment settings. Explicit
database-path overrides in `config.toml` are rejected rather than silently
writing to Ceph. Encryption keys and non-SQLite identity/session files remain
at their original persistent paths; metadata is copied opaquely without
querying authentication values. Original databases and WALs remain unchanged
for rollback.

After each non-static Atuin invocation, the launcher uses SQLite's backup API
to create consistent local images, verifies integrity and per-table counts,
then writes and fsyncs the inactive one of two pre-created persistent files,
`snapshot.0.zip` and `snapshot.1.zip`, under
`~/.local/state/dotfiles/history-local/`. Each archive contains the complete
database set, a generation number, checksums and counts; `meta.db` values/counts
are not queried. The last committed slot remains intact during the next write.
Fixed slots avoid a per-command Ceph directory fsync, measured at 2–5 seconds.
The file entries are created and directory-flushed during migration. All snapshots are private and excluded
from source control. No live SQLite or WAL is opened on Ceph.

History-start identifiers are returned only after persistence succeeds. Other
panes can record while a picker is open; local SQLite handles concurrent
writes and a local lock serializes snapshot publication. A failed snapshot
returns a failure and retains the active data. An operation interrupted before
its snapshot finishes is not acknowledged as persisted; the last completed
snapshot survives even if the inactive slot contains an interrupted ZIP write.
Direct invocation of the native Pixi binary bypasses this
guarantee. Use `atuin` or `dotfiles-history`, not its package-internal path.
Existing Bash sessions with a cached native command need `hash -r`; a fresh SSH
session uses the launcher automatically.

After notebook-local storage disappears, the launcher and
`dotfiles-host-up up` restore and validate the snapshot before any database
operation or agent preparation. Restore stages the complete set and publishes
the active directory atomically. It chooses the newest fully verified slot and
warns about an incomplete slot. No valid snapshot, or conflicting unprepared
local data, fails closed; it never initializes empty history. Checksums detect
media corruption, but this restart guarantee is not a substitute for independent
backups against storage loss. The existing `.local` home link includes
both the launcher and persistent snapshots, so ordinary link-home restores
their reachability. No shutdown hook, background copy timer, or service is
required. `dotfiles-host-up status` validates local and snapshot health without
restoring missing local data.

For rollback, first preserve the newest snapshot and validate its contents on
local storage. The retained original database is a migration-time baseline,
not the current history. Do not remove the launcher and resume that old database
without reconciling newer history. Rollback is a separate explicit operation.

Verified on T9K Linux x86_64 with Atuin 18.24.5, an overlayfs runtime and Ceph
snapshots: 40 real start/end cycles followed by deletion of the synthetic runtime
restored all 40 rows. Separate tests cover concurrent panes, a torn inactive
snapshot, committed WAL migration and preservation of original resources.
A fresh Bash-login-to-Nu PTY verified Up/Ctrl-R and fzf; repeated live command
round trips measured 0.24–0.28 seconds including synchronous persistence.
The notebook itself was not restarted during verification.

## Validation boundary

[The Linux evidence](verification/shared-history.md) covers actual Nu/Bash/Zsh
recording, recognized-secret exclusion, all four import formats, hidden setup
input, two-device encrypted loopback sync, and operation after that endpoint
stops. Native macOS/WSL/Windows execution is recorded in their platform tickets,
which have now run. The helper's Unix terminal masking is implemented; native Windows console
masking, native Nu import discovery and write isolation need ticket 11's
verified adapter. WSL uses the Unix boundary.

Primary references: [pinned account/sync guide](https://docs.atuin.sh/18.23/guide/sync/),
[pinned import implementation](https://github.com/atuinsh/atuin/blob/v18.23.0/crates/atuin/src/command/client/import.rs),
[pinned secret filtering](https://github.com/atuinsh/atuin/blob/v18.23.0/crates/atuin-client/src/history.rs).

These release links record the initial integration sources. Compatibility of
the current catalog pin is established by the runtime migration and encrypted
sync checks; an existing device additionally needs the backed-up-store rehearsal
described in [macOS deployment](MACOS_DEPLOYMENT.md).
