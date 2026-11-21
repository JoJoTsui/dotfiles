# 09: Make generated Codex profile recovery explainable

Status: done
Blocked by: None (can start immediately)

## What to build

Magpie apply and status agree on whether the selected generated profile is current, recoverable after interruption, or blocked by unexplained drift.

## Acceptance criteria

- [x] Exercise the public apply and status with existing fixture adapters. Known pending writes retry only when current fingerprints and ownership checks authorize continuation.
- [x] An intervening edit, unrecorded collision, or linked target is preserved with an actionable result. Preserve private creation, base Codex config and auth, and other clients' state.
- [x] Use existing provider-preserving resume and protected-file checks. Record real CLI and authorized native device verification separately from synthetic results. No real-home action is authorized by this ticket.

## Comments

The apply and status fixture runs covered known retries, pending fingerprint changes, collisions, and protected base/auth comparisons after a writer failure. All 50 Codex resume tests passed with checksum-verified Codex 0.169.0 and isolated loopback providers. A live Magpie account-home check requires separate authorization and remains unrun.
