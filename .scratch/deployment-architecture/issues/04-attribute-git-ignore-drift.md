# 04: Find the first Git ignore divergence on Linux

Status: done
Blocked by: None (can start immediately)

## What to build

Give an operator evidence for the first change to the managed Git ignore path and reproduce the earlier reapplication finding.

## Acceptance criteria

- [x] Capture existence, mode and hash around fresh apply, skill discovery, fixture seeding and reapply in the affected Linux fixture. Keep path-specific findings free of file contents.
- [x] Identify the writer when reproduced, using a narrow process trace if stage observations are insufficient. Correct a demonstrated repository-owned cause with a regression check. Document an external cause or a bounded inconclusive result with exact reproduction evidence.
- [x] An inconclusive reproduction keeps the finding open. Report failed and unrun dependent checks separately and retain the existing owned-file preservation gate.

## Comments

A network-disabled Ubuntu 24.04 replay identified Qoder skills list as the writer. The preserved Qoder 1.1.82 executable reproduced the exact historical hash. The isolated test preserved the Git ignore fingerprint and returned the same 56 skill records. Fifty focused checks passed. See the Linux verification notes in docs/validation/t9k-docker.md for the retained fixture scope.
