# 11: Deliver the common environment on native Windows

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A native Windows x86-64 user selects workstation or remote
compute and receives Nushell, Git Bash for subprocesses, common tools, all five
agents, portable instructions/skills, CodeGraph integration, and Atuin history.
Pinned user-scoped installer exceptions close the Windows package gaps.

**Blocked by:** 06 — Configure CodeGraph access without automatic indexing;
07 — Enable shared shell history and deliberate device setup.

**Status:** Implemented; native Windows execution passed in run
[38524061998](https://github.com/JoJoTsui/dotfiles/actions/runs/38524061998) at
commit `81857d6`, 2026-10-14, for both roles. Local Linux PowerShell
planning/copy application and actual Atuin explicit-file migration checks
passed. See [Windows evidence](../../../verification/windows.md) for the
verified cells and the two gates deliberately deferred for an interactive host.

- [x] Native Windows detection, explicit selection, and both roles produce correct native home/configuration/tool paths; Windows ARM is rejected as outside the initial target matrix.
- [x] Pixi installs supported required packages, including RTK, uv, Nushell, zoxide, Tailspin, and the compatible Node runtime.
- [x] Pinned upstream Windows steps install Bun and Atuin where conda-forge has no native package; Git Bash provides the required agent subprocess environment.
- [x] All five agents install through Bun and run harmless native diagnostics; Kimi Code finds its supported Git Bash subprocess shell.
- [x] Nushell is the primary managed interactive shell, Git Bash retains its appropriate role, and the full Nushell/Zsh/Bash promise is reserved for WSL.
- [x] Native uv/pip discover TUNA configuration, and zoxide, Tailspin logs, and applicable Atuin hooks/setup work in the available managed shells.
- [x] All clients discover portable real-file instructions/skills and supported CodeGraph configuration without automatic indexing or overwriting unrelated client state.
- [x] User-scoped bootstrap/reapplication preserve credentials and history; required installer failure propagates and account activation pending is reported distinctly.
- [x] Native Windows runner tests exercise these behaviors; Linux render/plan success is not represented as native Windows execution.

The public `bootstrap.ps1` boundary, pinned exception catalog, shared shell
adapters, payload/client merge, history migration and native runner are in this
ticket. The native workflow has now run for both roles, so every check above is
satisfied. No system/account change, real credential request, existing history
read or user-project index was used during local validation.

TDD evidence: public planning failed before the boundary existed; copy/reapply
and exception ownership failed before their adapters existed. A native Nu
history preservation regression failed when copying the rendered directory and
passed after limiting copies to source-owned config files. Explicit-file Nu
import tests failed before the public aliases/parser and passed against actual
Atuin 18.23. The native fixtures are committed for Windows execution; Linux
syntax checks do not validate Windows executables, consoles or Known Folders.
The ordinary Nu startup probe also failed with the pin's `-c` mode (missing
EDITOR), then passed with `-e`, an explicit JSON print and exit. Its isolated
XDG roots precede startup and it uses no individual config-file flags.

After integrating native macOS and WSL changes, the full applicable repository
suite passed 87 tests in 294.755 seconds: 72 executed and 15 explicitly skipped.
The two WSL PowerShell planning/refusal checks omitted by that invocation's
tool-flag naming passed separately in 1.573 seconds. Native Windows runtime
acceptance has since passed for both roles in run 38524061998; no skipped cell
was counted as native execution there either.
After the corrected WSL startup integration at a720b3c, the applicable selector
and shared startup suite passed 40 tests in 162.083 seconds: 39 executed, with
only the actual native Windows installation test skipped. The native installer
provides both `.cmd` and bare POSIX companion agent launchers; their Windows
execution through Nu/Git Bash was verified by that native gate.

## Deferred to an interactive Windows host

Two claims stay unexercised on purpose and are marked for a later interactive
session rather than counted here. The unredirected Known Folder fallback needs a
host started with XDG absent, which the disposable-home contract forbids, and
the console cancellation/TOTP/browser path needs a hosted Atuin account, which
this repository's synthetic-only policy excludes. See
[Windows evidence](../../../verification/windows.md) for both notes; the passing
console fixture covers only normal and failed child restoration and must not be
read as covering them.
