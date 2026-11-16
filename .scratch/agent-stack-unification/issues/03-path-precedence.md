# 03: Per-platform PATH precedence

**What to build:** The shared path model becomes per-platform. On macOS the
managed launcher directory (`~/.local/bin`) precedes the Bun directory
(`$BUN_INSTALL/bin`), so a launcher for a Homebrew-adopted agent wins in an
interactive shell. Linux, WSL, and native Windows keep the current Bun-first
order. Both shell adapters render the same model, and the rendered files are the
evidence.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] Rendered `.env_core` and Nu environment place the managed launcher directory before the Bun directory on macOS.
- [ ] Rendered files on Linux, WSL, and native Windows keep the current order.
- [ ] A simulated macOS shell resolves an adopted agent to the Homebrew executable rather than the Bun copy.
- [ ] Tests render and assert the order for both adapters on both platform families.
- [ ] Existing shell-behaviour and zprofile tests pass unchanged.
