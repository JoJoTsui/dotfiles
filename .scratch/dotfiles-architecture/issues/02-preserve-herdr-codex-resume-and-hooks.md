# 02. Preserve Codex threads and hooks in Herdr

**What to build:** Restore Codex threads from Herdr through the existing provider-preserving resume interface. Reconcile the managed SessionStart hook at command granularity.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] Herdr restoration uses the saved provider, model, and reasoning effort for each supported provider path. Fresh launches use their existing route.
- [ ] Install, repeat install, and removal preserve device hook commands and metadata within mixed SessionStart groups.
- [ ] Herdr continues to own its integration entries, and the managed resume hook retains the required ordering.
- [ ] Regressions exercise the public launcher and hook commands with a disposable home.
