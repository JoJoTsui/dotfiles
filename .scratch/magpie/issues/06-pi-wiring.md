# 06: Pi defaults and generated models.json

**What to build:** `deployment/client-settings/pi-settings.json.tmpl` sets `defaultProvider=magpie` and `defaultModel=group/workhorse`, keeps `modelThinkingLevels`, and does not create `enabledModels`. Add `.pi/agent/models.json` to `.chezmoiignore` as Magpie-owned; the repo never templates it. The apply's `magpie pi group/workhorse` (ticket 02) generates the provider block and the group model entry.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] Rendered Pi settings name `magpie` / `group/workhorse` and no longer default to `minimax-cn`.
- [ ] A fresh apply leaves `~/.pi/agent/models.json` to Magpie; the repo has no source file for it.
- [ ] With the fake `magpie`, the apply calls `magpie pi group/workhorse` exactly once.
- [ ] Pi client-settings tests pass.

## Comments
