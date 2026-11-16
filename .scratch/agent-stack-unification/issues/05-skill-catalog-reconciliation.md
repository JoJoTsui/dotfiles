# 05: Skill catalog single-owner reconciliation

**What to build:** The repository catalog becomes the sole owner of the shared
skill tree. The six skills that exist only in the `bunx skills` lockfile are
adopted as catalog rows seeded from their recorded source, path, and folder
hash. The CLI lockfile is read as device state: the deployment and the check
report every entry that is uncatalogued or disabled, with the exact
`bunx skills remove` commands, and a dedicated report exits non-zero when drift
exists so a gate can enforce it. The deployment never writes the CLI lockfile.
No managed root is written by `bunx skills`.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] Six adopted catalog rows resolve to their recorded upstream sources and pinned bytes, and the lock contains them.
- [x] Deployment and check report uncatalogued and disabled CLI entries with exact removal commands.
- [x] The drift report exits non-zero when drift exists; a normal apply reports without failing.
- [x] The CLI lockfile bytes and modification time are unchanged after a check and after an apply.
- [x] Adopted skills deploy through the existing catalog path on all supported platforms.
- [x] Tests cover adoption, uncatalogued drift, disabled drift, clean state, and the no-write guarantee.
