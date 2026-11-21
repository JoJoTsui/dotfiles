# 04: Find the first Git ignore divergence on Linux

Status: ready-for-agent
Blocked by: None (can start immediately)

## What to build

Give an operator evidence for the first change to the managed Git ignore path and reproduce the earlier reapplication finding.

## Acceptance criteria

- [ ] Capture existence, mode and hash around fresh apply, skill discovery, fixture seeding and reapply in the affected Linux fixture. Keep path-specific findings free of file contents.
- [ ] Identify the writer when reproduced, using a narrow process trace if stage observations are insufficient. Correct a demonstrated repository-owned cause with a regression check. Document an external cause or a bounded inconclusive result with exact reproduction evidence.
- [ ] An inconclusive reproduction keeps the finding open. Report failed and unrun dependent checks separately and retain the existing owned-file preservation gate.

## Comments
