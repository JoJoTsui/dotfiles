# 07: Measure time to a usable deployment

Status: ready-for-agent
Blocked by: None (can start immediately)

## What to build

Produce a repeatable baseline that shows where cold setup, no-change reapply and a single-agent update spend time.

## Acceptance criteria

- [ ] Measure representative macOS and Linux fixtures with matched warmed or cold caches, source/toolchain, selections and starting state for each comparison.
- [ ] Record total time to a working command, stage time, retries, downloads, and owned mutations across repeat samples. Reuse the current gate and reporting paths where possible.
- [ ] Identify the largest avoidable measured cost and the noise or spread. Derive the proposed speed target from the baseline and retain failures or inapplicable measurements.

## Comments
