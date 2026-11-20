# 11: Rehearse existing Mac settings without copying secrets

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** a reviewed local rehearsal helper that proves managed-setting migration/preservation against a private, redacted, explicitly allow-listed projection of the existing Mac, with the live source left unchanged.

- [ ] Start with fabricated device settings and public bootstrap/settings-merge tests; demonstrate the missing rehearsal/preservation failure before implementing the helper.
- [ ] Review a small input manifest before real-device execution. Exclude auth stores, session files, history databases, credential values, arbitrary trees, and unneeded files.
- [ ] Redact before producing projected artifacts; keep projected files private and reports value-free. Unknown credential-shaped settings fail closed or are safely omitted with a count, never copied as a convenience.
- [ ] Confinement checks reject linked input/output escapes and prevent real-home writes. Rehearse conflicting launcher/skill symlinks only in a fabricated isolated fixture; retain ordinary bootstrap symlink guards.
- [ ] Include unrelated providers/trust/instructions/skills, shell integrations, terminal preferences, and endpoint/transport preservation in the appropriate allow-listed fabricated/redacted slice.
- [ ] Hash source inputs before/after and prove output completeness with expected file/record counts or checksums. Record environment/source fingerprint without credential values.
- [ ] The supervisor reviews the helper and synthetic evidence before using the user-authorized real-device redacted projection. Do not perform the real-device rehearsal from a child agent without that handoff.
- [ ] Retain the completed Atuin result; no database recopy, auth login, sync, or live gateway probe is part of this rehearsal.
- [ ] Update operator documentation and commit the reviewed helper/tests together with attribution. A redacted rehearsal is not credential or inference acceptance.

## Comments

The user explicitly authorized the redacted allow-listed real-device projection after reviewing the proposed boundary. Any expansion of inputs beyond that boundary needs a new decision. Before/after source checks and redaction can run locally, but no raw device configuration content may be sent to a hosted implementer.

Supervisor checkpoint: persistent Pi implementation worktree `/Users/joey/SHELL/dotfiles.fix-macos-settings-rehearsal` on `fix/macos-settings-rehearsal`, based on committed profile checkpoint `37dc127`. Initial attempts stopped before edits when Pi startup requested real-home trust/settings/auth lock directories. Rather than permitting those writes, the current attempt uses task-owned Pi runtime state. The user explicitly approved the supported `--no-approve` flag, which distrusts project-local resource discovery; the native write/network sandbox remains in place. Only fabricated device inputs are authorized for the implementer; the supervisor will review the helper before the real redacted rehearsal.

First implementation returned without a real-device run. Supervisor review rejected it pending fixes: three fabricated TOML cases (multiline credential, credential in an inline table, credential comment) returned success with the marker retained, and a pre-existing hard-linked report overwrote its source-home alias. Independent focused tests under ordinary macOS TMPDIR had 14 failures of 17 because their fixture paths used the `/var` symlink alias. Pi's 17-test result used custom canonical scratch and did not establish ordinary fixture portability. The first report's deliberate mutation checks are not evidence of chronological red-before-green TDD. Pi is implementing public-seam regressions/fixes in the same worktree; no ticket commit, merge, or real-device projection is accepted yet.
