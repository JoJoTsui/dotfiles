# 03: Preserve Windows skill collisions during preflight

**What to build:** Windows skill preflight allows the copy adapter to preserve and report safe device collisions without traversing links or modifying their targets.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Selected skill file, directory, and link collisions are preserved and reported with an offline library and fetched library.
- [ ] Unsafe parent paths and write-through attempts still fail safely.
- [ ] Behavior tests exercise the public deployment boundary.
