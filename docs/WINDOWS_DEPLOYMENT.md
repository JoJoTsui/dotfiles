# Native Windows deployment

Run the user-scoped boundary from Windows PowerShell 5.1 or newer:

```powershell
./bootstrap.ps1 -Profile windows-workstation -Plan
./bootstrap.ps1 -Profile windows-remote-compute
./bootstrap.ps1 -TargetHome "$env:TEMP/dotfiles-device" -ApplyOnly
./bootstrap.ps1 -Agents codex,kimi-code
./bootstrap.ps1 -Agents none
./bootstrap.ps1 -Bundles desktop
```

The platform is native Windows; its host role defaults to workstation. Explicit
profile/component selections override environment selections and conflicts fail
before writing. Windows ARM, Unix-only bundles, relative homes, source-as-home,
and symlink/reparse write paths are rejected. Use `bootstrap.sh` inside WSL for
the complete Nushell/Bash/Zsh environment. Native Windows supplies Nushell and
PortableGit's Git Bash. Ordinary deployment changes neither system PATH, account
login shell, registry, Known Folder registration, nor driver/toolchain settings.

`TargetHome` designates HOME, USERPROFILE, APPDATA, LOCALAPPDATA, XDG roots,
Pixi/Bun/Cargo/Rustup caches and registries, Python configuration/cache roots,
Atuin state, and agent homes. Managed `dotfiles-shell.cmd` starts Nushell after
establishing those roots; `dotfiles-git-bash.cmd` opens the secondary shell.
Nushell and POSIX values come from the canonical shared settings. Git Bash PATH
entries use `cygpath -u`, while native tools receive Windows-absolute state
paths. Managed Git Bash is on PATH after Pixi; Pixi remains the exposed Git owner.
Kimi and Claude receive supported Git Bash environment overrides. Pi receives
a missing-default `shellPath`, preserving an explicit device choice.

Pixi owns the supported common environments, including RTK, uv, Nushell,
Tailspin, less, zoxide and Node. The exact upstream Windows exceptions are in
[windows-assets.json](../deployment/windows-assets.json): Pixi/Chezmoi bootstrap,
Bun baseline, Atuin, PortableGit, Helix with its runtime, jq and Rustup. Each
download is SHA-256 verified before extraction or execution. Rustup installs its
manager with no default compiler toolchain. Windows build SDKs and graphical
session prerequisites remain explicit, on-use dependencies.

All five agents and CodeGraph use the same manifests and frozen Bun locks as
Unix. Their projects live under `.bun/managed`; existing global Bun and Pixi
registries survive. Omitted agents remain installed. Native command launchers
use managed Node; CodeGraph MCP registrations spawn `node.exe` plus the pinned
`npm-shim.js` directly because a `.cmd` launcher is not universally executable
by a client's stdio subprocess implementation. Bootstrap creates no index.

The same raw payload catalog copies real skills/instructions without executing
their helpers. The same Chezmoi client-merge template stages all configs before
replacing any; device values and separate auth/trust/session files survive.
Native Nu and uv files deploy under `AppData/Roaming`; pip uses `pip/pip.ini`.
Only source-owned Nu settings are copied there: existing history, plugins and
unrelated files are preserved. Interactive `logs` uses Tailspin; zoxide uses the
explicit managed data directory. Native Nu startup artifacts also have a real
RoamingAppData discovery adapter.

Windows Known Folder APIs ignore changed HOME/USERPROFILE/APPDATA in several
Rust directory helpers. An isolated launch establishes absolute XDG roots
**before** Nu starts; setting them inside env.nu is too late for its pre-resolved
configuration/autoload paths. Applying to the ordinary native home also deploys
the normal RoamingAppData files, but this Linux environment cannot establish
unredirected native discovery. The native disposable-home tests retain the XDG
startup boundary and use no individual `--config` flags. They never scaffold
the CI user's actual Known Folder. Redirected enterprise profile policies need
separate native validation. [Pinned Nu resolver](https://github.com/nushell/nushell/blob/0.116.1/crates/nu-config/src/resolve.rs),
[native environment access](https://github.com/nushell/nushell/blob/0.116.1/crates/nu-config/src/env_access.rs).

`dotfiles-history.cmd` exposes status, explicit first-device/join setup, import,
and sync. New deployments report pending activation and retain offline history.
The Windows console adapter masks all attached-console activation input with
GetConsoleMode/SetConsoleMode and restores the original mode after the child
exits. Redirected/non-console input or output is rejected before starting auth.
Cancellation terminates and waits for the child before restoring input mode.
Hosted Hub authentication remains Atuin's browser flow; account credentials,
TOTP and the shared key remain outside git and command arguments.

Native Nu migration requires an explicit selected file:

```text
dotfiles-history import nu --file C:\selected\history.txt
dotfiles-history import nu-db --file C:\selected\history.sqlite3
```

The wrapper never invokes Atuin's Windows Nu Known Folder importers. Its
version/schema-guarded parser reads only the selected file or read-only SQLite
snapshot, stages unauthenticated rows, runs native secret pruning, transfers
accepted metadata, then builds the native encrypted record store. The explicit
`nu-file`/`nu-db-file` aliases expose this adapter on every platform for parity
checks. Pin 18.23 text behavior counts only LF-terminated lines, preserves CR,
skips invalid UTF-8 and expands literal `<\n>`. SQLite preserves lossy text,
exit/cwd, signed session hex, and the pin's **unscaled** duration_ms. Timestamps
that cannot fit the native integer history schema fall back to epoch. Import
markers are local and original files stay unchanged. File logging, including
the search/daemon/AI child overrides, is disabled to prevent native-home logs.
[Pinned native import mapping](https://github.com/atuinsh/atuin/blob/v18.23.0/crates/atuin-client/src/import/nu_histdb.rs).

Run `tests/native/windows.ps1` on Windows for the native acceptance gate. The
workflow uses windows-2025 for both roles with read-only permissions and pinned
Actions. It exercises actual installs/reapplication, stock PowerShell, managed
Nu/Git Bash paths, TUNA discovery, all five skill-discovery interfaces, native
MCP launches/connections, temporary CodeGraph indexing only, and real Windows
console/history/sync fixtures. Uploaded artifacts contain reports only.
Local verification and native pending cells are recorded in
[Windows evidence](verification/windows.md).
