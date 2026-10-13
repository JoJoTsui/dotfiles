# 12: Update pinned deployments through an explicit verification workflow

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A maintainer deliberately refreshes compatible package pins
and supported locks, sees the resulting changes, and revalidates common tools,
selected bundles, and agents for the declared targets before treating the update
as tested. Ordinary bootstrap continues to install the recorded version set.

**Blocked by:** 08 — Install selectable specialist tool bundles;
09 — Deliver native macOS deployment for both roles;
10 — Deliver WSL deployment and verify its Windows integration;
11 — Deliver the common environment on native Windows.

**Status:** Implemented; candidate network resolution and native runner results remain external checks.

- [x] Ordinary bootstrap uses recorded exact versions and frozen Bun lockfiles; no bootstrap path refreshes packages to latest. Pixi global has no committed transitive lock, which is documented.
- [x] `deployment/update_versions.py refresh` applies an explicit proposal to a staged source copy, regenerates changed Bun locks, checks manager/Windows pins, and writes a reviewable diff only after validation.
- [x] Agent candidate metadata is checked against the pinned Node version; `verify` checks all agent Node engines, frozen Bun locks, and agent/CodeGraph/Windows configuration contracts.
- [x] An opt-in network test resolves the common environments and every declared supported bundle/target pair in a temporary Pixi workspace. Resolver failures are nonzero.
- [ ] Isolated install/diagnostic checks and native execution verify their actual targets, with unavailable network or runtime coverage reported separately.
- [x] Reapplying the same proposal is idempotent; refresh writes only deployment source catalogs, assets, and agent package/lock files, never device credentials, history, project indexes, or installations.
- [x] [Update verification guide](../../verification/updates.md) documents proposal, review, resolution, and native verification boundaries.
