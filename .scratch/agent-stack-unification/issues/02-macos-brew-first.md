# 02: macOS Homebrew-first agent installation with floors

**What to build:** On macOS, resolve each selected agent through Homebrew and
then Bun. A Homebrew formula or cask at or above the catalog floor provides the
agent; a missing or below-floor package falls through to the frozen Bun project.
Codex's exact-match exception becomes a floor record, not a separate code path.
Both managed launchers point at the selected executable and are revalidated on
every apply, and the frozen project stays as the offline fallback. The
deployment records the observed provider and version in device state. A device
`agent` version entry forces a deployment-owned install. `dotfiles-agents status`
reports provider, effective version, and drift.

**Blocked by:** 01.

**Status:** done

- [x] A Homebrew version at or above the floor installs no Bun project and both launchers point at the Homebrew executable.
- [x] A Homebrew version below the floor uses the frozen Bun project and both launchers point at it.
- [x] A Homebrew package removed after adoption is repaired or falls back on the next apply; no launcher is left broken.
- [x] Unselected agents are untouched in both launcher directories.
- [x] A device `agent` version override forces an exact deployment-owned install and `status` reports it as device-owned.
- [x] The observed provider and version are recorded, and `status` shows them.
- [x] Tests with a fake Homebrew cover at-floor, above-floor, below-floor, and missing-package cases.

## Comments

The catalog carries the Homebrew package of every agent Homebrew ships:
`kimi-code` and `pi-coding-agent` and `opencode-v2` as formulas, `claude-code`
and `codex` as casks. The record names the package and its kind, and a Homebrew
record carries a floor instead of an exact pin. MiniMax Code and CodeGraph keep
the deployment-owned Bun provider alone.

The POSIX adapter resolves the chain: a package at or above the floor is
adopted, and both managed launchers point at the device's executable. The
deployment reads the version from the package listing and confirms it with the
command's diagnostic, so a missing, below-floor, or removed package falls
through to the frozen Bun project and the next apply repairs the launchers. The
frozen project stays on disk as the offline fallback. The deployment never
installs or upgrades a Homebrew package.

The deployment records the observed provider, version, and floor of every
selected agent in `~/.local/state/dotfiles/agents.lock.tsv`, following the
installer-tool lock pattern. `dotfiles-agents status` reports that provider and
the effective version on POSIX and native Windows. A device `agent` version
override skips the installer-owned record, forces the deployment-owned install,
and is reported as device-owned.

`deployment/agents/providers.tsv` gained a package-kind column, so both
bootstrap adapters and the update tool read the new layout. ADR 0009 is
superseded by ADR 0011: the exact-match exception became the first floor.
