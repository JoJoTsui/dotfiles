# 03: Deliver shared Nushell-first shell behavior

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A user starts standalone Nushell, Zsh, or Bash and receives
the same intended environment values and managed commands. Interactive
launchers prefer Nushell, zoxide navigation works, and the logs command uses
Tailspin in each supported shell.

**Blocked by:** 02 — Install common tools through managed installers.

**Status:** Implemented; Linux execution verified. Native platform execution is
tracked by tickets 09–11 and the final matrix, not claimed by Linux rendering.

- [x] One canonical shared-settings model renders POSIX and Nushell values; shell-specific initialization remains in each adapter.
- [x] Standalone shells work without inherited legacy variables or managed-tool search paths, including Nushell's guarded environment bootstrap.
- [x] Shared tool paths, editor, Python preference/mirrors, Rust mirrors, proxy settings/toggles, and role-specific values agree where applicable.
- [x] Existing environment overrides survive, repeated initialization is idempotent, and legacy tool directories remain off executable search paths.
- [x] Managed interactive launchers prefer Nushell; secondary shells, non-interactive scripts, agent subprocesses, and non-TTY sessions retain their intended shell behavior.
- [x] Required Nushell startup resources are available or safely handled; fresh standalone startup does not require the current host's external tree.
- [x] zoxide initializes in each available managed shell, and the logs command invokes the installed Tailspin with its pager.
- [x] RTK is available to shell and agent subprocesses; every intended managed launcher has executable target permissions.
- [x] Fresh-home subprocess checks exercise Nushell, Zsh, and Bash behavior, including non-interactive compatibility and environment parity, without changing the real host.

## Acceptance evidence

`tests/test_shell_behavior.py` has ten observable Linux checks, using pinned
real common executables read-only and separately writable disposable homes.
The public bootstrap/rendered-file/shell/managed-command seam was approved with
the spec. Red-to-green slices reproduced the missing standalone Nu paths and
startup resources, missing Python mirror defaults, proxy escaping/name drift,
missing logs/zoxide support, unsafe non-TTY launcher, invalid pager placeholder,
missing preparation command, and overwrite of working startup on malformed
external generation. Tests now cover those behaviors, device overrides,
repeatability, actual less paging, and pre-install startup.

Actual controlling-TTY sessions prove normal Linux Nu discovery, Starship and
Pixi completion autoload, and guarded preferred/secondary launch behavior.
Nu's `-c` path intentionally omits vendor autoload; it is used only for explicit
configuration/resource validation, not as evidence of interactive discovery.

Verified: full public suite (24 tests; 23 passed, the explicit network install
case skipped), ShellCheck warning checks, `git diff --check`, and separate
`--class t9k`/`--class linux` source applications with POSIX/Bash/Zsh parsing
and standalone Nu execution. Ticket 02 separately records package installation
and ownership; this ticket borrows those executables without claiming another
installation. Native macOS, WSL x86-64 and Windows execution has since passed
in its dedicated tickets; only WSL2 ARM is unscheduled. See [shared settings](../../../SHARED_SHELL_SETTINGS.md).
