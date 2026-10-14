# 04: Install selectable coding agents through Bun

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A user gets Kimi Code, pi, opencode, Claude Code, and Codex
through Bun by default, or chooses all, none, or a named installation list.
CodeGraph is also installed by default. Each pinned CLI runs with a compatible
managed runtime rather than being declared installed merely because its package
manager completed.

**Blocked by:** 02 — Install common tools through managed installers.

**Status:** Implemented and verified on Linux x86-64; foreign native validation
has since passed for macOS, native Windows and WSL2 x86-64 through tickets
09–11, with only WSL2 ARM64 unscheduled.

- [x] The default installs all five named agents through Bun; Codex has one managed installation source rather than competing Pixi and Bun installs.
- [x] All, none, and named-list selection behave predictably; unknown agent names fail clearly before installation.
- [x] Choosing none or omitting an agent does not remove an existing installation, and shared instruction/skill deployment remains the default contract.
- [x] CodeGraph remains a default installation independent of whether any agent executable is selected; installation does not create project indexes.
- [x] Package versions and supported locks are recorded, and Kimi Code uses its current package identity rather than the archived predecessor.
- [x] Agent and CodeGraph runtime requirements are satisfied by the managed Node/Bun toolchain and are checked when pins change.
- [x] Required installation failure propagates with a clear status; rerunning the same selection is idempotent.
- [x] Controlled selection/failure checks and actual isolated harmless CLI diagnostics verify different claims; diagnostics do not log in or send model requests.

Evidence: public `tests/test_agents.py` first failed on missing selectors and
installer behavior, then passed with the implemented boundary. Real isolated
Linux installation ran all five pinned clients plus CodeGraph through
`--version`, repeated all/none/codex/all, preserved an unrelated global registry
and CLI, and created no index or Codex auth file. The real OpenCode2 config
loader verifies V2 settings; Kimi doctors validate runtime/TUI config and its
disabled automatic upgrade. Deterministic apply tests exercise the working
source and both legacy Linux roles. See [agent ownership and pins](../../../AGENT_INSTALLATION.md).
Global instructions/skill payload delivery is still ticket 05; selectors do not
gate its default deployment. Native foreign runtime and optional Linux browser
PTY checks are not claimed by this ticket. Account activation remains local
and explicit.
