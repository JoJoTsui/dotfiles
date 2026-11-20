# 09: Preferred workflows and instruction-file audit

**What to build:** The shared instruction block names mattpocock, Herdr,
Worktrunk, and RTK as the preferred workflows for engineering method, pane
control, worktrees, and shell output. RTK stays instruction-only. The audit
proves all seven client instruction files carry the current block, the retired
Kimi file stays absent, and the per-client delta table reflects the current
caveats. No second instruction source is introduced.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] The block names the four preferred workflows and their areas, without duplicating their full instructions.
- [x] RTK has no skill entry and remains available through the shared instructions.
- [x] All seven client instruction files carry the current block after a simulated apply.
- [x] The retired Kimi instruction file is absent after apply.
- [x] The per-client delta table matches the deployed behaviour.
- [x] Tests assert the block and the seven destinations.

## Comments

The shared block opens with a Preferred workflows section. Each row names the
area and the first choice in it, and points at the place the detail already
lives: the mattpocock skills for engineering and productivity method point at
the Skills section, Herdr for pane, agent, and workspace control inside a Herdr
pane points at the generated `herdr` skill, Worktrunk for worktrees points at
the Worktree persistence and Worktree hygiene sections, and RTK for shell
output points at the RTK section. The section routes rather than repeats, so
none of the four workflows' instructions are restated.

RTK stays instruction-only. It has no row in `deployment/skills.tsv` and no
skill entry in any managed root; the deployed `~/.agents/RTK.md` and the block's
RTK section remain its only guidance.

The audit is a test, not a claim. It reads the payload catalog, applies the
deployment to a disposable home, and asserts that all seven block destinations
carry the current block, that every copy holds the same content, and that the
retired `~/.kimi-code/AGENTS.md` file stays absent even when a stale managed
block is planted there before the apply. The expected block is the shared
source plus the platform overlay, so a destination that is skipped or rendered
differently fails the audit.

The delta table in `deployment/agent-payload/CLIENTS.md` records what it had
missed: the marker-based replacement that keeps host text outside the block,
the platform overlay every copy carries, the user root each client reads and
the relocation overrides the deployment clears, the difference between the
retired user-scope `~/.kimi-code/AGENTS.md` file and the project-scope
`.kimi-code/AGENTS.md`, and the data dir that holds MiniMax's global memory.
The block itself stays one shared source; the table records the differences
instead of splitting the block into per-client copies.

Verified against disposable homes: the t9k (Linux remote-compute), Linux
workstation, and macOS workstation applies each leave the seven instruction
files with the same managed block and no retired Kimi file. The payload suite
passes. The full suite shows the same pre-existing macOS host-scope failures as
the parent commit, so nothing regressed. The pinned-client diagnostics skip
without the installed clients on this host.
