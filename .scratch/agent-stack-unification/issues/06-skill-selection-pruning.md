# 06: Skill selection, tags, and managed-skill pruning

**What to build:** The reviewed default set and its tags. `auto` keeps the
mattpocock engineering and productivity skills, graphify, worktrunk, the
humanizers, show-me, pr/research and the other general entries; `caveman` keeps
the mode and `caveman-compress`; the twelve other caveman-branded skills move to
a `caveman` tag; the six generic engineering skills from that repository stay
`auto`; the four design skills and the lark skills become opt-in tags. A host
selects groups with `DOTFILES_SKILLS`. The deployment records the skill
directories it deployed per root in device state and prunes only those when they
leave a profile. Device-created skills are never removed and are reported. The
generated Herdr skill is exempt.

**Blocked by:** 04, 05.

**Status:** ready-for-agent

- [ ] The default `auto` set is the reviewed core and no tagged group deploys without selection.
- [ ] `caveman`, `design`, and `lark` selection deploys only their groups; the two default caveman entries stay available without the tag.
- [ ] Managed skill directories are recorded per root in device state.
- [ ] A skill that leaves a profile is pruned from the managed root; a device-created entry is preserved and reported.
- [ ] The generated Herdr skill survives pruning and remains in the library.
- [ ] Reapplying with an unchanged selection changes nothing.
- [ ] Tests cover selection, deselection, prune safety, device preservation, and idempotence.
