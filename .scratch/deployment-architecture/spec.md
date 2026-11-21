# Trustworthy and faster dotfiles deployment

Status: ready-for-agent

## Problem Statement

Targeted agent updates can damage the record for skipped agents or revisit
unrelated work. Status does not consistently distinguish policy, history,
and live behavior. Operators cannot reliably explain a red reapplication or
judge where deployment spends its time. Recovery of the Magpie-generated
Codex profile is hard to reason about across apply and status.

## Solution

Make agent updates observable and preserve unselected state. Run comparable
scenarios across the native deployment adapters, make the read-only plan
describe execution order, and measure targeted deployment before removing
work. Concentrate generated Codex profile recovery at its existing ownership
seam.

## User Stories

1. As a Windows operator, I want a narrow apply to preserve skipped agents'
   ledger entries, so that their status remains useful.
2. As an operator, I want to see catalog intent, last applied state, and the
   current executable separately, so that I can diagnose drift.
3. As a Mac operator, I want Homebrew adoption to verify package provenance,
   so that an unrelated command with the same version cannot pass.
4. As a Mac operator, I want a scoped update after a Homebrew upgrade to
   restore any stale selected launcher, so that I can run the upgraded agent.
5. As an operator, I want a failed or inconclusive command probe reported
   explicitly, so that matching text does not imply a working command.
6. As a Linux operator, I want to know when the Git ignore file first changes,
   so that I can find the writer and verify reapplication.
7. As a compute-host operator, I want optional dependency failures connected
   to client behavior, so that I can tell which workflows are affected.
8. As a maintainer, I want exact-revision native Windows evidence, so that
   source inspection and emulation cannot substitute for a native result.
9. As an automation caller, I want the existing plan and apply modes to stay
   compatible, so that I can adopt the ordered plan on my schedule.
10. As an operator, I want the plan's ordered deployment steps to match the
    actual run, so that I can predict writes and stage dependencies.
11. As a maintainer, I want cold, warm, and targeted timings, so that I can
    prioritize the work that delays a usable command.
12. As an operator, I want a single-agent update to apply its dependencies
    and leave unrelated drift for a full apply, so that repair is fast and
    contained.
13. As an operator, I want a broken or missing managed output repaired even
    with unchanged inputs, so that a warm-path shortcut remains safe.
14. As a Codex user, I want a known interrupted profile write to recover, so
    that I can retry the same operation safely.
15. As a Codex user, I want intervening edits and unknown profile collisions
    preserved, so that retry cannot overwrite files it cannot prove it owns.
16. As a Codex user, I want base configuration, authentication, and
    provider-preserving resume intact, so that profile work does not change
    how existing threads or my subscription work.

## Implementation Decisions

- Keep Bash 3.2 and PowerShell 5.1 bootstrap prerequisites and existing
  installation provider, account-home, and legacy T9K ownership rules. Share
  behavioral scenarios across the adapters. Centralize policy where it
  actually repeats.
- Preserve skipped ledger rows and commit selected records after successful
  reconciliation. The catalog is intended state. The ledger records the
  last successful observation. Live status resolves the command and reports
  its observed path, successful version probe, and provider where provable.
  Handle missing or older ledgers without inventing recorded results.
- A demonstrated optional capability loss is degraded. An operation that
  cannot be exercised is unverified. Required failures, ownership breaches,
  and confirmed required regressions block the relevant gate.
- Retain the existing `actions` field. Add an ordered description of
  selected deployment steps that agrees with dispatch, applies the same
  platform rules, and has no planning side effects.
- Preserve documented `--agents-only` behavior. Narrow the everyday
  `dotfiles-agents update <agent>` after proving its dependency set.
  Preserve unselected agents, skills, shell and settings drift outside that
  set. Reconcile required changed or broken outputs. Explain skips and repair
  in terms of what was checked.
- Use matched baselines before selecting numerical performance targets.
  Compare time to usable command, stage time, downloads, retries and owned
  mutations. Keep a speed change only where savings repeat and repair and
  preservation checks pass. Record a no-change decision if the data does
  not justify an additional shortcut.
- Keep Magpie credential ownership and ADRs 0014 and 0015. Give apply and
  status common ownership and drift reasoning for the generated Codex
  profile only. Retry known interrupted writes within the existing guards.
  Surface unrecognized changes with a recovery result that preserves files.

## Testing Decisions

- Prefer public bootstrap `--plan` and apply, `dotfiles-agents` update and
  status, native workflow results, and Magpie apply, status and Codex resume.
  Check observable preservation and command behavior through the same
  interfaces an operator uses.
- Extend the existing native Windows workflow, Linux owned-file snapshots,
  macOS Homebrew-first scenarios, and Magpie interrupted-write fixtures.
  Rehearse full → narrow, an old ledger, PATH shadowing, stale launchers, and
  failed version probes. Run a supported native Windows scenario before
  claiming parity.
- Compare the Linux Git ignore file across fresh apply, discovery, fixture
  seeding, and reapply. Trace the first divergent writer if needed. Probe the
  affected optional client operation in the existing baseline fixture and
  report unavailable checks with their reason.
- Record source revision, profile, platform, toolchain, command selection,
  cache condition, inputs that affect the result, and scope. Keep fixture,
  container, native, and real-account evidence distinct. Verify cold and
  warm behavior and a deliberate broken-output repair.
- Verify safe Magpie retry, interrupted writes with intervening edits,
  collisions, scoped apply, protected files, and resume with existing
  synthetic fixtures. Authorized native checks establish actual CLI and
  real-device behavior separately.

## Out of Scope

- A unified bootstrap rewrite, automatic deployment daemon, installer order
  changes, blanket package upgrades, and migration of the legacy T9K tree.
- Refactoring Magpie ownership for other clients, changing Codex thread
  metadata, provisioning credentials, or changing gateway routing policy.
- Real-home apply and external publication without their own authorization
  and applicable native and rehearsal gates.

## Further Notes

The architecture decisions and review evidence are in the
[deployment architecture plan](../../docs/DEPLOYMENT_ARCHITECTURE_PLAN.md).
The reviewed baseline was `c06dc29`. Recheck findings against the
implementation base. The integration branch implements all nine tickets
and records their results in the local tracker. The native Windows parity
criterion remains open until the existing workflow runs on the published
integration revision. Portable PowerShell results do not establish native
parity. The measured scope and the post-review comparisons are in the
[deployment timing report](../../docs/verification/deployment-timing.md).
Real account-home verification still requires separate authorization and the
applicable native and rehearsal gates.
