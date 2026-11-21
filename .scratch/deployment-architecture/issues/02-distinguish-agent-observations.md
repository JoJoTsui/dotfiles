# 02: Make agent status report what runs

Status: done
Blocked by: None (can start immediately)

## What to build

Show catalog intent, last successful apply, and the live command together so an operator can see where they disagree.

## Acceptance criteria

- [x] POSIX and Windows status distinguish unavailable records, expected policy, resolved command path, actually observed version, and provider only where proven.
- [x] A version probe with nonzero exit cannot establish a working command. Cover PATH shadowing, missing ledger, pin and floor behavior, and a device version override.
- [x] Existing healthy commands remain identifiable; tests exercise public status with older records and capture distinct diagnostics for drift and unverified observations.

## Comments

The POSIX and portable PowerShell public status checks cover older and missing ledgers, device overrides, shadowed commands, nonzero probes, and launcher provenance. Final review added regressions for lookalike launchers and exact version tokens.
