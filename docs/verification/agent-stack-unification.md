# Agent stack unification verification

Branch `agent-stack-unification`, based on `main` at `007b928`. The design is
recorded in ADR [0011](../adr/0011-agent-provider-chain.md),
[0012](../adr/0012-herdr-owned-integrations.md), and
[0013](../adr/0013-single-owner-skill-library.md). The spec and the twelve
tickets are under `.scratch/agent-stack-unification/`.

The gate below was run on 2026-11-17 on macOS 15.8.1 arm64, from commit
`7dc9911`. No deployment was applied to the account home.

## Gates

| Gate | Result |
| --- | --- |
| Simulated macOS apply, `--class t9k --apply-only`, hermetic skill library | exit 0 |
| Simulated Linux apply, `--class linux --apply-only`, hermetic skill library | exit 0 |
| Windows boundary, PowerShell 7.6.9, symlink-free temporary root | 30 tests, 2 skips |
| Full suite | 594 tests, 28 failures + 14 errors, 55 skips |
| Native macOS aarch64 workstation | passed |
| Skill review check | 100 catalog entries, 17 reviewed exceptions, ratchet pass, 37 CLI-lock drift entries |

The full-suite failure set is **identical** to the baseline captured before the
verification run: every failure is a pre-existing macOS host-scope assumption
(GNU `stat -c` in the legacy adapter, Linux-only history/host-up/worktrunk
modules, macOS-versus-Windows plan assertions). The Windows boundary tests ran in
that suite; they were not skipped. The two Windows skips are the pinned Nu
renderer and the actual Windows installer, both native-runner gates.

The native macOS report is committed as
[`native-macos-agent-stack-2026-11-17.json`](native-macos-agent-stack-2026-11-17.json).
It records `status: passed`, `working_tree_dirty: false`, the source digest, and
the seven checks: native runtime and architecture, profile detection, default
installation 1 and 2, pinned commands and pending history, ordinary native
configuration discovery, and native shell/instruction/CodeGraph/encrypted-history
behavior.

## Provider evidence

The current device runs the pre-change providers. The planned resolution below
uses the host's installed Homebrew versions and the catalog floors. It was not
applied to the account home.

| Agent | Current device | Planned provider and floor | Effective on this device |
| --- | --- | --- | --- |
| kimi | Bun 2.4.1 | Homebrew `kimi-code` floor 2.4.1 | Homebrew 2.6.2 |
| pi | Bun 1.5.2 | Homebrew `pi-coding-agent` floor 1.5.2 | **Bun 1.5.2**: the formula is available but not installed, and the deployment adopts, never installs |
| opencode | Bun 2.2.5 | Homebrew `opencode-v2` floor 2.2.5 | Homebrew 2.3.0 (third-party tap) |
| claude | Bun 2.1.325 | Homebrew `claude-code` floor 2.1.325 | **Bun 2.1.325**: the cask is 2.1.311, below the floor |
| codex | Homebrew 0.169.0 (device-owned) | Homebrew `codex` floor 0.166.0 | **Homebrew 0.169.0** after removing the redundant `agent|codex|0.169.0` override; with the override it is Bun 0.169.0 |
| minimax | Bun 0.7.0 | Bun | Bun 0.7.0 |
| codegraph | Bun 1.6.2 | Bun | Bun 1.6.2 |
| qoder | Native 1.1.82 | Native 1.1.82 | Native 1.1.82 |

The macOS plan reports Homebrew as the first provider for the five agents
Homebrew ships and the Bun fallback in the `fallback` field. The actual selection
also requires the installed package to meet the floor, which is why Claude stays
on Bun until the cask reaches 2.1.325, and Pi stays on Bun because its formula is
not installed. The existing `agent|codex|0.169.0` override forced a
deployment-owned Bun install; the migration removes it, and the rehearsal then
adopted Homebrew 0.169.0.

The current device still resolves Kimi and OpenCode from `~/.bun/bin` because the
change has not been applied. Ticket 03 makes `~/.local/bin` win on macOS, so the
next apply points both launchers at the Homebrew executable.

## Skill evidence

`python3 deployment/update_skills.py check` against the deployed library:

- 100 catalog entries: 54 `auto`, 14 `caveman`, 28 `lark`, 4 `design`.
- 17 rows over the measured budget, all recorded as reviewed exceptions with
  their description length, root lines, reference presence, and a reason.
- Ratchet: no failures; every exception matches its measured row.
- 37 entries in `~/.agents/.skill-lock.json` are not owned by the catalog, all
  in the disabled DeepMind group, and are reported with their exact
  `bunx skills remove` commands.

The current device still holds all 100 pre-inventory skill directories, so the
first apply without `DOTFILES_SKILLS` deploys the 54 automatic entries and
reports the tagged leftovers rather than deleting them. The deliberate migration
is documented in [agent payloads](../AGENT_PAYLOAD.md) and
[skill review](../SKILL_REVIEW.md#migrating-a-pre-inventory-device).

## Not run

- The Linux x86-64 suite is host-scope on this Mac; its 42 failures are the
  pre-existing set above, not a regression.
- The native Windows installer and the pinned Nu renderer are native-runner
  gates; the Windows boundary logic ran under PowerShell 7.6.9.
- No real-home apply. The account home remains on the pre-change providers and
  the pre-inventory skill tree until an explicitly authorized application.
