# 07: Claude and MiniMax filtered profiles

**What to build:** Claude's and MiniMax's copy roots are built from the selected
profile rather than the whole library. The stale MiniMax copy disappears, Claude
receives only the profile entries, and device-created entries are preserved and
reported rather than overwritten or deleted. Both roots include the generated
Herdr skill.

**Blocked by:** 04, 06.

**Status:** done

- [x] Each copy root contains exactly the profile's managed entries plus device-created entries.
- [x] A managed entry that leaves the profile is removed from the copy root.
- [x] A device-created file or symlink with the same name is preserved and reported as a collision.
- [x] The generated Herdr skill appears in both copy roots.
- [x] Reapplying with an unchanged profile leaves file bytes unchanged.
- [x] Tests cover filtering, stale removal, device preservation, collision reporting, and idempotence.

## Comments

The copy into a managed root now inspects the destination before it writes. A
symlink at the skill path is preserved and reported, and the copy never follows
it; a regular file at the skill path is preserved and reported; an unrecorded
directory that already holds the selected bytes is adopted without a rewrite and
recorded as written; an unrecorded directory with other bytes is preserved and
reported; a directory the previous inventory recorded belongs to the deployment,
so the staged copy replaces it; a missing path is copied. The selection filter,
the disabled-skill filter, the inventory record, and the prune behaviour are
unchanged.

An entry the deployment does not own is never recorded, so it stays device
content. The stale copy a device carried before the inventory existed is
reported rather than deleted: the first apply names it, and the device owner
decides what happens to it.

The payload validation follows the same rule. It still refuses a symlinked
destination root and a symlinked instruction target, because the deployment
writes to those itself, but a symlink inside a skill destination is device
content: the copy preserves it and reports the collision instead of ending the
deployment. The copy never writes into a destination directory, so the write
cannot cross a link.

The generated Herdr skill reaches the shared tree and every other managed
`tree|skills` root, which are Claude's and MiniMax's roots today. The copy is
symlink-safe and never overwrites a device entry. The
`~/.local/state/dotfiles/generated-skills.tsv` record grows from one row to one
`name|root|generator` row per root, and the prune reader already matched the
name and the root, so the generated skill is exempt in every root.

The Pi and OpenCode profile roots are ticket 8, the skill review gate is ticket
10, and the native Windows adapter keeps its own copy path until ticket 11.
