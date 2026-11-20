# 12: Verify final macOS source and apply safely

Status: ready-for-agent
Blocked by: 09: Finish isolated Codex profile safety; 10: Resume Codex threads without changing providers; 11: Rehearse existing Mac settings without copying secrets

**What to build:** the final reviewed integration and evidence packet that permits the already-authorized Mac application only after every required preservation/runtime gate passes.

- [ ] Integrate reviewed ticket commits on the existing integration branch, preserve unrelated work, and run standards/spec review against the completion checkpoint plus originating review baseline where relevant.
- [ ] Fix verified review findings through the implementer; rerun affected checks. No unfinished blocker, missing required native behavior suite, or unrun real-CLI check is promoted to a pass.
- [ ] Both documented simulated-home profiles apply successfully; verify required regular files and relevant rendered values. Full Magpie suite, available linters, syntax, and whitespace checks pass.
- [ ] Run a fresh stable-source native macOS aarch64 workstation gate with exactly kimi, pi, opencode, claude, codex, minimax, qoder; record revision/fingerprint, selected agents, runtime, counts, and exclusions. The gate excludes account Magpie wiring and cannot prove inference.
- [ ] The reviewed existing-device redacted rehearsal and prior Atuin compatibility result satisfy their distinct gates; no raw credentials or sessions enter hosted tools.
- [ ] Preserve the active client transport. A genuine required interruption pauses for the separate user decision; serialization-only churn must not restart it.
- [ ] With all gates passed, create protected actual affected-file/symlink backups, recheck device drift, execute the authorized public bootstrap on the account home, and retain the recovery record.
- [ ] Verify live managed versions, configuration/discovery, history compatibility, gateway health, provider/group routes, new-session profiles, and provider-preserving resume as feasible without accessing real conversations. Distinguish catalog/field checks from real inference and classifier runtime proof.
- [ ] Prepare/revalidate the scoped Linux verification command; native Linux acceptance needs an authorized native host. DSH, DSH TUI, Windows, and unavailable runner evidence remain explicitly deferred.
- [ ] Resolve tickets only from completed evidence, preserve/archive task work before worktree cleanup, and do not push.

## Comments

Real-home application was authorized earlier and remains conditional on these gates. The new isolated CLI and redacted rehearsal authorizations do not waive them. Children may prepare/fix verification tooling but do not perform real-home application autonomously.

## Supervisor notes (2026-11-19)

### The deterministic suite: baseline versus ticket 10

Two full runs of `python3 -m unittest discover -s tests -v`, the first against
the integration base `1aa75c9` in the review worktree, the second against the
ticket-10 commit `6de16eb` in its own worktree:

| run | tests | failures | errors | skipped |
| --- | --- | --- | --- | --- |
| baseline `1aa75c9` | 1059 | 30 | 14 | 113 |
| ticket 10 `6de16eb` | 1108 | 29 | 14 | 123 |

The ticket-10 branch adds 49 tests (1108 − 1059) and 10 skips (123 − 113):
the 39 deterministic `test_codex_resume` tests run and the 10 opt-in runtime
tests are skipped without `DOTFILES_TEST_CODEX_RESUME=1`.

The failing set is identical apart from one test: the baseline fails
`test_agent_payload.AgentPayloadTests.test_platform_overlay_replaces_only_the_managed_instruction_block`
with "dotfiles: cannot prepare client config baseline (json):
.pi/agent/models-store.json", and the ticket-10 run does not. The failure is a
transient of the client-settings baseline render, it fails closed (the
deployment refuses to write rather than writing a bad file), and it did not
reproduce in seven re-runs (five sequential, two concurrent) of the same test.
It is recorded here as an unexplained one-off, not as a fixed defect.

Every other failure is host scope on macOS: the Linux-only
`test_deployment`, `test_host_up`, `test_local_history`, `test_legacy_shell`,
`test_legacy_history`, `test_agent_integrations`, `test_bundles`, and
`test_worktrunk` expectations. `AGENTS.md` states that this suite assumes a
Linux x86_64 host and that the macOS gate is the substitute; the native macOS
gate is the check that counts.

