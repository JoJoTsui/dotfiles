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
terminal. Atuin 18.23's hosted service uses its browser account flow. On another
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

Atuin 18.23 layers some environment settings before its config file. A config
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

The transfer is deliberately tied to Atuin 18.23.0. It refuses other versions
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

## Validation boundary

[The Linux evidence](verification/shared-history.md) covers actual Nu/Bash/Zsh
recording, recognized-secret exclusion, all four import formats, hidden setup
input, two-device encrypted loopback sync, and operation after that endpoint
stops. Native macOS/WSL/Windows execution remains with their platform tickets.
The helper's Unix terminal masking is implemented; native Windows console
masking, native Nu import discovery and write isolation need ticket 11's
verified adapter. WSL uses the Unix boundary.

Primary references: [pinned account/sync guide](https://docs.atuin.sh/18.23/guide/sync/),
[pinned import implementation](https://github.com/atuinsh/atuin/blob/v18.23.0/crates/atuin/src/command/client/import.rs),
[pinned secret filtering](https://github.com/atuinsh/atuin/blob/v18.23.0/crates/atuin-client/src/history.rs).
