# 09: Finish isolated Codex profile safety

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** a selected separate Magpie profile that cannot write through device-owned filesystem aliases, is recoverable on failure, and has been verified with the actual pinned CLI in an isolated home.

- [ ] Public apply regressions first demonstrate linked Codex-parent and hard-linked profile/catalog failures, including previously recorded wiring; minimal fixes reject them before gateway mutation and preserve aliased bytes.
- [ ] A fresh Codex directory can be created privately when absent; files, directories, and malformed/link collisions fail clearly without widening ownership.
- [ ] Base configuration/auth hashes, private profile creation, backups, interruption retry, drift repair, status, and exact selection exclusion remain covered.
- [ ] Inspect real scope/getter behavior. If ordinary integration is connected or scope cannot safely change, fail before avoidable gateway mutation using a supported read-only preflight when available. Do not disconnect or retag.
- [ ] Exercise the catalog-pinned CLI's version and profile operations in a fresh synthetic home with fake data and no access to the live gateway; record complete output checks and base config/auth hashes without displaying credentials.
- [ ] Adapt the implementation/fixtures to demonstrated pinned behavior rather than making the fake CLI an invented contract.
- [ ] Full synthetic Magpie tests, Bash 3.2 syntax, whitespace checks, and focused real-CLI checks pass; document any blocked runtime check honestly.
- [ ] Update the ownership/rollback contract in the same logical fix; commit it with the required attribution after supervisor review.

## Comments

The user explicitly authorized isolated execution of the digest-verified ARM64 CLI. New permission denials remain binding. No real credentials, session files, or gateway state may be used. Existing deployment-managed drift repair is intended and backed up; unrecorded collisions remain device-owned. The fixed gateway port is the documented contract, not a new configurable-port requirement.

Supervisor checkpoint: profile foundation committed as `37dc127`. Pi's read-only assessment completed; its source findings are evidence, not automatic scope additions. Persistent implementation worktree: `/Users/joey/SHELL/dotfiles.fix-macos-codex-profile-safety` on `fix/macos-codex-profile-safety`. Pi's startup initially failed because read operations acquire real-home lock directories; no implementation edits occurred in those attempts. The user explicitly approved Pi's documented `--no-approve` project-resource distrust flag. The native write sandbox remains intact. The current attempt uses a task-owned Pi configuration with the repository's public local gateway marker, not copied authentication/settings stores. Supervisor review, commit/integration, real-device checks, and cleanup remain pending.

The first isolated-state implementation process timed out at 2400 seconds; this was not a quota failure. Its work/report survived. A recovered complete log records 276 tests in 711.613 seconds, OK; the native CLI report includes source-proven fake routing and synthetic before/after hashes. Supervisor public-apply review then reproduced two uncovered fail-open defects: (1) a scope getter printing a recognized answer but exiting44 still permitted gateway mutations because its pipeline discarded the CLI status; (2) a failing stat caused link count to default to1 and a recorded hard-linked profile alias was modified before the eventual failure. Pi is implementing regressions/minimal fixes in the same worktree. The ticket is not accepted or merged. Runtime scripts that merely print statuses/digests are observed evidence, not reusable asserted acceptance; guard/assertion improvements remain under review.
