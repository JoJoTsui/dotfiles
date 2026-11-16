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

**Status:** ready-for-agent

- [ ] A missing integration is installed; an outdated one is reinstalled; a current one is not invoked again.
- [ ] Qoder calls `qodercli`; MiniMax and CodeGraph are never passed to Herdr.
- [ ] A codex reinstall is followed by resume-hook registration, and the final client-settings merge preserves both the Herdr entries and the resume hook.
- [ ] With Herdr absent the step succeeds with nothing to do; with `--apply-only` neither Herdr nor an agent installer runs.
- [ ] Unselected agents are never passed to Herdr, and their integration files are untouched.
- [ ] Herdr's generated skill exists in the shared tree when Herdr is present, is refreshed on reapply, and is exempt from pruning.
- [ ] `status` shows current/outdated/missing/unsupported per selected agent; health reports drift without failing the check.
- [ ] Tests with a fake Herdr log the invoked kinds and status reads, and cover the skip and apply-only paths.
