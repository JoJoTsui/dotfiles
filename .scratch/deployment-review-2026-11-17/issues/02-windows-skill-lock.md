# 02: Require reviewed Windows skill locks

**What to build:** A Windows remote skill fetch stops before fetching when a selected skill lacks a valid matching lock, while the explicit offline library remains usable.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Missing, empty, malformed, and mismatched selected lock entries fail before remote fetch.
- [ ] Valid locked remote sources and the explicit offline-library override work.
- [ ] Behavior tests cover success and failure without relying on live downloads.
