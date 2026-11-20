# macOS Magpie deployment completion

Status: ready-for-agent

## Problem Statement

The device owner cannot yet safely apply the reviewed deployment to the Mac. Separate Codex Magpie profile wiring has synthetic coverage, but real pinned-CLI behavior, linked-path preservation, provider-preserving resume, and the existing-device settings rehearsal are incomplete. Earlier native acceptance covers an older source revision. The owner needs these gaps resolved before application, with credible evidence rather than catalog intent or a fake CLI standing in for a live result.

This completion scope supersedes the initial review spec's account-home exclusion only after the approved verification and preservation gates pass. Earlier review tickets and evidence remain historical records.

## Solution

Finish a recoverable, selection-aware separate Magpie profile while keeping plain Codex's subscription configuration and authentication unchanged. Provide one interactive resume entry point that discovers resumable sessions across working directories and providers and restores the chosen thread's saved provider, model, and effort. Rehearse existing-device migration using an approved redacted projection, run acceptance against the final source, then apply to the authorized Mac with protected backup and a drift recheck. Prepare headless Linux verification without claiming an unavailable native Linux result.

## User Stories

1. As the device owner, I want plain Codex to retain my subscription configuration, so that the gateway does not replace my existing access.
2. As the device owner, I want new Magpie sessions to use a separate profile, so that provider experiments remain separate from subscription defaults.
3. As the device owner, I want one resume entry point across working directories and providers, so that I need not remember which profile started a thread.
4. As the device owner, I want resumed threads to retain their saved provider, model, and effort, so that resume does not silently reroute work.
5. As the device owner, I want provider definitions available during resume without a forced provider selection, so that subscription and Magpie threads both remain usable.
6. As the device owner, I want session metadata preserved, so that a gateway integration never retags my conversations.
7. As the device owner, I want compatibility checked against both the repository Codex pin and the installed version, so that a newer local result does not conceal a deployment failure.
8. As the device owner, I want unsupported resume capabilities reported explicitly, so that I do not receive a command that silently resumes the wrong provider.
9. As the device owner, I want unrecorded profile collisions preserved, so that adoption cannot overwrite my own configuration.
10. As the device owner, I want linked parents, symlinks, and hard-linked generated targets refused before mutation, so that deployment cannot change another file through an alias.
11. As the device owner, I want safe interrupted-write retry, so that retry does not adopt edits made after an interruption.
12. As the device owner, I want private profile creation and backups, so that gateway credentials never become public during generation.
13. As the device owner, I want the real pinned CLI checked in isolation, so that fixtures do not conceal incompatible scope selection or profile output.
14. As the device owner, I want a Codex-excluding selection to preserve its files and gateway lists, so that partial deployment respects its boundary.
15. As the device owner, I want a redacted rehearsal against explicitly selected current settings, so that preservation is checked without copying authentication stores or session content.
16. As the device owner, I want source and destination confinement checked before rehearsal writes, so that rehearsal cannot mutate the real home.
17. As the device owner, I want a fresh native macOS result against the final source and seven-agent selection, so that previous-source acceptance is not reused.
18. As the device owner, I want the active client transport preserved, so that a serialization-only change does not interrupt the session supervising deployment.
19. As the device owner, I want protected backups and a final drift check before application, so that the tested device state has not changed underneath the deployment.
20. As the device owner, I want live gateway/provider/group and client checks reported separately from actual inference, so that catalog discovery is not mistaken for routing proof.
21. As the device owner, I want Linux readiness distinguished from native Linux acceptance, so that a Mac run does not claim to validate another operating system.
22. As the device owner, I want DSH, DSH TUI, and Windows deferred, so that unrelated platform failures do not expand this completion task.

## Implementation Decisions