### The verified review findings (both axes)

1. **A credential leaf under an `oauth` table survives redaction.**
   `deployment/rehearse_settings.py` decides on the leaf key alone; `oauth` is
   not a credential name and a bare `key` is not one either. The device's
   `~/.kimi-code/config.toml` carries three such leaves
   (`providers.managed:kimi-code.oauth.key`, `services.moonshot_fetch.oauth.key`,
   `services.moonshot_search.oauth.key`) and the rehearsal projected them
   verbatim. Checked against the installed `@moonshot-ai/kimi-code` 2.6.2, the
   client's own schema is `oauth = { storage: "file" | "keyring", key: string }`
   and the token is resolved from the store *through* that reference, so on
   this device the projected value is a storage reference and not a secret. The
   rule gap is still a class defect and is fixed.
2. **The credential-bearing Codex profile is written before it is protected.**
   `deployment/magpie.sh` runs the writer before the `chmod 600`, and the
   writer-failure path returns before the chmod, so a 0644 profile receives the
   bearer credential world-readable and keeps it after a failed write. Fixed.
3. **`source_unchanged` is a read-window verdict, not a run verdict.** The
   report compares the pre-read fingerprint with the fingerprint taken right
   after the read. Fixed: the source is re-hashed at the end of the run.
4. **`README.md` says the deployment never writes the Codex configuration.**
   It writes the separate Magpie-owned profile that `codex -p magpie` uses.
5. **The resume command guesses a TOML.** The hand-written subset parser
   contradicts the repository's own rule ("fails closed on a getter it cannot
   parse rather than guessing"). Decision: require `tomllib`, resolve the
   interpreter the way `magpie_python()` does, refuse otherwise.
6. **Six copies of the codex-profile predicate in `deployment/magpie.sh`.** A
   judgement call, not a defect; extracted where it stays simple.

Findings 1 to 6 went to the implementer as one round on
`fix/macos-review-fixes` (base `807e10a`).

### Round 2: the findings went to the implementer

The brief carried the six findings with the mechanism, the measured device
state, the required behaviour, and the boundaries. The implementer worked in
`~/SHELL/dotfiles.fix-macos-review-fixes` (branch `fix/macos-review-fixes`,
base `807e10a`) and the run ended on the 2400-second timeout with the code
written and the report lost, so the supervisor reviewed the diff itself and
re-ran every check.

What landed, as five commits on `fix/macos-review-fixes`:

| commit | change |
| --- | --- |
| `66122ad` | the rehearsal judges a credential by the name of its table, and judges the source at the end of the run |
| `5a48e49` | the Codex profile is private before the writer runs |
| `7f23eb5` | one helper answers the "is this Codex row skipped" question |
| `8e67336` | the resume command fails closed without a `tomllib` interpreter |
| `fb284f5` | the README names the profile the deployment writes |

`0472305` on `fix/deployment-review` states the two contract changes in
`AGENTS.md`, and `4fea7c4` is the integration merge.

The supervisor's checks on that work:

- `tests.test_existing_settings_rehearsal` — 42 tests, OK.
- `tests.test_magpie` — 288 tests, OK.
- `tests.test_codex_resume` — 50 tests, OK, 10 skipped (the opt-in runtime
  class).
- `/bin/bash -n deployment/magpie.sh` and
  `/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume` — no syntax
  error; `git diff --check` — clean.
- The approved redacted rehearsal against the real device with the final
  helper: 12 files, 564 of 564 records kept, 24 integrity fields carried,
  14 redacted fields (the three new ones are the OAuth leaves), 0 omitted, 0
  unknown, `source_unchanged: true`, and every file's end-of-run fingerprint
  equal to its pre-read fingerprint.

Two of the commits were rewritten once: a hunk-level split of the test file
put the new tests after the module trailer, which left both intermediate
commits broken. The rehearsal change was committed as one logical change
instead, and the committed state was re-tested.

### The gate sequence on the final source (supervisor, 2026-11-19)

