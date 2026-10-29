# Preserved optional inventory

`legacy-pixi-global.toml` retains the previous 106-environment inventory, with
Codex's former entry replaced by its migration note. Codex has one repo-owned
installation source, Bun. `legacy-bun-package.json` preserves the prior client
and Lark CLI inventory for its Bun migration. These files are historical input
to the selectable inventory work, not manifests applied over a device registry.

Common defaults are declared in `../common-tools.tsv`. All 77 remaining former
Pixi environments belong to opt-in bundles in `../bundle-tools.tsv`, with exact
pins, explicit exposed commands, channels, and row-level platform selectors.
The catalog columns are `bundle|environment|specifications|exposures|channels|platforms`.
Use `all` or comma-separated platform names in the final column; a tool may
have separate target variants under the same logical environment. Bio also adds a pinned curl environment
for `fetchChromSizes`. `../bundles.tsv` declares whole-bundle targets and host
prerequisites. A requested bundle includes its complete inventory; unsupported
requests fail before state creation rather than dropping unsupported members.

| Bundle | Contents | Declared targets |
| --- | --- | --- |
| `bio` | 14 former Bioconda tool environments, curl, and `fetchChromSizes` | Linux/WSL x86-64 and ARM64 |
| `gpu` | NVTOP | Linux/WSL x86-64 and ARM64 |
| `desktop` | Zed and Firefox | Linux/WSL x86-64, macOS Intel/Apple silicon, native Windows x86-64 |
| `developer-portable` | sd, just, hyperfine, lazygit, yq, and xh | Linux/WSL x86-64 and ARM64, macOS Intel/Apple silicon, native Windows x86-64 |
| `developer` | Remaining 54 developer environments, including fnm, Zellij, Herdr, ShellCheck, and shfmt | Linux/WSL x86-64 |

The Linux-specific developer inventory has a narrower target intersection.
Select `--bundles developer,developer-portable` for the former complete Linux
developer inventory, or `--bundles developer-portable` on another supported
platform. This split does not uninstall previously deployed tools. Both roles
have the same bundle selection rules. No
bundle is selected by default. Use `--bundles bio,gpu` or `DOTFILES_BUNDLES`;
explicit CLI selection overrides the environment, and `none` selects none.

Each tool retains an independent environment. This permits tgv's older HTSlib
constraint to coexist with samtools/HTSlib 1.24 and keeps KMC's Python constraint
independent of common Python. DuckDB's historical package provides its Python
API, exposed as `duckdb-python`; it does not promise a nonexistent DuckDB CLI.
The uutils library `libstdbuf.so` remains a package resource, not an exposed
executable. Managed Node replaces automatic fnm initialization.

Herdr/Zellij settings deploy only with `developer`; the bio helper deploys only
with `bio`. Linux/WSL desktop supplies Firefox's pinned GTK/X11/audio/D-Bus
libraries and a process-scoped runtime launcher; it does not depend on a system
package install or change library search paths in other processes. macOS and
Windows use their package's native payload without those Linux dependencies.
Source application creates a separate desired
`~/.config/dotfiles/pixi-bundles.toml`. The installer merges common and selected
bundle entries atomically into the device registry before one Pixi sync. It
verifies all selected command exposures. Deselection neither deletes registry
entries nor silently uninstalls tools or previously deployed optional settings.

GPU drivers/devices, a graphical session, cloud/service accounts, reference
data, and project-specific SDKs are host or setup-on-use prerequisites. Package
installation does not provision those facilities. The tested Linux bundle
resolution baseline is glibc 2.28; macOS desktop requires macOS 14.2 or newer.
Actual WSL, macOS, Windows, GUI, and GPU telemetry checks are separate from a
Linux solver or help/version diagnostic.

Preserve bootstrap-only ownership as well: gping 1.21.0's earlier Linux release
installation, Rust compiler/toolchain setup, Lark CLI, and Headroom's optional
local service. Rustup itself is now a pinned common manager installed without
a default toolchain; `cargo`/`rustc` use requires deliberate toolchain setup.
Headroom's MCP is disabled until its optional capability is configured. The
historical Gping upstream release and Lark CLI remain discoverable in the
legacy bootstrap/Bun inventory; they are setup-on-use capabilities rather than
implicit defaults. Lark account/app prerequisites and Headroom's local service
are not activated by a tool bundle. Neither a legacy version seed nor its
presence on the current device is new-target execution evidence.

Common deployment does not install these specialist tools or enable their
dependent configuration. Selecting fewer tools must preserve existing device
installations; changes to owned entries merge with the device's registry.

Validation and remaining runtime limits: [bundle evidence](../../docs/validation/bundles.md).
