# Deployment review at e8de927

Baseline: `git diff 6f154d9a73bc61f8d864ad193ee172ebb276bc69...e8de927`. Findings describe the reviewed revision and must be rechecked after remediation.

## Standards

1. Unix generated skill copying overwrites an unrecorded device directory's `SKILL.md`, contrary to the copy-root ownership rule. Reproduced in a disposable home. Ticket 01.
2. Windows records generated skill ownership after preserving a different unrecorded device directory; a subsequent apply can delete it as owned. Source-traced; native PowerShell unavailable. Ticket 01.
3. Windows remote skill fetching treats the reviewed lock as optional, contrary to the required lock boundary. Source-traced; native PowerShell unavailable. Ticket 02.
4. Windows skill preflight traverses individual destination entries and rejects collisions before the copy adapter can preserve and report them. Source-traced; native PowerShell unavailable. Ticket 03.

## Spec

1. macOS client templates wire Claude and Pi to Magpie before the `--no-magpie` switch or gateway readiness is checked; reproduced with a disposable macOS-shaped apply. Ticket 04.
2. Unix generated skill copying overwrites unrecorded device content; reproduced in a disposable home. Ticket 01.
3. Client settings are merged before Magpie's migration backup and gateway checks, so the backup can contain already-migrated settings and failure can leave changed client settings. Source-traced. Ticket 04.
4. Gateway status prints desired wiring without inspecting client files, and apply trusts recorded wiring even when managed client state has drifted. Source-traced. Ticket 05.

## Verification limits

GitHub jobs at the reviewed revision did not start due to an account billing lock. The local system is macOS arm64, without PowerShell or a running Linux container runtime. See ticket 06 for the recorded test outcomes and outstanding native acceptance.
