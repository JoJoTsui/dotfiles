# 13: Verify the complete deployment matrix and new-host flow

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A new-host user follows one documented deployment and
activation flow, then verifies the selected environment. A maintainer runs one
verification entry point for the complete matrix and can distinguish local,
network-dependent, and native results without exposing the current host to
deployment effects.

**Blocked by:** 12 — Update pinned deployments through an explicit verification workflow.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] The local matrix renders/checks all fourteen supported platform/architecture/role combinations, installation selections, defaults, and declared bundle outcomes.
- [ ] Verification isolates homes, package-manager/XDG roots, credentials, history fixtures, and installer effects; the current host's real home and system configuration are outside every target.
- [ ] Applicable Linux shells and harmless CLI diagnostics run against the deployed state with inherited legacy environment/tool paths removed.
- [ ] Network-enabled resolution/install checks and native macOS/Windows/WSL checks are separately identified, with required failures nonzero and unperformed checks visibly pending or unavailable.
- [ ] Native runner coverage and its limits are documented; a mocked plan or foreign template render cannot satisfy a native execution check.
- [ ] Reapplication and explicit update preserve owned versus host-local state, and documentation/secret exclusions and intended executable permissions are verified.
- [ ] New-host instructions cover profile selection, optional bundles/agent selection, Nushell startup, history activation/import, verification, and explicit updates for each supported platform.
- [ ] The remote compute example selects its role explicitly and states the current legacy host is a validation source rather than an apply target.
- [ ] Final evidence maps all twelve original requests and the accepted ADR contracts to observable passing checks or clearly identified remaining external blockers.
