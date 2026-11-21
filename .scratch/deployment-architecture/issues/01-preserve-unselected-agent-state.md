# 01: Preserve agent records on a narrow apply

Status: ready-for-agent
Blocked by: None (can start immediately)

## What to build

Run a full apply followed by a one-agent apply on an existing simulated home. Keep the records for every agent outside that run's selection on both adapters.

## Acceptance criteria

- [ ] Native Windows reproduces full → narrow state loss before the fix and preserves the original rows afterward. The Unix regression scenario still passes.
- [x] The latest successful selected result replaces its prior row without duplicates. An unsuccessful selected install cannot publish an unverified observation.
- [x] A missing ledger and the existing ledger format remain usable. Verify via public apply and status. Run the existing Windows workflow at the tested revision or report the native gate pending.

## Comments

Portable PowerShell reproduced the dropped row before the fix and passed full-to-narrow, selected replacement, and failed-install preservation after it. Both simulated Unix profiles passed. The existing Windows workflow carries the native regression; keep native parity open until that runner executes it.
