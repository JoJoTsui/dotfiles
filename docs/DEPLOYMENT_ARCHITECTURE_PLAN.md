# Deployment architecture plan

## Status at `598478f`

The architecture review began at `c06dc29`. Its two central dispatch findings
are resolved in the current tree:

- Native Windows preserves unselected agent-ledger rows during a narrow apply,
  matching the Unix behavior (`deployment/windows.ps1`;
  `tests/test_windows_deployment.py`).
- The deployment proxy runs before Magpie and shell preparation, matching the
  ordered plan (`bootstrap.sh`; `tests/test_deployment.py`).

The remaining decisions below describe the accepted architecture and its
verification boundary. Historical problem statements and review evidence stay
in `.scratch/deployment-review-2026-11-17/`; they are not current deployment
instructions.

## Decisions

1. A targeted agent update reconciles the selected coding agent and its
   verified dependencies. Leave unrelated drift for a full apply.
2. A demonstrated optional capability loss produces a degraded result. An
   operation that could not be exercised is unverified. Required behavior,
   ownership violations, and verified regressions in supported scenarios
   retain their blocking role.
3. The first Magpie refactor covers only the generated Codex profile. It
   preserves credential ownership, the base Codex configuration and
   authentication, and provider-preserving resume.
4. Keep the existing `--agents-only` apply behavior. Narrow the everyday
   `dotfiles-agents update <agent>` path after verifying the dependencies.
5. Keep the plan's existing `actions` field and add an ordered list of
   deployment steps that agrees with execution.
6. Require native CI evidence for Windows parity. Baseline deployment time
   before choosing numerical targets. Require repeatable savings and proof
   that a broken managed output still gets repaired for every speed change.
7. Recovery may resume only when the existing ownership and fingerprint
   checks establish that the interrupted write can continue. Stop and report
   unexplained drift while preserving the current files.

## Delivery order

### Establish trustworthy state and evidence

Preserve unselected ledger entries on both native adapters. Make agent status
show declared intent, the last recorded apply, and the resolved live command
with distinct evidence. Verify successful command execution and provider
provenance where supported. Exercise existing-device workflows through the
public commands, including a Homebrew upgrade, a PATH shadow, and a native
Windows full-to-narrow apply.

Use the existing Linux gate to capture the earliest divergent fingerprint of
the Git ignore file. Trace the writer on a clean reproduction when stage
observations are insufficient. Exercise the affected optional operation in
the Ubuntu 20.04 fixture and report its capability result. Keep a failed,
skipped, or unrun check visible and tied to its environment.

### Explain the plan and shorten the update

Use the existing Bash and PowerShell adapters and their bootstrap
prerequisites. Make the ordered plan and execution agree on selected work.
Measure cold setup, warm reapply, and single-agent updates on equivalent
macOS and Linux fixtures. Record time to a verified command, stage times,
downloads, retries, and owned mutations. Use the measurements to pick work
to eliminate. Recheck missing outputs, drift, and effective input changes
before skipping work.

### Make generated Codex profile recovery local

Give the existing Magpie apply and status paths one place to reason about
the generated profile's ownership, pending write evidence, and observed
drift. Verify safe retry and preservation after a collision or an intervening
edit. Keep synthetic results and authorized native device observations
distinct. [Magpie ownership](adr/0014-magpie-owns-the-model-gateway.md) ·
[Provider-preserving resume](adr/0015-neutral-codex-resume-layer.md)

## Operating model

OpenGitOps informs the distinction between declared, recorded, and observed
state. SRE rollout practice informs promotion from disposable environments to
representative native systems. Forward-deployed engineering informs the
choice of workflows, including the Mac after a package upgrade, Linux
remote compute, and an existing Windows workstation. Matt Pocock's depth
and locality criteria favor shared behavior checks at the existing public
interfaces. Andrej Karpathy's partial autonomy and Lauren Tan's executable
verification inform what agents can prove before presenting an operator
decision. [OpenGitOps](https://opengitops.dev/blog/1.0-announcement/) ·
[Google SRE](https://sre.google/workbook/canarying-releases/) ·
[Apollo field workflows](https://investors.palantir.com/files/Apollo%20Demo%20Day%20-%20Transcript%20EN.pdf) ·
[Architecture skill](https://github.com/mattpocock/skills/blob/main/docs/engineering/improve-codebase-architecture.md) ·
[Software Is Changing (Again)](https://www.youtube.com/watch?v=LCEmiRjPEtQ&t=1102s) ·
[pstack](https://github.com/cursor/plugins/tree/main/pstack)

The [local spec](../.scratch/deployment-architecture/spec.md) and
[implementation tickets](../.scratch/deployment-architecture/issues/) carry
the acceptance criteria and dependencies.
