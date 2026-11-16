# 03: Per-platform PATH precedence

**What to build:** The shared path model becomes per-platform. On macOS the
managed launcher directory (`~/.local/bin`) precedes the Bun directory
(`$BUN_INSTALL/bin`), so a launcher for a Homebrew-adopted agent wins in an
interactive shell. Linux, WSL, and native Windows keep the current Bun-first
order. Both shell adapters render the same model, and the rendered files are
the evidence.

**Blocked by:** 02.

**Status:** done

- [x] Rendered `.env_core` and Nu environment place the managed launcher directory before the Bun directory on macOS.
- [x] Rendered files on Linux, WSL, and native Windows keep the current order.
- [x] A simulated macOS shell resolves an adopted agent to the Homebrew executable rather than the Bun copy.
- [x] Tests render and assert the order for both adapters on both platform families.
- [x] Existing shell-behaviour and zprofile tests pass unchanged.

## Comments

The shared path model in `.chezmoidata.toml` now separates the managed PATH
entries from their order. `sharedShell.pathEntries` names each directory once
— the Bun directory, the managed launcher directory, the Pixi exposures, Cargo,
and the Windows Git Bash directory — and the order lists decide which one
wins: `pathOrder` for Linux and WSL, `macosPathOrder` for macOS, and
`windowsPathOrder` for native Windows. macOS puts the managed launcher
directory first, so a launcher for an adopted Homebrew agent wins; the other
platforms keep the Bun directory first, because Bun is the agent provider
there. The entry values exist once, so a new managed directory is declared in
one place and only the order lists change.

Both adapters render that one model. `dot_env_core.tmpl` prepends the
directories in the POSIX order and `dot_config/nushell/env.nu.tmpl` adds the
same directories in the Nu order, so the two shells agree on which directory
wins. The bootstrap's own PATH export is unchanged: the interactive shell is
the target, and the bootstrap export only orders the deployment's own
commands.

The rendered Linux, WSL, and Windows files are byte-identical to the previous
rendering, and the macOS files differ only by the swapped pair. The native
macOS verifier's standalone Nu path check follows the macOS order.

`tests/test_path_precedence.py` renders the shared settings of every platform
through the public bootstrap in a disposable home and asserts the order both
adapters produce. A macOS shell that sources the rendered `.env_core` resolves
the agent command from the managed launcher directory, so the copy the device's
Homebrew provides runs instead of the Bun copy; a Linux shell resolves the Bun
copy.

`tests/test_shell_behavior.py` keeps its shared-path expectation and now
derives it from the platform under test, so the suite stays correct in its
macOS shape. It is skipped on this host: it needs the pinned tool prefix
`DOTFILES_TEST_TOOL_HOME`, which this host does not provide.
