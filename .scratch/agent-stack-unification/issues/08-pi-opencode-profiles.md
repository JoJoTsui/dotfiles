# 08: Pi and OpenCode profile roots

**What to build:** Pi and OpenCode receive a profile root through the `skills`
path already present in their merged settings, instead of the whole shared tree.
The root contains exactly the selected profile plus the generated Herdr skill.
The change must not create duplicate discovery: if either client treats the
setting as additive to a shared root, the test proves there is no duplicate name
and the documented behaviour records the limitation.

**Blocked by:** 04, 06.

**Status:** ready-for-agent

- [ ] Pi's merged settings point at a profile root whose contents match the selection.
- [ ] OpenCode's merged settings point at a profile root whose contents match the selection.
- [ ] No skill name is discovered twice by either client from a managed root.
- [ ] The generated Herdr skill appears in both roots.
- [ ] A profile change is reflected on the next apply without leftover entries.
- [ ] Tests cover both clients, the profile contents, duplicate absence, and reapply.
