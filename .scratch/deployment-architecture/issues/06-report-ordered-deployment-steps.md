# 06: Make the ordered deployment plan match execution

Status: ready-for-agent
Blocked by: None (can start immediately)

## What to build

An operator can use the read-only plan to understand the order of selected work on both public bootstrap adapters.

## Acceptance criteria

- [ ] Keep the existing actions field and documented entry points compatible. Add an ordered step list derived from the same selection decisions as execution where possible.
- [ ] Verify plan versus observed order for full, apply-only and agents-only workloads with relevant platform and proxy/Magpie exclusions. The Linux proxy case lists installation ahead of Magpie and shell preparation.
- [ ] Plans have no writes or installer calls. Synthetic comparison and native scope are identified separately.

## Comments
