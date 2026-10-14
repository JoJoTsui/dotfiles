# Portable deployment implementation tracker

The grill, specification, and tickets are committed in this repository. This
file tracks implementation locally; no GitHub issue tracker is configured for
these tickets. Tickets 01–12 are implemented with the evidence recorded in
their status lines and verification notes. Ticket 13 integrates the complete
matrix and onboarding flow. Native macOS, Windows and WSL2 x86-64 execution has
passed on the committed native workflows; WSL2 ARM64 is not scheduled because no
Windows ARM64 WSL2 runner is available.

## Specification review

Read the [specification](spec.md). The proposed highest testing boundary is the
deployment entry point: profile, source state, selections, and isolated target
home produce a rendered target, installation plan, and observable result.
Post-apply shell/tool behavior verifies that output. Deterministic checks,
network resolution/install checks, and native execution report separate results.

The accepted boundary separates local plan/render checks, network installation
and resolution, and native execution. See the [final matrix evidence](../../verification/complete-matrix.md).

## Ticket review

Each ticket is an end-to-end behavior with its own acceptance checks. Blockers
below list only immediate gates; transitive prerequisites are omitted. The
numbering is a valid dependency order and does not require a linear execution
schedule.

| Ticket | Blocked by | What it delivers |
| --- | --- | --- |
| [01: Isolated Linux deployment](tickets/01-isolated-linux-deployment.md) | None | Resolve a Linux profile and safely plan/apply source state to a disposable home. |
| [02: Common tools through managed installers](tickets/02-common-tools.md) | 01 | Bootstrap Pixi and pinned common tools with usable exposed commands. |
| [03: Shared Nushell-first shell behavior](tickets/03-shared-shell-behavior.md) | 02 | Standalone Nu/Bash/Zsh share values, launchers, zoxide, and log viewing. |
| [04: Selectable Bun agent installation](tickets/04-bun-agent-installation.md) | 02 | Install the five agents and CodeGraph through Bun with selection and runtime checks. |
| [05: Portable instructions and skills](tickets/05-agent-instructions-skills.md) | 04 | Each agent discovers real-file global instructions and the portable skill payload. |
| [06: CodeGraph integration without indexing](tickets/06-codegraph-integration.md) | 05 | Clients use their supported CodeGraph mechanism while project indexing stays explicit. |
| [07: Shared history and device setup](tickets/07-shared-history.md) | 03 | Record/search local history, activate encrypted sync, and optionally import synthetic legacy history. |
| [08: Selectable specialist bundles](tickets/08-specialist-bundles.md) | 02 | Install requested bio/GPU/desktop bundles or clearly reject unsupported targets. |
| [09: Native macOS deployment](tickets/09-macos-deployment.md) | 06, 07 | Both Mac architectures and roles receive the complete common deployment with native verification. |
| [10: WSL deployment](tickets/10-wsl-deployment.md) | 06, 07 | Detect WSL, deploy both roles, and verify Linux-shell behavior and Windows integration separately. |
| [11: Native Windows deployment](tickets/11-windows-deployment.md) | 06, 07 | Nu/Git Bash, Windows installer exceptions, all agents, skills, and history work natively. |
| [12: Explicit verified updates](tickets/12-explicit-updates.md) | 08, 09, 10, 11 | Deliberately refresh compatible pins/locks and revalidate the selected deployment targets. |
| [13: Complete deployment and onboarding verification](tickets/13-complete-matrix-onboarding.md) | 12 | Provide a documented new-host flow and one verification entry point covering the complete matrix. |

The numbered dependency order was used for implementation. Platform-native
claims stood pending until the corresponding native runner reported pass; they
are now recorded per platform, with WSL2 ARM64 explicitly unscheduled.

## Requirement coverage

| Original request | Primary tickets |
| --- | --- |
| 1. Diverse profiles | 01, 09, 10, 11 |
| 2. Isolated all-profile testing | Every slice; 13 integrates the complete matrix |
| 3. Nu first; shared shell settings | 03, 09, 10, 11 |
| 4. RTK through Pixi | 02, 03, 05 |
| 5. Default Pixi | 02 |
| 6. Default uv and TUNA mirror | 02, 03, 09, 10, 11 |
| 7. Bun and selectable five-agent defaults | 02, 04, 09, 10, 11 |
| 8. Default global instructions and skills | 05 |
| 9. Shared shell history | 07, 09, 10, 11 |
| 10. Default CodeGraph and agent settings | 04, 06 |
| 11. Default zoxide | 02, 03 |
| 12. Default Tailspin usage | 02, 03 |

Specialist bundles are covered by 08, and the agreed pin/update policy by 02,
04, and 12. All drafts live under the existing repository-only documentation
exclusion.

## Tracker setup

The repository-local Markdown files are the implementation tracker. The
[GitHub tracker proposal](tracker-setup.md) remains inactive; no remote issues
were created as part of the implementation.
