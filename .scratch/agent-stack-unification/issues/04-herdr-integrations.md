# 04: Herdr integration trigger, repair, and generated skill

**What to build:** A deployment step that installs and repairs Herdr's own
integrations for the selected managed agents, never writing the integration
bytes. Each selected agent maps to its Herdr kind (`qoder` → `qodercli`;
MiniMax and CodeGraph have none). A missing integration is installed, an
outdated one is reinstalled, a current one is left alone. After every codex
install or reinstall, the managed resume-hook registration runs so the custom
SessionStart entry is last. The step runs in full and agents-only deployments,
never in `--apply-only`, skips cleanly when Herdr is absent, and never touches
unselected agents. When Herdr is present, its own skill output is generated into
the shared tree, refreshed on apply, exempt from pruning, and included in every
profile. `dotfiles-agents status` reports each agent's Herdr state, and
`dotfiles-agent-health --clients` reports the same drift informationally.

**Blocked by:** 01.

**Status:** done

- [x] A missing integration is installed; an outdated one is reinstalled; a current one is not invoked again.
- [x] Qoder calls `qodercli`; MiniMax and CodeGraph are never passed to Herdr.
- [x] A codex reinstall is followed by resume-hook registration, and the final client-settings merge preserves both the Herdr entries and the resume hook.
- [x] With Herdr absent the step succeeds with nothing to do; with `--apply-only` neither Herdr nor an agent installer runs.
- [x] Unselected agents are never passed to Herdr, and their integration files are untouched.
- [x] Herdr's generated skill exists in the shared tree when Herdr is present, is refreshed on reapply, and is exempt from pruning.
- [x] `status` shows current/outdated/missing/unsupported per selected agent; health reports drift without failing the check.
- [x] Tests with a fake Herdr log the invoked kinds and status reads, and cover the skip and apply-only paths.

## Comments

Review of commit `27577e6` found that the generated-skill writer followed a
symlink at `~/.agents/skills/herdr` or at `SKILL.md`, so `cp` wrote the skill
outside the managed tree, and that it ignored a failed `mkdir`/`cp`, so the
deployment reported success with no generated skill.

The writer now refuses a symlink at the skill directory and at the skill file
and names the path it refused, and a failed directory creation or write fails
the step `install-agents.herdr.skill`. The unchanged-bytes skip, the skip when
Herdr is absent or produced no bytes, and the `generated-skills.tsv` record
stay as they were. `tests/test_herdr_integrations.py` covers the symlinked
directory, the symlinked file, and a normal refresh.
