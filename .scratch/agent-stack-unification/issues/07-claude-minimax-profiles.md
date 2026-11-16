# 07: Claude and MiniMax filtered profiles

**What to build:** Claude's and MiniMax's copy roots are built from the selected
profile rather than the whole library. The stale MiniMax copy disappears, Claude
receives only the profile entries, and device-created entries are preserved and
reported rather than overwritten or deleted. Both roots include the generated
Herdr skill.

**Blocked by:** 04, 06.

**Status:** ready-for-agent

- [ ] Each copy root contains exactly the profile's managed entries plus device-created entries.
- [ ] A managed entry that leaves the profile is removed from the copy root.
- [ ] A device-created file or symlink with the same name is preserved and reported as a collision.
- [ ] The generated Herdr skill appears in both copy roots.
- [ ] Reapplying with an unchanged profile leaves file bytes unchanged.
- [ ] Tests cover filtering, stale removal, device preservation, collision reporting, and idempotence.
