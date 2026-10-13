# 09: Deliver native macOS deployment for both roles

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** An Intel or Apple silicon Mac user selects workstation or
remote compute and receives the complete common environment with Nushell-first
shells, all five agents, instructions/skills, CodeGraph access, and history
integration. Native checks establish Mac execution separately from Linux
rendering.

**Blocked by:** 06 — Configure CodeGraph access without automatic indexing;
07 — Enable shared shell history and deliberate device setup.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] Platform detection and explicit macOS selection render correct target paths for Intel/Apple silicon and both host roles.
- [ ] Common pinned dependencies resolve for both architectures, with Linux-specific exposures or required packages excluded or adapted.
- [ ] Native user-scoped bootstrap installs and exposes the common tools and all default Bun-managed agents with compatible runtimes.
- [ ] Standalone Nushell, Zsh, and Bash share intended values and integrations; interactive preference does not change the account login shell implicitly.
- [ ] Agent instruction/skill discovery, supported CodeGraph integration, TUNA configuration, zoxide, Tailspin logs, and pending/activated history behavior work through the deployment boundary.
- [ ] Role-specific settings follow the chosen role, and real-file output/idempotence preserve local credentials and unrelated user state.
- [ ] Native macOS runner checks exercise installation and shell/tool behavior for the declared architectures; unavailable native execution is reported pending, not passed by a Linux render.
