# 10: Resume Codex threads without changing providers

Status: ready-for-agent
Blocked by: None (09 is merged as `011f302`)

**What to build:** one interactive resume entry point across working directories and providers that restores the selected thread's saved provider/model/effort, leaving subscription defaults and session metadata unchanged.

Design facts established from the 0.169.0 primary source and the installed CLI, for the implementer:

- `codex -p/--profile <name>` layers `$CODEX_HOME/<name>.config.toml` over the base user config. A layer that sets none of `model`, `model_provider`, or `model_reasoning_effort` does not count as a selection layer, so the TUI keeps `RestoreFromThread`.
- `load_for_resume` in 0.169.0 injects the thread's saved provider before loading, then validates that the saved provider is present in the effective `model_providers`. A provider definition is therefore required for a Magpie-origin thread; the definition alone is enough, and no selection is needed.
- `codex resume --all` removes the working-directory filter and `--include-non-interactive` adds resumable Exec/AppServer threads. Archived threads are not resumable and are not promised.
- `codex exec resume` always sends resolved settings and is not a mixed-provider substitute.

- [ ] In a fresh synthetic Codex home, create two threads through distinct fake loopback providers and show the current mixed-provider resume failure before fixing it.
- [ ] A neutral provider-definitions-only layer supplies Magpie alongside base-config providers without selecting a model, provider, or effort for resume. Plain new-session Codex and the separate new-session Magpie profile retain their respective defaults.
- [ ] The entry point includes resumable non-interactive threads and all working directories; archived or intrinsically non-resumable threads are documented accurately rather than promised.
- [ ] Actual interactive discovery/resumed turns use each saved endpoint/model/effort; a list/help/exec-resume-only result is not acceptance. Real sessions and paid model calls remain unused.
- [ ] Reject explicit model/provider overrides that would defeat preservation. Protect generated credential-bearing artifacts, existing device collisions, exclusions, and missing prerequisites through the approved public boundaries.
- [ ] Verify against the repository Codex pin and the installed Codex version, both of which are now 0.169.0. The user directed the version directly (use 0.169.0, not 0.166.0), so the catalog pin, the frozen lock, and the registry digests already carry 0.169.0; the two-version runtime comparison is no longer a version gate, but the 0.169.0 mixed-provider resume behavior is still the acceptance evidence. Preserve the results and rerun the matching deployment checks. Any other version change remains a separate decision.
- [ ] Update commands, ownership, backup/rollback, limitations, and automated tests together. Keep the solution small; do not inject provider selections into the base config or retag sessions.
- [ ] Commit the reviewed logical fix with required attribution and report reproducible runtime evidence.

## Decisions (supervisor, 2026-11-19)

- **Entry point**: one managed command (`~/.local/bin/dotfiles-codex-resume`, source `dot_local/bin/executable_dotfiles-codex-resume`) that runs `codex resume --all --include-non-interactive`. It is the documented way to resume; plain `codex` and `codex -p magpie` keep their own new-session defaults.
- **Neutral layer**: provider *definitions* only. It never sets `model`, `model_provider`, or `model_reasoning_effort`, so `resume_model_settings_for_overrides` keeps `RestoreFromThread`. Delivery is by CLI `-c` dotted overrides (they become the `SessionFlags` layer, which `load_for_resume` reloads through `current_cli_overrides()`); a run-time-only `$CODEX_HOME/<name>.config.toml` (0600, atomic, collision-refused, removed on exit) is the documented fallback if runtime proves CLI overrides do not reach the resumed thread's effective config.
- **Credential ownership (resolved)**: the deployment never owns, copies, or persists Magpie's gateway credential. At run time the command derives the provider table from Magpie's own `~/.codex/magpie.config.toml` (Magpie-owned, 0600) and passes the credential to the child through the environment with the provider's `env_key` mechanism. The credential never enters argv, a deployment-owned file, a log, a report, or the repository. A base config that already defines `model_providers.magpie` is left untouched (the device's own definition wins).
- **Override rejection**: `-m/--model`, `--model-provider`, `-c model=…`, `-c model_provider=…`, `-c model_reasoning_effort=…`, and `-p/--profile` are refused with a message that names the preservation guarantee they would defeat.
- **Gateway facts**: Magpie answers loopback requests even without an enabled gateway key (`internal/gateway/lan.go`: only a non-local caller without a key is refused), but the key carries identity, so the credential is still passed when Magpie's profile has one.
- **Scope**: `--all` covers every working directory; `--include-non-interactive` adds resumable Exec/AppServer threads. Archived threads are not resumable and are documented, not promised. `codex exec resume` always sends resolved settings and is not a substitute.

## Supervisor review and runtime evidence (2026-11-19)

Round 1 (Pi, `1aa75c9` base) delivered the command, the tests, ADR 0015, and the
docs. The supervisor reviewed the diff and ran the runtime harness on a host
that grants a pseudo terminal, which the child's sandbox refuses
(`open("/dev/ptmx")` → EPERM). The harness's own pty driver did not drive the
picker, and one of its assertions would have failed; both were sent back as
round-2 findings.

Supervisor measurement, codex-cli 0.169.0, synthetic home, ephemeral loopback
ports, live port 3425 never used:

- The picker lists the synthetic sessions of both providers; `enter` accepts the
  highlighted row and `↑/↓` browse.
- A fresh Codex home shows an "Update now (runs `brew upgrade --cask codex`)"
  prompt when a newer release exists, and its Enter runs the upgrade. Any
  automated key driver must disable the startup update check
  (`check_for_update_on_startup = false`) before it presses a key.
