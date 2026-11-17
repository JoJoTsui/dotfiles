# 06: Pi defaults and generated models.json

**What to build:** `deployment/client-settings/pi-settings.json.tmpl` sets `defaultProvider=magpie` and `defaultModel=group/workhorse`, keeps `modelThinkingLevels`, and does not create `enabledModels`. Add `.pi/agent/models.json` to `.chezmoiignore` as Magpie-owned; the repo never templates it. The apply's `magpie pi group/workhorse` (ticket 02) generates the provider block and the group model entry.

**Blocked by:** 02.

**Status:** done

- [x] Rendered Pi settings name `magpie` / `group/workhorse` and no longer default to `minimax-cn`.
- [x] A fresh apply leaves `~/.pi/agent/models.json` to Magpie; the repo has no source file for it.
- [x] With the fake `magpie`, the apply calls `magpie pi group/workhorse` exactly once.
- [x] Pi client-settings tests pass.

## Comments

`deployment/client-settings/pi-settings.json.tmpl` now selects the Magpie
provider and the workhorse group. The hand-copied MiniMax model table is
gone: the template keeps one thinking level for the default group model, and
Magpie owns the context windows, the costs, and the levels of every model it
serves. The template creates no `enabledModels` list, so Pi keeps the picker
it has.

`.pi/agent/models.json` joins the ignored targets, next to the other client
files the merge owns. The repository has no source file for it, so a fresh
apply leaves the file to Magpie, which generates the provider block and the
group model entry when the apply runs `magpie pi group/workhorse`.

The merge never removes a device key, so a device whose Pi settings still
name `minimax-cn` keeps its own `modelThinkingLevels` entries; the new
provider and model replace the defaults the template owns. Clearing the old
default model on a device that already selected one by hand is the operator's
step, and `docs/MAGPIE.md` says so.

Tests run:

- `python3 -m unittest test_magpie -v` — 45 tests, all pass, including the new
  Pi checks: the template names `magpie` and `group/workhorse` and no
  `minimax-cn`, the models file is ignored and has no source, a simulated
  macOS apply renders the group defaults and writes no `models.json`, and the
  apply calls `magpie pi group/workhorse` exactly once.
