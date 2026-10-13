# 09: Deliver native macOS deployment for both roles

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** An Intel or Apple silicon Mac user selects workstation or
remote compute and receives the complete common environment with Nushell-first
shells, all five agents, instructions/skills, CodeGraph access, and history
integration. Native checks establish Mac execution separately from Linux
rendering.

**Blocked by:** 06 — Configure CodeGraph access without automatic indexing;
07 — Enable shared shell history and deliberate device setup.

**Status:** Implemented; native macOS execution pending CI.

- [x] Explicit macOS selection renders native target paths for Intel/Apple silicon and both roles; the native gate also checks Darwin/architecture detection.
- [x] Common pinned dependencies resolve for both architectures through the existing foreign-target gate; macOS reuses that exact common catalog.
- [ ] Native user-scoped bootstrap installs and exposes the common tools and all default Bun-managed agents with compatible runtimes.
- [ ] Standalone Nushell, Zsh, and Bash share intended values and integrations; interactive preference does not change the account login shell implicitly.
- [ ] Agent instruction/skill discovery, supported CodeGraph integration, TUNA configuration, zoxide, Tailspin logs, and pending/activated history behavior work through the deployment boundary.
- [x] Role-specific rendering, regular-file output, idempotence, credentials and unrelated state preservation passed in all four isolated combinations.
- [ ] Native macOS runner checks exercise installation and shell/tool behavior for the declared architectures; unavailable native execution is reported pending, not passed by a Linux render.

Implementation: [macOS deployment](../../../MACOS_DEPLOYMENT.md). Distinct local
and pending native layers: [verification evidence](../../../verification/macos.md).
The committed native workflow covers both architectures/roles and requires
installed commands and ordinary discovery. Unchecked runtime criteria await
native execution; their implementation is included in this ticket.
