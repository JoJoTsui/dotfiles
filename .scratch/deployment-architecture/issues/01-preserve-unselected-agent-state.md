# 01: Preserve agent records on a narrow apply

Status: ready-for-agent
Blocked by: None (can start immediately)

## What to build

Run a full apply followed by a one-agent apply on an existing simulated home. Keep the records for every agent outside that run's selection on both adapters.

## Acceptance criteria

- [ ] Native Windows reproduces full → narrow state loss before the fix and preserves the original rows afterward. The Unix regression scenario still passes.
- [ ] The latest successful selected result replaces its prior row without duplicates. An unsuccessful selected install cannot publish an unverified observation.
- [ ] A missing ledger and the existing ledger format remain usable. Verify via public apply and status. Run the existing Windows workflow at the tested revision or report the native gate pending.

## Comments