Tip: `0472305` on `fix/deployment-review` (the integration merge `4fea7c4` plus
the contract change in `AGENTS.md`).

| step | result |
| --- | --- |
| 1. review, both axes | six findings, all verified by the supervisor and fixed through the implementer |
| 2. deterministic suite | 1123 tests, 29 failures + 14 errors, 123 skipped — the failure set is identical to the ticket-10 run and carries no new failure against the baseline |
| 3. simulated homes | `t9k` applied `linux-remote-compute`, `linux` applied `linux-workstation`; `~/.local/bin/dotfiles-codex-resume` is a regular file at 0755 in both; the nushell config bootstraps standalone (`print "ok"`) |
| 4. native macOS gate | **passed**, aarch64 workstation, exactly kimi, pi, opencode, claude, codex, minimax, qoder; source fingerprint `7dc03e53…`; eight check phases; 546 s |
| 5. device rehearsal | helper 6, 12 files, 564/564 records, 24 integrity fields, 14 redacted, 0 omitted, 0 unknown, `source_unchanged: true` |
| 6. headless Linux | prepared and refused cleanly: "Linux x86_64 execution is required" — not a pass, an authorized native Linux host is still needed |

The one difference against the baseline run is
`test_agent_payload.AgentPayloadTests.test_platform_overlay_replaces_only_the_managed_instruction_block`,
which failed once in the baseline run with a client-settings baseline render
error, passed in the ticket-10 run and in this run, and did not reproduce in
seven re-runs (five sequential, two concurrent). It fails closed when it
happens.

### The protected application (step 7) is ready and waiting on one word

The affected set is computed from the device: 104 managed, client-settings,
and agent-instruction paths, of which **77 existing regular files** are backed
up with their mode, size, and SHA-256 in
`/private/tmp/dotfiles-protected-backups/20261118T212324Z/manifest.tsv`
(13 at 0600, 47 at 0644, 17 at 0755; the copies are mode 0600 inside a 0700
directory), and 27 do not exist yet.

The plan for the account home is the authorized shape: `proxy: false`,
`magpie: true`, `systemChanges: false`, `loginShellChanges: false`, copy
mode, and exactly the seven selected agents.

The harness refuses to let the supervisor run the apply to `$HOME` without the
authorization visible in the session, so the operator runs it:

```bash
! bash bootstrap.sh --source /Users/joey/SHELL/dotfiles --home /Users/joey \
    --agents kimi,pi,opencode,claude,codex,minimax,qoder
```

The pre-apply inventory is already recorded: codex 0.169.0 (the pin),
python 3.15.2, chezmoi 2.73.3, nu 0.117.0, node 26.13.1, bun 1.4.4,
pixi 0.84.2, git 2.56.1 — every one at or newer than its repository pin —
and every selected agent command present. The Magpie gateway answers on
127.0.0.1:3425 as 0.1.4451, and the device credential store
`~/.config/dotfiles/magpie.env` is absent, which is harmless here because
Magpie already owns the providers it needs.

### Cleanup (step 9), done before the apply

All five task worktrees were merged into `fix/deployment-review`, tagged, and
removed without `--force`:

| worktree | tip | archive tag |
| --- | --- | --- |
| `dotfiles.fix-macos-codex-profile-safety` | `95279de` | `archive/macos-codex-profile-safety` |
| `dotfiles.fix-macos-settings-rehearsal` | `339f426` | `archive/macos-settings-rehearsal` |
| `dotfiles.fix-macos-codex-preserving-resume` | `6de16eb` | `archive/macos-codex-preserving-resume` |
| `dotfiles.fix-macos-application-gates` | `807e10a` | `archive/macos-application-gates` |
| `dotfiles.fix-macos-review-fixes` | `fb284f5` | `archive/macos-review-fixes` |

Every untracked file those worktrees carried was copied into
`evidence/` first and compared file by file; the copies are byte-identical.
The branches were deleted only after the tags were verified to resolve.

The repository keeps the untracked tracker `.scratch/deployment-review-2026-11-17/`
with the evidence and these notes. Nothing is pushed.
