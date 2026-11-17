# Agent stack unification verification

The design is recorded in ADR [0011](../adr/0011-agent-provider-chain.md),
[0012](../adr/0012-herdr-owned-integrations.md), and
[0013](../adr/0013-single-owner-skill-library.md). The spec and the twelve
tickets are under `.scratch/agent-stack-unification/`.

Gates ran on 2026-11-17 on macOS 15.8.1 arm64. The fresh native gate is commit
`7dc9911`. The live migration was then applied from the merged `main` at
`6567edf`, after the existing-device rehearsal. The protected pre-apply backup
is `~/.local/state/dotfiles/backups/20261117T092846Z-pre-agent-stack`.

## Gates

| Gate | Result |
| --- | --- |
| Simulated macOS apply, `--class t9k --apply-only`, hermetic skill library | exit 0 |
| Simulated Linux apply, `--class linux --apply-only`, hermetic skill library | exit 0 |
| Existing-device rehearsal, private copy of this Mac's managed state | exit 0; credentials, instruction blocks, 33 Claude symlinks, and device settings preserved |
| Windows boundary, PowerShell 7.6.9, symlink-free temporary root | 30 tests, 2 skips |
| Full suite | 594 tests, 28 failures + 14 errors, 55 skips |
| Native macOS aarch64 workstation | passed |
| Live apply and post-apply skill review | exit 0; no ratchet failures |

The full-suite failure set is **identical** to the baseline captured before the
verification run: every failure is a pre-existing macOS host-scope assumption
(GNU `stat -c` in the legacy adapter, Linux-only history/host-up/worktrunk
modules, macOS-versus-Windows plan assertions). The Windows boundary tests ran
in that suite; the two Windows skips are the pinned Nu renderer and the actual
Windows installer, both native-runner gates.

The native macOS report is committed as
[`native-macos-agent-stack-2026-11-17.json`](native-macos-agent-stack-2026-11-17.json).
It records `status: passed`, `working_tree_dirty: false`, the source digest, and
the seven checks: native runtime and architecture, profile detection, default
installation 1 and 2, pinned commands and pending history, ordinary native
configuration discovery, and native shell/instruction/CodeGraph/encrypted-history
behavior.

## Provider evidence

The pre-change device ran the old providers. The live column is the state
recorded after the authorized apply.

| Agent | Before | Planned provider and floor | Live after |
| --- | --- | --- | --- |
| kimi | Bun 2.4.1 | Homebrew `kimi-code` floor 2.4.1 | Homebrew 2.6.2 |
| pi | Bun 1.5.2 | Homebrew `pi-coding-agent` floor 1.5.2 | **Bun 1.5.2**: the formula is available but not installed, and the deployment adopts, never installs |
| opencode | Bun 2.2.5 | Homebrew `opencode-v2` floor 2.2.5 | Homebrew 2.3.0 (third-party tap) |
| claude | Bun 2.1.325 | Homebrew `claude-code` floor 2.1.325 | **Bun 2.1.325**: the cask is 2.1.311, below the floor |
| codex | Homebrew 0.169.0 (device-owned) | Homebrew `codex` floor 0.166.0 | **Homebrew 0.169.0** after removing the redundant `agent|codex|0.169.0` override |
| minimax | Bun 0.7.0 | Bun | Bun 0.7.0 |
| codegraph | Bun 1.6.2 | Bun | Bun 1.6.2 |
| qoder | Native 1.1.82 | Native 1.1.82 | Native 1.1.82 |

The live `agents.lock.tsv` records:

```text
kimi|homebrew|2.6.2|2.4.1
pi|bun|1.5.2|1.5.2
opencode|homebrew|2.3.0|2.2.5
claude|bun|2.1.325|2.1.325
codex|homebrew|0.169.0|0.166.0
minimax|bun|0.7.0|0.7.0
codegraph|bun|1.6.2|1.6.2
qoder|native|1.1.82|1.1.82
```

A new login shell resolves Kimi 2.6.2, Codex 0.169.0, and OpenCode 2.3.0 from
`~/.local/bin`; Pi and Claude resolve from the frozen Bun projects. The 1.4 GB
of `.bun/managed` projects remain as the offline fallback.

## Herdr and credentials

All six managed integrations report `current`: Pi v9, Claude v11, Codex v10,
Kimi v8, OpenCode v13, and Qoder CLI v4. `qodercli` was the missing integration
before the change. The Codex resume hook remained registered, and the final
client-settings merge preserved the Herdr entries.

`.codex/auth.json` and `.pi/agent/auth.json` hashes match the pre-apply backup
exactly. All seven client instruction files carry the managed block, the
preferred-workflows section is present, and the retired Kimi file is absent.

## Skill evidence

The catalog holds 100 rows: 54 `auto`, 14 `caveman`, 28 `lark`, 4 `design`. The
live device now loads the reviewed profile:

- 55 skills per managed root: the 54 automatic entries plus the generated
  `herdr` skill. The shared tree, Claude's copy, and MiniMax's copy all agree.
- The 46 tagged pre-inventory entries were removed deliberately after the apply,
  with the pre-apply backup retaining them. The two Claude symlinks for
  `find-skills` and `resolving-merge-conflicts` are device entries and remain
  untouched.
- `managed-skills.tsv` records 160 managed directories (54 × 3 minus the two
  device symlinks that the deployment preserves rather than owns).
- `python3 deployment/update_skills.py check`: 10 catalog rows over the budget,
  17 reviewed exceptions (7 name tagged rows outside the current library), the
  generated `herdr` skill reported outside the catalog budget, and **no ratchet
  failures**.
- 37 entries in `~/.agents/.skill-lock.json` are not owned by the catalog, all
  in the disabled DeepMind group, and are reported with their exact
  `bunx skills remove` commands.

Re-enabling a group is the documented opt-in: `DOTFILES_SKILLS=design`,
`DOTFILES_SKILLS=caveman`, or `DOTFILES_SKILLS=lark` on the next apply.

## Not run and known limits

- The Linux x86-64 suite is host-scope on this Mac; its 42 failures are the
  pre-existing set above, not a regression.
- The native Windows installer and the pinned Nu renderer are native-runner
  gates; the Windows boundary logic ran under PowerShell 7.6.9.
- `dotfiles-agent-health --clients` passes. Graphify is provisioned through the
  `developer-portable` bundle (`graphifyy` 0.9.103) and the same bundle supplies
  sd, just, hyperfine, lazygit, yq, and xh. The graphify row moved from the
  Linux-only `developer` bundle because the package is a portable noarch Python
  CLI.
- The branch has not been pushed. The live backup is retained under
  `~/.local/state/dotfiles/backups/`.
