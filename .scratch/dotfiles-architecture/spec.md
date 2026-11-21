# Deepen dotfiles lifecycle modules

**Status:** ready-for-agent

**Design baseline:** `97d7ff2`. The five behavior contracts were confirmed in the design review.

## Problem Statement

Several maintenance commands expose ordering and ownership decisions their callers have to reproduce. A failed Nushell refresh can leave a live loader importing removed modules. A Herdr restore can bypass the provider-preserving Codex launcher, and editing a mixed SessionStart group can remove device hooks. Shells can disagree on proxy selection, and a failed refresh can overwrite the working profile. PortableGit can reuse its pinned installation but refuses an ordinary upgrade when the installed vendor tree contains links. Deployment checks can make assertions about the wrong adapter, fail on obsolete test data, or omit which scenarios ran.

## Solution

Give Nushell publication, proxy resolution and refresh, and PortableGit replacement each a module that owns the full decision it exposes. Use Herdr’s restore adapter to reach the existing Codex resume interface and reconcile the managed hook at entry granularity. Have native deployment adapters exercise the public commands and report the exact observed outcomes.

## User Stories

1. As a Nushell user, I want bootstrap and standalone refresh to publish the same usable completion resources, so that either command prepares my interactive shell.
2. As a Nushell user, I want each active loader to import a complete generation after a partial refresh, so that opening a shell remains possible.
3. As a macOS user, I want the active native and XDG loaders to stay usable, so that launching Nu from different shells works.
4. As a device owner, I want refresh to preserve my own startup resources, so that cleanup removes only obsolete managed generations.
5. As a Herdr user, I want a restored Codex thread to retain its saved provider, model, and reasoning effort, so that restoration behaves like the managed resume command.
6. As a Codex user, I want a hook install or removal to preserve neighboring commands in a mixed SessionStart group, so that my integrations keep running.
7. As a proxy user, I want Nushell and POSIX launchers to select the same endpoint for the same environment, so that my shell choice has no effect on routing.
8. As a proxy user, I want a managed launcher to run its child directly when no managed endpoint is healthy, so that stale inherited variables do not silently route it through an unhealthy proxy.
9. As a deployment operator, I want a failed proxy refresh to preserve the working profile, so that I can retry without provisioning again.
10. As a Windows operator, I want an existing PortableGit installation to upgrade despite ordinary vendor links, so that a pin change needs no manual move.
11. As a Windows operator, I want a failed PortableGit upgrade to preserve the previous usable runtime, so that an interrupted deployment can recover.
12. As a Windows operator, I want same-pin reapplication to reuse the verified installation, so that it stays fast and avoids unnecessary writes.
13. As a maintainer, I want the portable check to exercise both public plan interfaces, so that one adapter cannot accidentally stand in for another.
14. As a maintainer, I want report evidence tied to a checkout and a scenario outcome, so that a skipped or failed check is visible.
15. As a maintainer, I want fixture expectations tied to current catalogs and simulated-home capabilities, so that unrelated pin changes and live-only guards do not invalidate the verification.

## Implementation Decisions

- Keep the existing shell preparation and completion refresh commands as the public interface. A single publication module owns the completion-generation lifecycle from validation to retirement across the selected loaders. Each loader switch must leave a usable generation on either side. A failed refresh may leave different loaders on different complete generations. Retire a managed generation only after all managed references to it are gone. Preserve device-owned resources and the existing destination checks.
- Route Herdr’s Codex restoration through the provider-preserving resume interface. Respect the existing resume and Herdr ownership ADRs. Reconcile the exact owned hook command and preserve unrelated groups, entries, metadata, and order. Keep fresh launches on their existing route.
- Centralize endpoint precedence, health and fallback behind an interface the POSIX and Nushell launchers share. Preserve existing command arguments, exit status, supported overrides, and routing rules. Scope proxy variables to the child, including clearing the supported inherited proxy variables on direct fallback. Stage a replacement profile, validate it before publishing, and preserve the last working profile on refresh failure. Keep the deployment instance temporary and device proxy settings device-owned.
- Keep PortableGit’s pin, digest, installer selection, and same-pin reuse rules. Extract a different pin into a clean confined location, verify its required launchers and version, and replace the active runtime with recovery to the previous usable version on publication failure. Permit vendor-created links inside their owned tree without allowing writes through a substituted destination or parent. Retries must not lose the last usable installation.
- Compare shared plan fields between the public adapters. Assert their platform-specific tool and step selections in their own scenarios. Derive catalog defaults in override tests from the relevant catalog, and keep the test override different from the default. Exercise bundle selection and installation without asking simulated homes to perform live-only Magpie actions. Record the checkout SHA and passed, failed, or skipped outcome for every reported native scenario, with reason when skipped.

## Testing Decisions

- Use the existing command interfaces as test seams. Add regressions for the demonstrated failures and verify successful runs and retries. Use disposable homes and preserve test evidence for the tool version, platform, and revision.
- Run real Nu through the normal prepare and standalone refresh entry points, including a failed second publication and interactive startup through the relevant loader paths. Existing completion and deployment fixtures are prior art.
- Exercise Herdr’s restore entry point with disposable saved thread metadata for the supported provider paths. The hook test must include a mixed group and cover install, repeat install, and removal. Existing Herdr and Codex resume fixtures are prior art.
- Use a local endpoint and process fixtures to verify proxy selection, inherited environment cleanup, unchanged parent state, and invalid refresh followed by a valid retry.
- Use the public Windows installation path and validate same-pin reuse, linked vendor tree upgrade, and rollback. Portable PowerShell fixtures are regression evidence. Native Windows acceptance establishes vendor archive and platform behavior.
- Exercise source apply for the documented simulated profiles and native verification on the platforms available with a relevant scenario. A native run must identify its revision and expose skipped scenarios. Distinguish unavailable runners from passed scenarios.

## Out of Scope

- Replacing bootstrap, changing installation pins, or introducing a cross-platform installer framework beyond the PortableGit slice.
- Changing account shell, proxy service ownership, agent provider identity, Magpie wiring, or Codex profile ownership.
- Applying to an account home or publishing a branch without separate authority.

## Further Notes

Use an integration branch based on the confirmed baseline. Pi owns implementation. Codex owns the standards and spec reviews, guides fixes back to Pi, and verifies the integration evidence.