- Reuse the existing integration branch and public bootstrap, Magpie apply/status, settings merge, and native acceptance boundaries. Keep one logical configuration area per fix commit.
- Keep the base Codex configuration and authentication device-owned and hash-guarded. Magpie may write only the selected separate profile and model catalog. Never disconnect ordinary integration or retag threads automatically.
- Validate filesystem ownership/confinement at the write boundary. Reject linked generated targets and linked parents before installer/gateway mutation; retain private creation, collision refusal, backup, exact interrupted-retry fingerprints, and selection exclusion.
- Existing deployment-owned profile drift may be repaired behind a pre-change backup; do not convert that documented behavior into an unrequested immutable-file policy.
- Prove the pinned CLI's actual scope, profile-generation, permissions, and base-file preservation behavior in a fresh synthetic home. Prevent its gateway calls from reaching the real device gateway. The user explicitly authorized this isolated execution after the prior denials.
- Prefer a provider-definitions-only resume profile/entry point if runtime evidence confirms it. It must omit model/provider/effort selection and preserve other device provider definitions through the normal base layer. Reject model/provider overrides that would defeat provider-preserving resume.
- Do not change version pins merely because the device is newer. The user first conditionally authorized a narrow Codex catalog/frozen-lock update from 0.166.0 to 0.169.0 only if the isolated runtime comparison confirmed older-pin mixed-provider resume failure and newer-version success, and then directed the version directly: use Codex 0.169.0, not 0.166.0. The pin, the frozen lock, the registry digests, the tests, and the docs now carry 0.169.0. The runtime comparison still stands as the ticket 10 acceptance evidence, but it no longer gates the version choice. Any other version change still needs an explicit decision.
- Use a reviewed local helper for the approved existing-device rehearsal: allow-list managed setting inputs, redact credential values before producing the projection, exclude authentication stores/sessions/history databases, refuse linked input/output escapes, and report paths/counts/preservation verdicts only. Do not copy arbitrary home trees or add excluded inputs opportunistically.
- A redacted rehearsal proves setting merge and preservation, not account activation or live credentials. Retain the completed Atuin snapshot result; do not recopy its databases.
- After synthetic and existing-device rehearsal acceptance, run the scoped native macOS gate against a stable source revision. Then protect the actual affected configuration/symlinks, recheck drift, perform the already-authorized public bootstrap, and verify live behavior. A real active-transport interruption still requires a separate decision.
- Pi implements approved tickets using implement-spec and TDD, with a persistent ticket worktree based on the integration tip. The supervisor reviews diffs/evidence and merges. OpenCode may replace Pi only on a demonstrated Pi quota limit, not a timeout or unrelated tool/provider failure. Children do not spawn further agents.

## Testing Decisions

The user approved these seams and the four-ticket dependency graph:

- Public Magpie apply/status with disposable homes and a fake CLI for deterministic preservation, collision, retry, drift, selection, and scope-refusal regressions. Follow existing behavior tests; prove a red result before the minimal fix.
- Isolated real Magpie CLI profile operations with fabricated configuration and credentials only; no real gateway access. Prove output completeness using file counts/schema checks and before/after hashes, not exit code alone.
- A synthetic Codex CLI/interactive experiment using two distinct fake loopback provider endpoints, synthetic threads, no real sessions, and no paid inference. Verify discovery plus a resumed turn under each saved provider/model/effort, not just help output or thread listing. Include a forbidden-override case and both supported version targets.
- Public bootstrap/settings rehearsal with a small fabricated device slice first, then the approved redacted real-device projection. Assert preserved unrelated settings, source hashes unchanged, confined regular outputs, and value-free reports.
- Full Magpie synthetic suite, Bash 3.2 syntax, Git whitespace checks, both documented simulated-home profiles, and the scoped native macOS gate on stable final source. Run available shell linters; unavailable tools and required skips are not passes.
- Existing-device backup/drift and live checks follow the deployment gate. Separate model-list discovery, actual inference, and classifier/runtime evidence. Record task-relevant source revision/fingerprint, parameters, environment, counts/checksums, and skipped checks.

## Out of Scope

- DSH, DSH TUI, and native Windows deployment in this completion scope.
- Reading or rewriting real Codex sessions; provider retagging; combining the subscription and Magpie model pickers by editing the base configuration.
- Authentication, login, provider key provisioning, hosted history sync, new graph indexes, uncontrolled home copies, or system/login-shell changes.
- Unapproved pin upgrades, speculative races/refactors, pushing branches, publishing private settings, or bypassing a tool denial.
- Claiming native Linux acceptance without an authorized native Linux runner.

## Further Notes

The initial fixed review baseline remains `6f154d9a73bc61f8d864ad193ee172ebb276bc69`. The integration branch is `fix/deployment-review`; the completion review also compares against the committed profile checkpoint created before ticket implementation. Existing issues 01–08 retain earlier work and evidence. Completion tickets 09–12 carry the new approved dependency graph.

The full synthetic Magpie suite passed 256 tests with no skips before the completion tickets. The approved Magpie ARM64 payload digest is `2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132`. Both execution in isolation and the redacted existing-device rehearsal were explicitly approved in the completion questionnaire. These approvals do not authorize real-home changes before the gates pass.
