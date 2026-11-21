# 06: Make the ordered deployment plan match execution

Status: done
Blocked by: None (can start immediately)

## What to build

An operator can use the read-only plan to understand the order of selected work on both public bootstrap adapters.

## Acceptance criteria

- [x] Keep the existing actions field and documented entry points compatible. Add an ordered step list derived from the same selection decisions as execution where possible.
- [x] Verify plan versus observed order for full, apply-only and agents-only workloads with relevant platform and proxy/Magpie exclusions. The Linux proxy case lists installation ahead of Magpie and shell preparation.
- [x] Plans have no writes or installer calls. Synthetic comparison and native scope are identified separately.

## Comments

The Bash and portable PowerShell plan and dispatch checks passed. Unix coverage included an isolated installer fixture with the proxy ordered before Magpie and shell preparation, and actual Chezmoi file apply in both simulated Linux profiles. Native Windows evidence remains separately gated.
