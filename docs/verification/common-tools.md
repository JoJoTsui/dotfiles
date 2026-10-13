# Common-tool verification

Verification snapshot: 2026-10-13, ticket 02. All writes and package caches used
disposable or retained directories under `/tmp`; the live host was not applied,
authenticated, imported, or indexed.

| Layer | Observed result |
| --- | --- |
| Deterministic boundary | 13 tests passed with real isolated chezmoi apply for both Linux roles; the opt-in install test is separately skipped in that run. |
| Required failures | Controlled Pixi sync exit 37 identifies its sync step; a corrupt archive fails SHA-256 verification before execution/apply and names its manager step. |
| Native Linux x86-64 | Real pinned downloads, Pixi sync, Rustup manager installation, and harmless CLI diagnostics passed in an isolated home. The check reruns bootstrap and verifies managed command locations and retained unrelated Pixi exposure. |
| TUNA discovery | Managed pip returns its configured TUNA index. Managed uv's settings display discovers the rendered TUNA index during an offline dry-run against a deliberately unavailable package. No Python package installation or mirror-network success is inferred from that diagnostic. |
| Foreign resolution | Pixi workspace lock resolution succeeded for all 29 per-tool environments on their declared targets: 139 environment/target solves across Linux x86-64/ARM64, macOS Intel/ARM64, and native Windows x86-64. Windows omits six Unix-only conda entries for its later explicit exceptions. |
| Native foreign/ARM execution | Pending. Resolution did not execute those binaries. Native platform adapters and their runners belong to later tickets. |
| Full bootstrap | Pending ticket 04. Its explicit agent-stage failure is expected at this midpoint and never produces the full completion message. |

The real-install test is `tests/test_common_install.py`, enabled with
`DOTFILES_TEST_INSTALL=1`. The retained validation home is
`/tmp/dotfiles-implementation/common-linux/home`; its `install-1.log` and
`install-2.log` capture actual installer results. Binaries under its
`.pixi/bin` (or direct `.pixi/envs/<name>/bin`) and `.cargo/bin/rustup` may be
used read-only by later diagnostics. Every later test supplies its own writable
HOME, XDG roots, Atuin/database, manager, and cache roots. Installed prefixes
must not be relocated or shared for concurrent mutation.

The foreign resolution workspace and generated lock are retained at
`/tmp/dotfiles-implementation/common-resolution/{pixi.toml,pixi.lock}`.
Each workspace feature reproduces one exact catalog environment, keeping
Python/pip together and separate tools independent. That workspace lock is
resolution evidence; Pixi global has no installation lockfile. Exact global
direct pins leave build/transitive drift, documented in the deployment boundary.

Chezmoi's default bootstrap is 2.73.0 with verified release digests; the separate
2.72.2 explicit test override only supplies the deterministic apply executable.
Pixi 0.81.0 and Rustup 1.29.1 downloads were checked against committed official
SHA-256 digests before execution. Rustup used `--default-toolchain none`;
no usable compiler toolchain is claimed by that manager check. Node 24.21.0
and Bun 1.3.11 executed successfully; the verified agent engine metadata is
compatible with Node 24 and their actual client execution follows in ticket 04.

Pinned upstream references: [Pixi 0.81.0 assets](https://github.com/prefix-dev/pixi/releases/expanded_assets/v0.81.0),
[Chezmoi 2.73.0 checksums](https://github.com/twpayne/chezmoi/releases/download/v2.73.0/chezmoi_2.73.0_checksums.txt),
and [Rustup 1.29.1 archives](https://static.rust-lang.org/rustup/archive/1.29.1/).