- Text and Return in one write are read as a paste: the Return is swallowed.
  They must be separate writes.
- The resumed turn's request carried the thread's saved model and reasoning
  effort (`gpt-6.1-terra`/`high` for the Magpie thread, `gpt-6.1-sol`/`medium`
  for the other provider's thread) and the `prompt_cache_key` of the thread's
  creation request. One auxiliary request per turn carries the configuration's
  own effort; that call is Codex's own, not the resumed turn.

Round-2 findings sent to the implementer: the pty driver, the picker
assertion (assert on the thread's own request, not the last one), the `-c`
refusal that does not trim the key the way Codex trims it, a linked Codex
input that the command reads instead of refusing, the runtime class joining
the repository's deterministic suite, a Codex version floor, and the
credential's presence in the environment of the resumed agent's shell commands
(documented, not engineered around).

Round 2 landed all of them: 32 deterministic tests (22 unit + 10 opt-in
runtime, 22 running and 10 skipped without the opt-in), the trimmed refusal
verified by the supervisor against the round-1 command (`-c ' model = "…" '`,
`-c '\tmodel_provider\t= "magpie"'`, and `-c ' model_reasoning_effort = "high" '`
all slipped past before), the aliased-input refusal, the Codex 0.169.0 floor,
and the opt-in `DOTFILES_TEST_CODEX_RESUME=1`.

The supervisor's re-run of the opt-in runtime class on its pty-capable host:
31 of 32 passed; `test_the_picker_in_a_pty_resumes_the_thread` failed with
"the resumed turn reached no endpoint". The driver itself worked (`status:
ran`, every step recorded, `update_prompt_seen: false`): the picker resumed
the **alpha** thread, because the picker highlights the most recently updated
session and the alpha thread had just been updated by the app-server scenario,
and the scenario then looked for the request only in the Magpie provider. The
acceptance is a property, not a row: whichever thread the picker resumes, its
own saved provider, model, and effort must be the ones used. Sent back as
round 3.

Round 3 landed the collection rule (every fake provider, the thread found by
its `prompt_cache_key`, the property asserted instead of a row, the browsing
dropped) and five deterministic tests for that rule. On the supervisor's
pty-capable host the picker scenario then failed earlier than before:
"the thread view did not render". The captured screen shows why: the picker
renders in two stages — the header and the footer with "Loading sessions…"
and "0 / 0… · 0%" come first, the rows and the counter "1 / 4" follow. The
driver sent its Return while the list was still loading, so no row was
accepted and the picker stayed on the screen; the title in the wait markers
was already there. Sent back as round 4 with the measured fix (wait until the
list has rows), and with the supervisor's own re-run of the fixed sequence:
"ran", and the resumed turn reached the magpie provider with the
picker-target thread's own model (`gpt-6.1-terra`) and effort (`high`).

Round 4 landed the wait for the loaded session list (a counter with a
non-zero total), five deterministic tests for that rule, and the documented
limitation below. The supervisor's re-run of the opt-in class on its
pty-capable host: **42 tests, OK** — including
`test_the_picker_in_a_pty_resumes_the_thread`, which failed in rounds 2 and
3.

Two contract findings from the supervisor's own review of the command (a fake
Codex records the argv): a user override of `model_providers.magpie.*` is
passed to Codex and then silently overwritten by the command's own
definition (the generated overrides come last and Codex applies them in
order), and the usage text does not match what `--last` does (Codex reads
the first positional after `--last` as the prompt, not as a session id).
Sent back as round 5.

### The model catalog (supervisor, 2026-11-19)

The neutral layer carries provider definitions only. A thread whose model the
active catalog does not know — every Magpie group id — therefore runs with
Codex's fallback model metadata and Codex says so ("Model metadata for
`<id>` not found. Defaulting to fallback metadata"). Measured on the
supervisor's host: the saved provider, the saved model, and the saved
reasoning effort are still used (a thread created with effort `high` sends
effort `high` after the resume), and the catalog can be delivered through the
same CLI channel (`-c model_catalog_json=<absolute path>` removes the
warning). It is not carried: an explicit catalog resolves a model by its
exact slug alone and replaces the active catalog for the whole process, so
carrying it would take the model metadata away from the other threads
resumed in the same run. The fallback is documented as a limitation
(round 4).

## Comments

Codex 0.169.0 primary source chooses saved-thread settings unless an explicit profile/session layer selects model, provider, or reasoning effort. This supports an experiment, not a runtime pass. The separate Magpie new-session profile must remain selecting; use a distinct neutral resume path rather than weakening its validation.

Supervisor checkpoint: ticket 10 is accepted and committed as `6de16eb` on
`fix/macos-codex-preserving-resume` (base `1aa75c9`). The acceptance criteria
are met: the neutral layer carries provider definitions only; the app-server
path and the interactive picker path both resume a thread with its own saved
provider, model, and reasoning effort (49 tests on the supervisor's
pty-capable host, 39 of them without the opt-in); the overrides that would
defeat the preservation are refused, not ignored; the gateway credential
reaches Codex through the environment only; the synthetic run never touches
the real Codex home, the live gateway on 127.0.0.1:3425, or a paid model.
The evidence report is preserved at
`.scratch/deployment-review-2026-11-17/evidence/ticket10-report.md`; it is
local evidence and is not part of the commit. The documented limitation (the
layer carries no model catalog) is recorded in `docs/MAGPIE.md` and ADR 0015.
