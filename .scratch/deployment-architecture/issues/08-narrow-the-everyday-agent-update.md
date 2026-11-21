# 08: Make single-agent updates fast and scoped

Status: ready-for-agent
Blocked by: [01 · Preserve agent records on a narrow apply](01-preserve-unselected-agent-state.md), [03 · Verify provenance and recover a stale Homebrew launcher](03-recover-homebrew-launchers.md), [06 · Make the ordered deployment plan match execution](06-report-ordered-deployment-steps.md), [07 · Measure time to a usable deployment](07-measure-deployment-baseline.md)

## What to build

An everyday single-agent update runs only work needed by the selected agent and its verified dependencies, and tells the operator what it repaired or skipped.

## Acceptance criteria

- [ ] Map dependencies from existing public scenarios. Leave unselected agents and unrelated skill, shell, and settings drift for a full apply. Keep existing --agents-only behavior compatible.
- [ ] Changed effective inputs, a missing launcher, a broken executable, and relevant dependency changes trigger repair. Verification protects ownership even when inputs match.
- [ ] Measure repeated matched before and after runs and report time to a working command. Keep only optimizations with savings beyond observed variation and passing repair and preservation checks.

## Comments
