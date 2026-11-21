# 02: Make agent status report what runs

Status: ready-for-agent
Blocked by: None (can start immediately)

## What to build

Show catalog intent, last successful apply, and the live command together so an operator can see where they disagree.

## Acceptance criteria

- [ ] POSIX and Windows status distinguish unavailable records, expected policy, resolved command path, actually observed version, and provider only where proven.
- [ ] A version probe with nonzero exit cannot establish a working command. Cover PATH shadowing, missing ledger, pin and floor behavior, and a device version override.
- [ ] Existing healthy commands remain identifiable; tests exercise public status with older records and capture distinct diagnostics for drift and unverified observations.

## Comments
