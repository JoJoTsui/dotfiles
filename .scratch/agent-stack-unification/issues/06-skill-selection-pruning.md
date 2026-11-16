# 06: Skill selection, tags, and managed-skill pruning

**What to build:** The reviewed default set and its tags. `auto` keeps the
mattpocock engineering and productivity skills, graphify, worktrunk, the
humanizers, show-me, pr/research and the other general entries; `caveman` keeps
the mode and `caveman-compress`; the fourteen other caveman-branded skills move to
a `caveman` tag; the six generic engineering skills from that repository stay
`auto`; the four design skills and the lark skills become opt-in tags. A host
selects groups with `DOTFILES_SKILLS`. The deployment records the skill
directories it deployed per root in device state and prunes only those when they
leave a profile. Device-created skills are never removed and are reported. The
generated Herdr skill is exempt.

**Blocked by:** 04, 05.

**Status:** done

- [x] The default `auto` set is the reviewed core and no tagged group deploys without selection.
- [x] `caveman`, `design`, and `lark` selection deploys only their groups; the two default caveman entries stay available without the tag.
- [x] Managed skill directories are recorded per root in device state.
- [x] A skill that leaves a profile is pruned from the managed root; a device-created entry is preserved and reported.
- [x] The generated Herdr skill survives pruning and remains in the library.
- [x] Reapplying with an unchanged selection changes nothing.
- [x] Tests cover selection, deselection, prune safety, device preservation, and idempotence.

## Comments

The catalog now holds 54 `auto` rows, 14 `caveman` rows, 28 `lark` rows, and 4
`design` rows. The caveman mode and `caveman-compress` stay automatic, and the
six generic engineering skills of the caveman repository stay automatic because
they are general workflows rather than caveman voice. The reviewed lock records
the same selection as the catalog, so `update_skills.py check` passes.

The selection applies to the fetch and to the copy into a managed root, so a
library supplied through `DOTFILES_SKILLS_DIR` deploys the selected skills and
nothing else. That keeps the profile the same on a device that fetches and on a
host that supplies its own library. A name the catalog does not declare is
device content and never enters a managed root.

The deployment records the directories it wrote in
`~/.local/state/dotfiles/managed-skills.tsv`, one `name|root` row per
directory, and the prune step runs after the payload copy. A recorded directory
that leaves the selection is removed from its root; the exemptions keep the
prune inside the deployment's ownership. A device-created skill is preserved and
reported, a generated skill named in `generated-skills.tsv` is preserved, and a
symlinked entry is refused rather than followed or deleted through.

The payload validation follows the same selection: it refuses a symlinked
destination for a skill the deployment writes, and leaves the destination of a
skill the selection excludes to the prune, which preserves it.

Native Windows keeps its own adapter, which does not yet consume the selection
or the inventory. That parity is ticket 11.
