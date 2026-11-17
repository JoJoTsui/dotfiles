# 02: Per-agent visibility catalog

**What to build:** `deployment/magpie/visible.tsv` with `agent|names`, where a
name is a declared group id or a provider id. The apply validates agents and
names, then runs `magpie visible <agent> <names>` after the groups. Do not run
`--only-picked`; it freezes the current list and would hide a model starred
later. A visibility failure fails the apply. `dotfiles-magpie status` adds
`visible|agent|names` lines.

Ship `claude|conductor,openai-stack`, `pi|workhorse`, `dsh|workhorse`. A
provider id added to a row exposes that provider's starred/picked models; the
app owns the stars.

**Blocked by:** 01.

**Status:** done

- [x] The catalog validates unknown agents and unknown group/provider names.
- [x] The fake Magpie records `visible claude conductor,openai-stack`,
      `visible pi workhorse`, `visible dsh workhorse` in that order.
- [x] A failing `magpie visible` aborts the apply.
- [x] `dotfiles-magpie status` reports the three visibility rows.
- [x] Re-running is idempotent; no client file is backed up for a visibility-only run.

## Comments

- `deployment/magpie/visible.tsv` ships `claude|conductor,openai-stack`,
  `pi|workhorse`, `dsh|workhorse`, and `dotfiles/share` gets the matching
  `{{ include }}` wrapper so the managed command reads the same catalog.
- The apply reads the narrowing back with `magpie visible <agent>` (the
  `X is shown …` line), normalizes both lists, and adds a `visible:<agent>`
  change only when they differ. Execution runs after the groups and before
  the agent wiring, so `magpie pi`/`magpie dsh` regenerate the agent files
  from the narrowed list. No `--only-picked` is passed.
- A visibility-only run takes no backup: the backup step is skipped when
  every pending change is a `visible:` entry.
- `status` prints `visible|agent|names` from the live read-back, and
  `every model` for an agent that is not narrowed.

Checks:

```
DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest tests.test_magpie
Ran 87 tests ... OK

DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh --source "$PWD" \
  --home "$sim" --class t9k --apply-only   # exit 0, no catalog in the home
DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh --source "$PWD" \
  --home "$sim" --class linux --apply-only # exit 0, no catalog in the home
```

Follow-up from the live router refresh: all three agents now see all four
managed groups and the providers that serve the preferred models, and
`picked.tsv` is the exact per-agent star set. The apply writes only the
`pickedModels` key into `~/.config/magpie/settings.json` (Python merge, 0600,
other keys and agents preserved), then refreshes `magpie visible` so the
gateway serves it. A visibility or picked change also forces the Magpie-owned
wiring again, because `magpie visible` rewrites the agent model list and can
reset Pi's default; the live Pi default is back on `group/workhorse`.
