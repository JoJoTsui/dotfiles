# 13: Verify the complete deployment matrix and new-host flow

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A new-host user follows one documented deployment and
activation flow, then verifies the selected environment. A maintainer runs one
verification entry point for the complete matrix and can distinguish local,
network-dependent, and native results without exposing the current host to
deployment effects.

**Blocked by:** 12 — Update pinned deployments through an explicit verification workflow.

**Status:** Implemented. Local matrix, deterministic tests, and opt-in Linux
network/install verification passed on 2026-10-13. Native runner execution is
reported separately: macOS, native Windows and WSL2 x86-64 have since passed
(runs 38524061897, 38524061998 and 38524061914 at commit `81857d6`), and only
WSL2 ARM64 remains unscheduled because no Windows ARM64 WSL2 runner exists.

- [x] The local matrix renders/checks all fourteen supported platform/architecture/role combinations, installation selections, defaults, and declared bundle outcomes.
- [x] Verification isolates homes, package-manager/XDG roots, credentials, history fixtures, and installer effects; the current host's real home and system configuration are outside every target.
- [x] Applicable Linux shells and harmless CLI diagnostics run against the deployed state with inherited legacy environment/tool paths removed by the opt-in network verifier.
- [x] Network-enabled resolution/install checks and native macOS/Windows/WSL checks are separately identified, with required failures nonzero and unperformed checks visibly pending or unavailable.
- [x] Native runner coverage and its limits are documented; a mocked plan or foreign template render cannot satisfy a native execution check.
- [x] Reapplication and explicit update preserve owned versus host-local state, and documentation/secret exclusions and intended executable permissions are verified by the existing acceptance suite.
- [x] New-host instructions cover profile selection, optional bundles/agent selection, Nushell startup, history activation/import, verification, and explicit updates for each supported platform.
- [x] The remote compute example selects its role explicitly and states the current legacy host is a validation source rather than an apply target.
- [x] Final evidence maps all twelve original requests and the accepted ADR contracts to observable passing checks or clearly identified remaining external blockers.
