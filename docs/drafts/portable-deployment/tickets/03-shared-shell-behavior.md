# 03: Deliver shared Nushell-first shell behavior

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A user starts standalone Nushell, Zsh, or Bash and receives
the same intended environment values and managed commands. Interactive
launchers prefer Nushell, zoxide navigation works, and the logs command uses
Tailspin in each supported shell.

**Blocked by:** 02 — Install common tools through managed installers.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] One canonical shared-settings model renders POSIX and Nushell values; shell-specific initialization remains in each adapter.
- [ ] Standalone shells work without inherited legacy variables or managed-tool search paths, including Nushell's guarded environment bootstrap.
- [ ] Shared tool paths, editor, Python preference/mirrors, Rust mirrors, proxy settings/toggles, and role-specific values agree where applicable.
- [ ] Existing environment overrides survive, repeated initialization is idempotent, and legacy tool directories remain off executable search paths.
- [ ] Managed interactive launchers prefer Nushell; secondary shells, non-interactive scripts, agent subprocesses, and non-TTY sessions retain their intended shell behavior.
- [ ] Required Nushell startup resources are available or safely handled; fresh standalone startup does not require the current host's external tree.
- [ ] zoxide initializes in each available managed shell, and the logs command invokes the installed Tailspin with its pager.
- [ ] RTK is available to shell and agent subprocesses; every intended managed launcher has executable target permissions.
- [ ] Fresh-home subprocess checks exercise Nushell, Zsh, and Bash behavior, including non-interactive compatibility and environment parity, without changing the real host.
