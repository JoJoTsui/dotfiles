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

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] Ordinary bootstrap uses recorded versions and supported locks rather than silently refreshing packages to latest.
- [ ] An explicit update operation refreshes managed pins/locks and Windows exception versions, producing a reviewable change set.
- [ ] Updates validate Bun/Node/agent/CodeGraph engine compatibility and the version-dependent agent integration schemas.
- [ ] Resolution checks cover common defaults and declared supported requested bundles across the target matrix; required conflicts/failures are visible.
- [ ] Isolated install/diagnostic checks and native execution verify their actual targets, with unavailable network or runtime coverage reported separately.
- [ ] Repeat update/deployment with the same version set is idempotent and does not change authentication, existing history, project indexes, or unrelated installations.
- [ ] Documentation describes refreshing, reviewing, verifying, and applying a version set without claiming an unverified update passed.
