# 03: Verify provenance and recover a stale Homebrew launcher

Status: done
Blocked by: [02 · Make agent status report what runs](02-distinguish-agent-observations.md)

## What to build

An operator who upgrades a Homebrew agent can run its targeted update and get a working launcher tied to the installed package.

## Acceptance criteria

- [x] Native or representative Homebrew fixtures cover an out-of-band upgrade with removal of the old versioned executable and an unrelated same-name executable earlier in PATH.
- [x] Adoption checks the selected package's executable provenance. If a formula or cask supplies a supported stable executable path, demonstrate the upgrade behavior before using it.
- [x] The update adopts or upgrades eligible existing packages within current ownership policy and never installs an absent Homebrew agent. Public status shows the resolved result.

## Comments

Twenty-four Homebrew fixtures covered package provenance, a same-version PATH shadow, formula opt paths, and replacement of removed cask executables. Thirteen update and fourteen installer tests passed. No real Homebrew upgrade was performed for verification.
