# 02: macOS Homebrew-first agent installation with floors

**What to build:** On macOS, resolve each selected agent through Homebrew and
then Bun. A Homebrew formula or cask at or above the catalog floor provides the
agent; a missing or below-floor package falls through to the frozen Bun project.
Codex's exact-match exception becomes a floor row, not a separate code path.
Both managed launchers point at the selected executable and are revalidated on
every apply, and the frozen project stays as the offline fallback. The
deployment records the observed provider and version in device state. A device
`agent` version entry forces a deployment-owned install. `dotfiles-agents status`
reports provider, effective version, and drift.

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] A Homebrew version at or above the floor installs no Bun project and both launchers point at the Homebrew executable.
- [ ] A Homebrew version below the floor uses the frozen Bun project and both launchers point at it.
- [ ] A Homebrew package removed after adoption is repaired or falls back on the next apply; no launcher is left broken.
- [ ] Unselected agents are untouched in both launcher directories.
- [ ] A device `agent` version override forces an exact deployment-owned install and `status` reports it as device-owned.
- [ ] The observed provider and version are recorded, and `status` shows them.
- [ ] Tests with a fake Homebrew cover at-floor, above-floor, below-floor, and missing-package cases.
