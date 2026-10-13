# Portable deployment review

The grill is complete and committed as `fdd818c`. These artifacts are drafts
for the `to-spec` and `to-tickets` review steps. Tracker publication and
implementation have not occurred.

## Specification review

Read the [specification](spec.md). The proposed highest testing boundary is the
deployment entry point: profile, source state, selections, and isolated target
home produce a rendered target, installation plan, and observable result.
Post-apply shell/tool behavior verifies that output. Deterministic checks,
network resolution/install checks, and native execution report separate results.

Review whether this boundary matches expectations before publishing the spec.

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

Review ticket granularity, whether each blocking edge is necessary, and whether
any tickets should be merged or split before publishing.

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

The repository has a GitHub remote for `JoJoTsui/dotfiles`, an existing
single-context glossary/ADR layout, and an installed `triage` skill. There is
no configured tracker or triage vocabulary yet.

The related setup workflow must select GitHub Issues or local Markdown, confirm
triage vocabulary, and review the resulting tracker/domain instruction draft.
The recommended GitHub configuration is prepared in the
[tracker setup proposal](tracker-setup.md); it is not active configuration.
The specification will use `ready-for-agent` when published. Tickets will be
published in dependency order, as sub-issues of the spec on a real tracker or as
one Markdown file per ticket under the configured local convention.
