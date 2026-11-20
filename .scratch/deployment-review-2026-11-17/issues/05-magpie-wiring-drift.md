# 05: Detect and reconcile Magpie wiring drift

**What to build:** Gateway status reflects actual managed client wiring, and reapply repairs missing or drifted managed wiring without overwriting unrelated device state.

**Blocked by:** 04: Gate and back up Magpie client migration.

**Status:** ready-for-agent

- [ ] Missing or incorrect required wiring is reported and produces the documented status result.
- [ ] Reapply repairs managed wiring even when recorded desired state is unchanged.
- [ ] Tests exercise drift and preservation using disposable client state.

## Comments

The first uncommitted implementation falsely reported healthy wiring because the Python heredoc consumed the expected keys, and it used the wrong Pi thinking-level key. A later synthetic probe confirms both cases now report drift. The updated Magpie suite passed all 118 tests, including drift reporting and regeneration of Pi's missing model file. This ticket remains blocked by ticket 04 and final integration review.
