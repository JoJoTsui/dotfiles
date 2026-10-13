# 04: Install selectable coding agents through Bun

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A user gets Kimi Code, pi, opencode, Claude Code, and Codex
through Bun by default, or chooses all, none, or a named installation list.
CodeGraph is also installed by default. Each pinned CLI runs with a compatible
managed runtime rather than being declared installed merely because its package
manager completed.

**Blocked by:** 02 — Install common tools through managed installers.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] The default installs all five named agents through Bun; Codex has one managed installation source rather than competing Pixi and Bun installs.
- [ ] All, none, and named-list selection behave predictably; unknown agent names fail clearly before installation.
- [ ] Choosing none or omitting an agent does not remove an existing installation, and shared instruction/skill deployment remains the default contract.
- [ ] CodeGraph remains a default installation independent of whether any agent executable is selected; installation does not create project indexes.
- [ ] Package versions and supported locks are recorded, and Kimi Code uses its current package identity rather than the archived predecessor.
- [ ] Agent and CodeGraph runtime requirements are satisfied by the managed Node/Bun toolchain and are checked when pins change.
- [ ] Required installation failure propagates with a clear status; rerunning the same selection is idempotent.
- [ ] Controlled selection/failure checks and actual isolated harmless CLI diagnostics verify different claims; diagnostics do not log in or send model requests.
