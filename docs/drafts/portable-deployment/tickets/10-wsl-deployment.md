# 10: Deliver WSL deployment and verify its Windows integration

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A WSL user gets the complete Nushell/Zsh/Bash common
environment for workstation or remote compute, with correctly selected Linux
architecture and WSL-specific behavior. Linux behavior and Windows integration
are verified as separate observable claims.

**Blocked by:** 06 — Configure CodeGraph access without automatic indexing;
07 — Enable shared shell history and deliberate device setup.

**Status:** Implemented; local rendering/planning checks passed, native WSL2 execution pending.

- [x] WSL detection distinguishes its environment from ordinary Linux, and explicit platform/role overrides still take precedence.
- [x] x86-64/ARM64 and both roles render correct home and tool paths without treating native Windows paths as Linux home defaults.
- [ ] The pinned common toolchain, all default Bun-managed agents, global instructions/skills, and CodeGraph integrations are usable through the WSL deployment entry point.
- [ ] Standalone Nushell, Zsh, and Bash share values, TUNA configuration, zoxide, Tailspin logs, and history integration without depending on an inherited legacy environment.
- [x] Ordinary setup remains user-scoped and does not change the Windows host's system or account configuration implicitly.
- [x] Local Linux execution and target-resolution checks are reported separately from actual WSL/Windows integration checks.
- [ ] An actual WSL environment verifies required Windows integration; unavailable runtime coverage remains explicitly pending rather than inferred from Linux fixtures.
- [ ] Reapplication preserves credentials, local history, and unrelated installations while device activation/import remain explicit.

Implementation: [WSL deployment and verification](../../../WSL_DEPLOYMENT.md),
`tests/test_wsl.py`, `tests/native/wsl.{ps1,py}`, and
`.github/workflows/native-wsl.yml`. The native gate checks both roles using an
unprivileged user, a checksum-pinned disposable WSL2 distro, Linux filesystem
source/home, actual Windows command/path interoperability, default tools and
clients, all three shells, history, and preserved local state. ARM64 is an
explicit opt-in self-hosted target. Unchecked native acceptance remains pending;
Linux rendering, borrowed-tool diagnostics and parser checks do not mark it passed.
