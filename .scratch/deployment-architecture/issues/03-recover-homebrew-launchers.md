# 03: Verify provenance and recover a stale Homebrew launcher

Status: ready-for-agent
Blocked by: [02 · Make agent status report what runs](02-distinguish-agent-observations.md)

## What to build

An operator who upgrades a Homebrew agent can run its targeted update and get a working launcher tied to the installed package.

## Acceptance criteria

- [ ] Native or representative Homebrew fixtures cover an out-of-band upgrade with removal of the old versioned executable and an unrelated same-name executable earlier in PATH.
- [ ] Adoption checks the selected package's executable provenance. If a formula or cask supplies a supported stable executable path, demonstrate the upgrade behavior before using it.
- [ ] The update adopts or upgrades eligible existing packages within current ownership policy and never installs an absent Homebrew agent. Public status shows the resolved result.

## Comments
