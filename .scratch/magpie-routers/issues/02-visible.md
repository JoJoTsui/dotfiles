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

**Status:** ready-for-agent

- [ ] The catalog validates unknown agents and unknown group/provider names.
- [ ] The fake Magpie records `visible claude conductor,openai-stack`,
      `visible pi workhorse`, `visible dsh workhorse` in that order.
- [ ] A failing `magpie visible` aborts the apply.
- [ ] `dotfiles-magpie status` reports the three visibility rows.
- [ ] Re-running is idempotent; no client file is backed up for a visibility-only run.

## Comments
