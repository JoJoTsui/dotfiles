# 07: Measure time to a usable deployment

Status: done
Blocked by: None (can start immediately)

## What to build

Produce a repeatable baseline that shows where cold setup, no-change reapply and a single-agent update spend time.

## Acceptance criteria

- [x] Measure representative macOS and Linux fixtures with matched warmed or cold caches, source/toolchain, selections and starting state for each comparison.
- [x] Record total time to a working command, stage time, retries, downloads, and owned mutations across repeat samples. Reuse the current gate and reporting paths where possible.
- [x] Identify the largest avoidable measured cost and the noise or spread. Derive the proposed speed target from the baseline and retain failures or inapplicable measurements.

## Comments

All 18 scoped baseline commands reached verified Pi 1.6.0. Three matched samples per workload cover macOS and emulated Ubuntu 20.04. The timing document records sample values, stage times, rewrites, and the limits of log-derived network observations.
