# 10: Deliver WSL deployment and verify its Windows integration

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A WSL user gets the complete Nushell/Zsh/Bash common
environment for workstation or remote compute, with correctly selected Linux
architecture and WSL-specific behavior. Linux behavior and Windows integration
are verified as separate observable claims.

**Blocked by:** 06 — Configure CodeGraph access without automatic indexing;
07 — Enable shared shell history and deliberate device setup.

**Status:** Implemented; native WSL2 x86-64 execution passed in run
[38524061914](https://github.com/JoJoTsui/dotfiles/actions/runs/38524061914) at
commit `81857d6`, 2026-10-14. WSL2 ARM64 is not scheduled: no Windows ARM64 WSL2
runner exists, so it stays a rendering/resolution cell only.

- [x] WSL detection distinguishes its environment from ordinary Linux, and explicit platform/role overrides still take precedence.
- [x] x86-64/ARM64 and both roles render correct home and tool paths without treating native Windows paths as Linux home defaults.
- [x] The pinned common toolchain, all default Bun-managed agents, global instructions/skills, and CodeGraph integrations are usable through the WSL deployment entry point.
- [x] Standalone Nushell, Zsh, and Bash share values, TUNA configuration, zoxide, Tailspin logs, and history integration without depending on an inherited legacy environment.
- [x] Ordinary setup remains user-scoped and does not change the Windows host's system or account configuration implicitly.
- [x] Local Linux execution and target-resolution checks are reported separately from actual WSL/Windows integration checks.
- [ ] An actual WSL ARM64 environment verifies that architecture's Windows integration; no suitable runner is available, so the cell is explicitly unscheduled rather than inferred from the x86-64 run.
- [x] Reapplication preserves credentials, local history, and unrelated installations while device activation/import remain explicit.

Implementation: [WSL deployment and verification](../../../WSL_DEPLOYMENT.md),
`tests/test_wsl.py`, `tests/native/wsl.{ps1,py}`, and
`.github/workflows/native-wsl.yml`. The native gate checks both roles using an
unprivileged user, a checksum-pinned disposable WSL2 distro, Linux filesystem
source/home, actual Windows command/path interoperability, default tools and
clients, all three shells, history, and preserved local state. Linux rendering,
borrowed-tool diagnostics and parser checks do not mark native acceptance passed.

Post-dependency composition: 40 WSL-selected actual Linux shell/client/MCP/history
and isolated boundary cases passed, zero skips, 175.614s. The earlier required
deterministic gate remains recorded as 70 cases / 39 passed / 31 explicit skips.
Both WSL2 x86-64 native role cells then passed in workflow run 38524061914; the
two WSL2 ARM64 cells remain unscheduled because no Windows ARM64 WSL2 runner is
available, and an x86-64 result cannot stand in for them.

The native Nu launch now uses ordinary REPL startup (`-e`, then harmless print
and explicit exit). A two-role public `--probe-nu` regression reproduced the
old command-only startup failure and verifies shared env/config, prompt and
history resources without explicit config flags. The focused WSL/shell suite
passed 19 cases, zero skips, 78.101s on Linux; the probe reports native acceptance
as false and does not fill any native cell.
