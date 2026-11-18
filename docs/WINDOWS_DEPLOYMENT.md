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

The eight Bun-managed agents and CodeGraph use the same manifests and frozen Bun
locks as Unix. Qoder uses its pinned native Windows release manifest with the
same SHA-256 verification. The verified executable is copied directly to
`.qoder/bin/qodercli/qodercli-<version>.exe`; both managed Qoder commands invoke
that pin. Existing vendor dispatchers, older versions and device state survive.
Cached binaries and downloaded payloads must report the exact pinned version;
an invalid cache is repaired only after the replacement passes verification.
Bun projects live under
`.bun/managed`; existing global Bun and Pixi registries survive. Omitted agents
remain installed. Native command launchers
bind JavaScript entries to the validated `DOTFILES_NODE_BIN` override when
supplied, or managed `.pixi/bin/node.exe` by default. Git Bash companions use
the same selected runtime. CodeGraph MCP registrations spawn `node.exe` plus the pinned
`npm-shim.js` directly because a `.cmd` launcher is not universally executable
by a client's stdio subprocess implementation. Bootstrap creates no index.

Git Bash receives bare POSIX companion launchers alongside native `.cmd`
launchers for the agents, CodeGraph and bunx. Each companion invokes the pinned
managed runtime; shell discovery is included in the native acceptance gate.

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
separate native validation. [Pinned Nu resolver](https://github.com/nushell/nushell/blob/0.117.0/crates/nu-config/src/resolve.rs),
[native environment access](https://github.com/nushell/nushell/blob/0.117.0/crates/nu-config/src/env_access.rs).

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

## The pinned Magpie CLI on native Windows

A full native Windows deployment installs the pinned Magpie CLI. The shared
release catalog `deployment/magpie/releases.tsv` owns the version every
target shares and the SHA-256 digest that verifies each asset; the Windows
adapter consumes its `windows-amd64` row and never resolves a release at run
time. The download must use HTTPS and the payload is verified against the
catalog digest before it is executed or placed. Windows ARM is outside the
supported architecture matrix, so the `windows-arm64` row is never consumed
here.

The binary lives at `~/.local/share/dotfiles/magpie/bin/magpie.exe`, beside
the POSIX companion that Git Bash runs. The native launcher
`~/.local/bin/magpie.cmd` starts the pinned binary; the bare POSIX launcher
in the same directory belongs to the source application and is never
rewritten. A binary found at the managed CLI path is hashed before it is
executed: only bytes matching the catalog digest are reused, and the
`--version` check runs only after that. A device binary whose digest differs
is preserved unchanged and fails with a diagnostic that says to move it
aside; it is neither executed nor overwritten. The `.cmd` launcher resolves
the binary relative to `%~dp0` instead of embedding the home path, so non-ASCII
names and literal percent characters do not become batch-file text. It disables
delayed expansion to preserve exclamation marks. These paths still need native
Windows verification.

Both managed launchers (`~/.local/bin/magpie.cmd` and the POSIX companion
beside the binary) are preflighted before the binary is downloaded or either
launcher is written. A byte-identical launcher left by an earlier run is
adopted without a rewrite, which keeps repeated runs idempotent. Any other
existing launcher — a device file, a directory, or a symlink — is preserved
and fails with an actionable diagnostic before the CLI or a launcher is
mutated. The normal symlink guards on all other managed paths still apply.
The deployment reads no credential, writes no provider key, and starts no
service.

This slice installs the CLI only. The model gateway, the provider catalogs,
the credential store, the client wiring, and the service lifecycle stay
outside the Windows boundary: the catalogs and the POSIX engine are kept out
of the Windows home, and the deployment does not wire Claude Code, Pi, or any
other client to a gateway. `-Plan` reports the two apart, so an installed CLI
is never read as a gateway-ready deployment:

```text
magpie.cli             the CLI this run installs
magpie.version         the pinned version from the shared catalog
magpie.target          windows-amd64
magpie.url             the pinned release URL
magpie.sha256          the pinned digest
magpie.path            .local/share/dotfiles/magpie/bin/magpie.exe
magpie.gateway         false on native Windows
magpie.gatewayReason   why the gateway wiring is not part of this run
magpie.reason          why the CLI was skipped, when it was
```

The CLI is installed by default in a full deployment. `-NoMagpie` turns the
step off for one run, `DOTFILES_MAGPIE=false` turns it off for the device,
and the restricted modes (`-ApplyOnly`, `-AgentsOnly`) never install it; each
skip prints its reason. Those runs read no Magpie release catalog, report no
pin in the plan, and do not reject symlinks at the Magpie-only CLI/launcher
paths they will not write; the plan still keeps the two slices apart.

These checks are source-reviewed and covered by the public fixture tests;
the Windows behavior tests run only where PowerShell is available. The
installed CLI did not wire a gateway or provide native acceptance evidence.

Run `tests/native/windows.ps1` on Windows for the native acceptance gate. The
workflow uses windows-2025 for both roles with read-only permissions and pinned
Actions. It exercises actual installs/reapplication, stock PowerShell, managed
Nu/Git Bash paths, TUNA discovery, all five skill-discovery interfaces, native
MCP launches/connections, temporary CodeGraph indexing only, and real Windows
console/history/sync fixtures. Uploaded artifacts contain reports only.
Both roles passed natively in run
[38524061998](https://github.com/JoJoTsui/dotfiles/actions/runs/38524061998),
before the Magpie CLI changes described above. Those changes still need a native
Windows gate; [Windows evidence](verification/windows.md) records the earlier
result and the two gates left deferred for an interactive Windows host.
