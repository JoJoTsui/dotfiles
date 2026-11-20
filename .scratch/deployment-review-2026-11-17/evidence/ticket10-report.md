# Ticket 10 — Codex resume without switching a thread's provider

Workspace: `/Users/joey/SHELL/dotfiles.fix-macos-codex-preserving-resume`
Branch: `fix/macos-codex-preserving-resume` (base: integration tip `1aa75c9`,
"Codex pin 0.169.0"; the tip did not move during this work).
Codex under test: `codex-cli 0.169.0` (`/Users/joey/.local/bin/codex`), the
installed runtime and the repository pin.

## What changed

| File | Change |
| --- | --- |
| `dot_local/bin/executable_dotfiles-codex-resume` | new managed command (`~/.local/bin/dotfiles-codex-resume`) |
| `tests/test_codex_resume.py` | new behavioral and runtime regressions |
| `tests/codex_resume_runtime.py` | new runtime harness (fake providers, app-server driver, pty driver) |
| `docs/adr/0015-neutral-codex-resume-layer.md` | new ADR for the neutral resume layer |
| `docs/MAGPIE.md` | the resume section now documents the command, the refusals, and the verification boundary |
| `AGENTS.md`, `README.md`, `GLOSSARY.md` | the command, the ownership rule, and the new glossary term |

Nothing under `deployment/` changed: the apply owns no part of this feature,
the base Codex configuration and authentication stay device-owned, and no
session is retagged.

## The command

`dotfiles-codex-resume [SESSION_ID] [PROMPT] [--last] [--cd DIR]
[--no-alt-screen]`

- Runs `codex resume --all --include-non-interactive`, so the picker covers
  every working directory and the resumable Exec/AppServer threads.
- Adds a **provider-definitions-only** layer, delivered as CLI `-c` dotted
  overrides. It never sets `model`, `model_provider`, or
  `model_reasoning_effort`.
- The definitions come from Magpie's own `~/.codex/magpie.config.toml` at run
  time. A base `config.toml` that already defines `model_providers.magpie`
  wins and is left alone. Without a Magpie profile the command degrades to a
  plain resume and says so on stderr.
- The gateway credential is never owned, copied, or persisted here. It is read
  from the profile at run time and handed to the child through the environment
  with the provider's `env_key` mechanism, so it never enters argv, a
  deployment-owned file, a log, a report, or the repository. A header whose
  name looks like a credential moves to `env_http_headers` for the same
  reason; the actor header stays in `http_headers` because Codex reads it
  there to offer the OpenAI actor tools.
- `--model`, `--model-provider`, `-c model=…`, `-c model_provider=…`,
  `-c model_reasoning_effort=…`, and `--profile` are refused with a message
  that names the guarantee they would defeat. They are not ignored.

## Red and green (TDD)

The seam is the command's public interface: the argv and the environment it
hands to `codex`. A fake `codex` records both, so the tests assert what the
next process sees, not how the wrapper is written.

```
$ python3 -m unittest tests.test_codex_resume -v
```

| Cycle | Red | Green |
| --- | --- | --- |
| 1 | 14 tests written first: `Ran 14 tests … FAILED (failures=1, errors=13)` — the command did not exist | command implemented: `Ran 14 tests … OK` |
| 2 | `line 143: user_overrides[@]: unbound variable` (bash 3.2 + `set -u` on an empty array) | `${array[@]+"${array[@]}"}` idiom: `Ran 14 tests … OK` |
| 3 | `this python3 has no TOML reader` (the deployment's `python3` may predate `tomllib`) | a small TOML reader as the fallback: `Ran 14 tests … OK` |
| 4 | `KeyError: 'DOTFILES_CODEX_RESUME_MAGPIE_TOKEN'` (the environment held a name and a value in two slots) | one `NAME=VALUE` slot: `Ran 14 tests … OK` |
| 5 | the credential header and an unusable provider table had no rule | both degrade or move to the environment: `Ran 27 tests … OK (skipped=1)` |

Final state of the targeted suite:

```
$ python3 -m unittest tests.test_codex_resume -v
Ran 27 tests in 11.2s
OK (skipped=1)
```

The one skip is the picker in a pseudo terminal, which this sandbox refuses
to allocate (see the blocker below).

## Runtime evidence

Everything ran in a synthetic home under the ticket's TMPDIR
(`$TMPDIR/t10` and a fresh `TemporaryDirectory` per run). The real
`~/.codex`, its sessions, its history, its authentication, and the real
`~/.codex/magpie.config.toml` were never read or written. No credential was
printed: every fixture uses a placeholder, and the fake endpoints record only
the model, the reasoning effort, and whether a bearer was present.

The fake endpoints bind **ephemeral loopback ports** (59995/59996/59997 in
one run, 64203 in another), never 3425; the harness asserts that no fake port
is the live gateway port, and the report records the excluded port. The live
gateway was therefore never contacted.

The wire format mirrors the public upstream helpers
(`app-server-test-client/src/loopback_responses_server.rs` and
`core/tests/common/responses.rs`): `POST <base>/responses` answered with
`text/event-stream` and the `response.created` / `response.output_item.done`
/ `response.completed` events.

### Commands

```
codex exec --skip-git-repo-check -c model_provider=alpha -c model=gpt-6.1-sol \
    -c model_reasoning_effort=medium 'alpha thread'
codex exec --skip-git-repo-check -p magpie -c model_reasoning_effort=high \
    'magpie thread'
codex resume -p magpie <alpha thread>          # red: another provider's thread
codex resume <magpie thread>                   # red: without the provider definition
dotfiles-codex-resume <magpie thread>          # green
dotfiles-codex-resume <alpha thread>           # green
```

The two synthetic threads were created with different saved providers, models,
and reasoning efforts: `alpha` / `gpt-6.1-sol` / `medium` and `magpie` /
`gpt-6.1-terra` / `high`.

### Red results (observed first)

| Case | Observed |
| --- | --- |
| the Magpie profile against the `alpha` thread | ``failed to load configuration: Cannot change this thread's model provider from `alpha` to `magpie` on resume.`` |
| the `magpie` thread without the provider definition | `This chat uses model provider "magpie", which is no longer configured. Restore this provider's configuration to continue.` (`modelProviderNotConfigured`) |

### Green results

The managed command handed Codex exactly this layer (recorded argv, no
secret):

```
resume --all --include-non-interactive
  -c model_providers.magpie.name="magpie"
  -c model_providers.magpie.base_url="http://127.0.0.1:<port>/v1"
  -c model_providers.magpie.wire_api="responses"
  -c model_providers.magpie.http_headers.x-openai-actor-authorization="magpie"
  -c model_providers.magpie.env_key="DOTFILES_CODEX_RESUME_MAGPIE_TOKEN"
```

No `model=`, no `model_provider=`, no `model_reasoning_effort=`.

| Resumed thread | Endpoint that received the turn | model | reasoning effort | bearer | actor header |
| --- | --- | --- | --- | --- | --- |
| `magpie` thread | magpie fake endpoint | `gpt-6.1-terra` | `high` | present | `magpie` |
| `alpha` thread | alpha fake endpoint | `gpt-6.1-sol` | `medium` | present | absent |

The app-server's own resume answer agreed: `modelProvider: magpie`,
`model: gpt-6.1-terra`, `reasoningEffort: high` for the first thread and
`alpha` / `gpt-6.1-sol` / `medium` for the second.

### The defaults of a new session are untouched

| New session | Endpoint | model | effort |
| --- | --- | --- | --- |
| plain `codex` (base configuration) | alpha fake endpoint | `gpt-6.1-sol` | `medium` |
| `codex -p magpie` (the Magpie profile) | magpie fake endpoint | `gpt-6.1-terra` | `high` (the CLI override of the creation run) |
| `codex -p magpie` without any override | magpie fake endpoint | `gpt-6.1-terra` | `medium` (the model's own default) |

The last row is the plain profile session: it used the profile's own model and
the model's default effort, so the resume command changed neither layer.

The base `config.toml` was byte-identical before and after every run, and the
device's other provider definition (`[model_providers.other]`) was still
present: the injected layer merges into `model_providers` instead of replacing
it.

## Blocker: the picker in a pseudo terminal

The acceptance asks for the interactive picker to be driven in a pty. This
sandbox does not hand out pseudo terminals:

```
$ python3 -c "import pty; pty.openpty()"
OSError: out of pty devices
$ python3 -c "import os; os.open('/dev/ptmx', os.O_RDWR)"
OSError: [Errno 1] Operation not permitted
```

`script` and `expect` fail the same way, and `/dev/tty` reports
"Device not configured" because the session has no controlling terminal.

What was done instead, and what it does and does not prove:

- The harness keeps the pty driver (`drive_picker` in
  `tests/codex_resume_runtime.py`): it spawns the managed command in a pty,
  presses Enter in the picker, types a prompt, and asserts on what the fake
  endpoint received. It runs wherever the host allows a pty; here it records
  `status: blocked` with the exact error, and the test skips with that
  reason.
- The resume was therefore driven through the app-server JSON-RPC protocol
  that the picker itself drives (`thread/resume` without a model or provider,
  which is what the TUI sends under `RestoreFromThread`, then `turn/start`).
  The provider layer under test was still the layer the managed command
  built: the harness records the command's argv and starts the app-server
  with those same `-c` overrides.
- The red cases were driven the same way, with the request the TUI sends
  under `OverrideFromCurrentConfig` (`modelProvider`/`model`).

So the provider, model, and reasoning effort of the resumed turn are proven
against the real 0.169.0 binary, but **the picker's own key handling is not
proven in this sandbox**. It has to be run on a host that grants a pty before
the picker path itself can be claimed.

## Checks

| Check | Result |
| --- | --- |
| `python3 -m unittest tests.test_codex_resume -v` | 27 tests, OK, 1 skip (the pty picker) |
| `DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest tests.test_magpie -v` | `Ran 284 tests in 507.523s` — OK |
| `python3 -m unittest tests.test_deployment tests.test_agent_herdr tests.test_host_up` | 16 failures + 1 loader error — **pre-existing**: the same result at the base commit `1aa75c9` (the Herdr/Codex daemon and the Linux-assuming deployment suite on a macOS host) |
| `/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume` | clean |
| `git diff --check` | clean |
| simulated-home apply, `--class t9k` | the command landed as `~/.local/bin/dotfiles-codex-resume`, mode 0755; the run then failed at `apply-source.skills` because the sandbox has no network (`cannot fetch skill academic-paper from https://github.com/…`) — unrelated to this change |
| simulated-home apply, `--class linux` | same: 0755, then the same network-bound skill fetch |
| ShellCheck, shfmt | **skipped**: not installed, and installing them is out of scope |

No download, build, install, push, reset, stash, or permission change was
made. Nothing outside this worktree and the ticket's TMPDIR was written.

## Limitations

- Archived threads are not resumable; the command does not offer them.
- `codex exec resume` always sends resolved settings and is not a substitute.
- The neutral layer does not carry Magpie's model catalog
  (`model_catalog_json`): a catalog applies to the whole session, and a Magpie
  catalog would change the model metadata of a thread of another provider. The
  models in the run (`gpt-6.1-sol`, `gpt-6.1-terra`) are in Codex's embedded
  catalog; a model outside it falls back to Codex's fallback model metadata
  (0.169.0 source), which this run did not exercise.
- The command refuses `--profile`, so a device that wants a profile *and* a
  resume has to use the plain Codex command for the profile case.
- The layer carries a fixed set of provider keys; a provider option the
  command does not know is not carried.

## Remaining risks

- The picker path is unproven in this sandbox (see the blocker).
- The behaviour depends on Codex 0.169.0's selection rule
  (`resume_model_settings_for_overrides`) and on `load_for_resume`. A newer
  Codex has to be checked again; the repository pin and the installed runtime
  are both 0.169.0 today.
- The layer merges into `model_providers`. A device that defines
  `model_providers.magpie` in the base configuration keeps its own definition,
  and the command then injects nothing — a Magpie thread then needs that
  device definition to be correct.
- The Magpie profile is read at run time. A profile that changes shape (a new
  credential mechanism, a credential in a query parameter) degrades the
  command to a plain resume with a message, by design.

## Proposed commit message

```
[agents]: resume Codex threads without switching their provider

Add the managed dotfiles-codex-resume command: it runs codex resume
--all --include-non-interactive and adds a provider-definitions-only layer
derived at run time from Magpie's own profile. The layer never selects a
model, a provider, or a reasoning effort, so a resumed thread keeps its own
saved provider, model, and reasoning effort. The gateway credential reaches
Codex through the environment with the provider's env_key mechanism and never
enters argv, a file, a log, or this repository. A device's own
model_providers.magpie definition wins, a missing profile degrades to a plain
resume, and an explicit model, provider, effort, or profile is refused with
the guarantee it would defeat.

Add the ADR for the neutral resume layer, the MAGPIE section for the
command, and the behavioral and runtime regressions: two fake loopback
providers, two synthetic threads with different saved settings, the two
resume failures the run has to avoid, and the resumed turns that reach each
thread's own endpoint with its saved model and effort.
```

The supervisor commits; this worktree is left uncommitted.

---

# Round 2 — the five findings of the supervisor review

Workspace and branch are unchanged: `/Users/joey/SHELL/dotfiles.fix-macos-codex-preserving-resume`,
branch `fix/macos-codex-preserving-resume`, base/integration tip `1aa75c9`.
Nothing was committed; the supervisor commits.

The supervisor's host handed out pseudo terminals, so the interactive facts
below are the supervisor's measurements (Codex 0.169.0, synthetic home,
ephemeral loopback ports, live port 3425 never used). This sandbox still
refuses a pty, so the interactive check is reported as **blocked**, never as a
pass.

## What changed in round 2

| File | Change |
| --- | --- |
| `dot_local/bin/executable_dotfiles-codex-resume` | the three refusals the findings asked for: a trimmed `-c` key, a refused aliased input, a Codex version floor |
| `tests/codex_resume_runtime.py` | the pty driver of the measured sequence, the update-check guard, the cache key and input size in the fake provider, the auxiliary request kept apart |
| `tests/test_codex_resume.py` | the regressions for the trimmed key, the aliased inputs, and the version floor; the runtime class is opt-in |
| `docs/MAGPIE.md`, `docs/adr/0015-neutral-codex-resume-layer.md`, `AGENTS.md` | the picker path, the auxiliary request, the version floor, the opt-in command, and the environment limitation |

## 1. The pty driver drives the picker

**Red (round 1).** The driver sent `\r` on a fixed four second delay, without
waiting for the picker to render, and sent the prompt and the Return in one
write (`b"picker turn\r"`). The supervisor measured that text and Return in
one write are read as a paste: the Return is swallowed and the text lands in
the composer without submitting. The first Return could also land in the
startup update prompt of a fresh Codex home, whose Enter runs
`brew upgrade --cask codex`.

**Green (round 2).** `drive_picker` in `tests/codex_resume_runtime.py` now:

1. waits for the picker to render (its own footer: `enter resume`, `browse`),
   with the screen read without the terminal's control sequences;
2. sends `↑` and then `↓`, each in a write of its own with a pause between
   them;
3. sends `\r` in a write of its own, which accepts the highlighted row;
4. waits for the thread view (the composer);
5. sends the prompt text in a write of its own, waits, and only then sends
   `\r` in a write of its own.

The update prompt can never be accepted: the synthetic `config.toml` sets
`check_for_update_on_startup = false` (the key exists in Codex 0.169.0), the
driver sends no key at all before the picker has rendered, and a screen that
shows `Update available`, `Update now`, or `brew upgrade` aborts the run
before any further key is written. The synthetic home also trusts its working
directory, so the interactive path does not stop on the trust dialog.

The picker scenario creates one thread of its own, right before the run, so
that the picker lists four synthetic sessions (the three of the other
scenarios plus its own target). Which row the picker highlights is the
picker's own business: the assertion looks the request of the thread that was
actually resumed up, by its cache key.

**Check.** Blocked here: this sandbox allocates no pseudo terminal
(`opening a pseudo terminal failed: out of pty devices`). The runtime class
records `status: blocked` with that error and skips with that reason. The
supervisor's pty-capable host runs the same driver.

## 2. The picker assertion names the request of the resumed thread

**Red (round 1).** The assertion used the last received request. The
supervisor measured that a turn produces an additional request of Codex's own
(the thread title request) that carries the configuration's own effort, so the
last request is not the resumed turn. Reproduced against the round-2 report
data with the auxiliary request added:

```
round-1 rule  -> model=gpt-6.1-terra effort=medium   assertion effort == high: False
round-2 rule  -> model=gpt-6.1-terra effort=high     assertion effort == high: True
```

**Green (round 2).** The fake provider now records `prompt_cache_key`,
`input_items`, `input_chars`, and the tail of the user text of every request.
The harness keeps the cache key of each thread's creation request, and the
assertion picks the request whose `prompt_cache_key` matches it — the request
that belongs to the resumed thread. The auxiliary request is recorded under
`auxiliary` and is **not** asserted on: it is Codex's own call, it belongs to
a temporary thread of its own, and it carries the configuration's effort
rather than the thread's.

## 3. The refused `-c` key is trimmed the way Codex trims it

**Red.** `test_a_spaced_config_override_is_refused` against the round-1
command: 3 failures, `returncode 0 == 0` — `-c ' model = "gpt-6.1-sol"'`,
`-c '\tmodel_provider\t= "magpie"'`, and `-c ' model_reasoning_effort = "high" '`
all slipped past the refusal.

**Green.** The refusal trims the key before it compares it, exactly as Codex
trims it (`k.trim()` in `utils/cli/src/config_override.rs`, `parse_overrides`),
and compares the trimmed key against `model`, `model_provider`, and
`model_reasoning_effort`.

## 4. An aliased input is refused, not read through

**Red.** `test_a_linked_magpie_profile_is_refused` and
`test_a_linked_base_configuration_is_refused` against the round-1 command:
2 failures, the provider table of the linked profile reached `codex`.

**Green.** The command refuses the two files it reads the way the
deployment's Codex boundary refuses an aliased path (`deployment/magpie.sh`,
`magpie_codex_profile_preflight`): a symlink, a path that is not a regular
file, and a file with another name (a link count above one) are never read
through the link. The same rule applies to a linked Codex home. The command
degrades to a plain resume with a message on stderr instead of reading
through the link.

## 5. The runtime class is opt-in

**Red.** The round-1 class ran whenever `codex` was on the `PATH`, and
`tests/verify_portable.py` runs `python3 -m unittest discover -s tests -v`:
a portable verification would have started the real Codex CLI and a pty.

**Green.** The class is gated behind the repository's own pattern,
`DOTFILES_TEST_CODEX_RESUME=1`. The fake-Codex unit tests (22) always run;
the runtime class (10 tests) skips without the opt-in.

```
$ python3 -m unittest discover -s tests -p "test_codex_resume.py" -v
Ran 32 tests in 5.526s
OK (skipped=10)

$ DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
Ran 32 tests in 16.743s
OK (skipped=1)
```

The exact command that runs the runtime class:

```bash
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
```

## 6. The Codex version floor

**Red.** `test_an_old_codex_is_refused` against the round-1 command: a
failure — an old Codex was accepted.

**Green.** The command reads `codex --version` and refuses anything below
`0.169.0` with a message that names both versions, and refuses a version it
cannot read. The reason is the selection rule of that release: below 0.169.0
the app server required the saved provider of a thread to equal the provider
of the current configuration, so a neutral layer alone was not enough
(`/Users/joey/SHELL/dotfiles/.scratch/deployment-review-2026-11-17/codex-resume-compatibility.md`).
Nothing is claimed about a newer Codex beyond what the docs already state: it
needs its own check.

## 7. The credential in the environment of the resumed agent

The credential reaches Codex through the environment, so the shell commands
the resumed agent runs inherit it, the same way the other `env_key` providers
of this device already do. The command does **not** override
`shell_environment_policy`: a merge would replace the device's own list
instead of extending it. This is recorded as a documented limitation in
`docs/MAGPIE.md` and in the ADR, not as a code change.

## Commands (value free)

```bash
python3 -m unittest tests.test_codex_resume -v
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
python3 -m unittest discover -s tests -p "test_codex_resume.py" -v
python3 tests/codex_resume_runtime.py          # the report of the run
/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume
git diff --check
```

Every fixture uses a placeholder credential. The fake endpoints record the
model, the reasoning effort, the cache key, the input size, and whether a
bearer was present; never a credential value. The fake providers bind
ephemeral loopback ports, never 3425.

## Red and green, per finding

| Finding | Red | Green |
| --- | --- | --- |
| 1 pty driver | round-1 driver: a fixed-delay `\r`, text and Return in one write (a paste), no wait for the picker | the measured sequence, the update check off in the synthetic home, the update prompt aborts the run; **pty blocked in this sandbox** |
| 2 picker assertion | round-1 rule picks the last request → effort `medium` ≠ `high` | the request whose cache key matches the thread's creation request → effort `high`; the auxiliary request is recorded apart |
| 3 trimmed key | 3 failures: the spaced `-c` forms were accepted | the key is trimmed like Codex trims it; 3 forms refused |
| 4 aliased input | 2 failures: the linked profile was read through the link | a symlink, a non-regular file, and a file with another name are refused and degrade with a message |
| 5 opt-in | the class ran inside the deterministic discovery | `DOTFILES_TEST_CODEX_RESUME=1` gates it; 10 skips without it |
| 6 version floor | a failure: an old Codex was accepted | an old Codex is refused with a message that names both versions |
| 7 environment | no code change by judgement | documented as a limitation; `shell_environment_policy` is not overridden |

## Checks

| Check | Result |
| --- | --- |
| `python3 -m unittest tests.test_codex_resume -v` | 32 tests, OK, 10 skipped (the opt-in runtime class) |
| `DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v` | 32 tests, OK, 1 skipped (the pty picker: blocked in this sandbox) |
| `python3 -m unittest discover -s tests -p "test_codex_resume.py" -v` | 32 tests, OK, 10 skipped — the deterministic discovery starts no Codex CLI and no pty |
| `python3 -m unittest discover -s tests -v` (the whole deterministic suite) | 37 failures and 93 errors, none of them in `test_codex_resume`; the failing suites (skills, proxy, history, herdr, wsl, magpie process safety) are untouched by this change and fail the same way at the base commit `1aa75c9`: `python3 -m unittest tests.test_agent_payload tests.test_host_up tests.test_skill_selection` → 16 failures + 13 errors there as well. Several of them are this sandbox's missing pty and missing tools. |
| the round-1 command against the round-2 regressions | 6 failures (the trimmed key, the aliased inputs, the version floor) |
| `/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume` | clean |
| `git diff --check` | clean |
| ShellCheck, shfmt | **skipped**: not installed on this host, and installing them is out of scope |
| the pty picker | **blocked**: this sandbox allocates no pseudo terminal |

No install, download, push, reset, stash, or network fetch was made. The real
`~/.codex`, its sessions, its authentication, and the real
`~/.codex/magpie.config.toml` were never read or written; every run used a
synthetic home under this ticket's TMPDIR.

## Remaining limitations

- The interactive picker path is proven on a pty-capable host (the
  supervisor's), not in this sandbox. The driver and its assertions are the
  same code in both places.
- A turn produces more than one request at the provider. The auxiliary request
  is Codex's own and is deliberately not asserted on.
- The credential reaches Codex through the environment, so the shell commands
  the resumed agent runs inherit it. `shell_environment_policy` is not
  overridden, because a merge would replace the device's own list.
- The command needs Codex 0.169.0 or newer; an older Codex is refused. A
  newer Codex needs its own check before it is claimed.
- An aliased `magpie.config.toml`, an aliased `config.toml`, and a linked
  Codex home degrade the command to a plain resume. A device that links its
  Codex home gets no Magpie provider layer.
- Archived threads are not resumable; the command does not offer them.
- The neutral layer does not carry Magpie's model catalog
  (`model_catalog_json`): a catalog applies to the whole session.
- The layer carries a fixed set of provider keys; a provider option the
  command does not know is not carried.

## Proposed commit message

```
[agents]: harden the Codex resume command and its runtime check

Refuse the overrides that defeat the preservation the way Codex compares
them: the key of a configuration override is trimmed before it is compared,
so the spaced form of -c model=… is refused as well. Refuse an aliased
input the way the deployment's Codex boundary refuses one, and degrade with
a message instead of reading through the link. Refuse a Codex older than
0.169.0, whose selection rule needs the saved provider to equal the
provider of the current configuration.

Drive the interactive picker the way Codex 0.169.0 answers: wait for the
picker to render, browse with the arrow keys, accept the highlighted row,
wait for the thread view, and write the prompt and its Return in writes of
their own. Turn the startup update check off in the synthetic home, so the
update prompt can never be accepted.

Assert on the request that belongs to the resumed thread, the one whose
prompt_cache_key matches the thread's creation request, and keep the
auxiliary request of Codex's own out of the assertion. Gate the runtime
class behind DOTFILES_TEST_CODEX_RESUME=1, so the deterministic suite never
starts the real Codex CLI or a pseudo terminal, and record the credential in
the environment of the resumed agent as a documented limitation.
```

---

# Round 3 — the picker assertion of the supervisor's re-run

Workspace and branch are unchanged:
`/Users/joey/SHELL/dotfiles.fix-macos-codex-preserving-resume`, branch
`fix/macos-codex-preserving-resume`, base/integration tip `1aa75c9`. Nothing
was committed; the supervisor commits. Only the runtime harness, its
regressions, and the two documents that described the picker drive changed.

## The finding (red)

The supervisor's re-run of the round-2 work on its pty-capable host:

```
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
...
FAIL: test_the_picker_in_a_pty_resumes_the_thread
AssertionError: unexpectedly None : the resumed turn reached no endpoint
Ran 32 tests in 49.943s
FAILED (failures=1)
```

Everything else passed, including the seven runtime checks that do not need a
pseudo terminal. The driver itself worked: the scenario reported
`status: ran` with the full step list ("the picker rendered", "browsed with
the arrow keys", "accepted the highlighted row", "the thread view rendered",
"wrote the prompt in a write of its own", "submitted the prompt in a write of
its own") and `update_prompt_seen: false`.

The failure was in what the scenario looked at afterwards:

- The screen of the run showed that the resumed thread was the **alpha**
  thread (`› alphathread`, `› resumedalphaturn`, `› pickerturn`). The picker
  highlights the most recently *updated* session, and the alpha thread had
  just been updated by the app-server scenario, so it was the first row.
  The `↑` and then `↓` of the driver is a no-op when the list wraps.
- The scenario collected the requests of the run from the **Magpie provider
  only** (`received = magpie.received()[before:]`). The turn of the alpha
  thread reached the alpha endpoint, so `thread_request` stayed `null` and
  the assertion failed with "the resumed turn reached no endpoint".

## The fix

| File | Change |
| --- | --- |
| `tests/codex_resume_runtime.py` | the picker run collects the requests of **every** fake provider; the resumed thread is identified by its `prompt_cache_key` among the creation cache keys of all the synthetic threads; the driver no longer sends an arrow key; the target thread of the picker is created before the pty check and its creation request is picked by its own prompt |
| `tests/test_codex_resume.py` | the picker assertion also checks the provider of the resumed thread; a new deterministic class `PickerSelectionTests` covers the selection rule without a Codex and without a pseudo terminal |
| `docs/MAGPIE.md`, `docs/adr/0015-neutral-codex-resume-layer.md` | the picker drive and the request rule are described as they are now: no arrow key, no named row, every provider searched |

1. **Every provider is searched.** The picker run takes the requests of all
   three fake providers (`alpha`, `magpie`, `other`) from the moment the run
   starts, puts them in one list, and orders them by a sequence number of
   their own (`seq`), so the order of the requests is the order they arrived
   in. The picker run's requests are no longer read from the Magpie
   provider alone.
2. **The thread that was resumed is identified by its cache key.**
   `resumed_thread_request(received, known, prompt_text)` keeps the requests
   whose `prompt_cache_key` is one of the creation cache keys of the
   synthetic threads (`alpha`, `magpie`, `plain`, `picker-target`), prefers
   the one that carries the prompt of the run, and returns it. The thread's
   own saved provider, model, and reasoning effort are read from that
   creation request, so the assertion is a property:

   ```
   request["label"]   == saved["provider"]   # the thread's own provider
   request["model"]   == saved["model"]       # the thread's own model
   request["effort"]  == saved["effort"]      # the thread's own effort
   ```

   The auxiliary request of Codex's own (the thread title request) belongs to
   a thread of its own, carries a cache key that is not known, and is
   therefore not a candidate; it is still recorded apart under `auxiliary`.
3. **The browsing is dropped.** The picker orders the list and picks the
   highlighted row itself; the row order is not something this harness can
   rely on (the supervisor measured the highlighted row to be the alpha
   thread, not the row the driver had created for itself). The driver
   therefore sends **no arrow key** at all and accepts the row the picker
   highlights, and no row is claimed anywhere: the step list is now "the
   picker rendered", "accepted the highlighted row", "the thread view
   rendered", "wrote the prompt in a write of its own", "submitted the prompt
   in a write of its own". The docs no longer say that the driver browses
   with the arrow keys.
4. **The update-prompt guard and the separate writes are kept.** The driver
   still sends no key at all before the picker has rendered, still aborts the
   run when the update prompt is on the screen, and still writes the prompt
   text and its Return in writes of their own.

The target thread of the picker scenario is now created **before** the pty
check, so its creation is part of the report even where the picker cannot
run; its creation request is picked by its own first prompt ("picker target
thread") instead of by position, and the scenario records the exit code of
that run.

## Red and green

The rule is the thing that was wrong, so it is covered deterministically: the
requests of the several providers are put in one list, and the thread that was
resumed is the one whose creation request shares the cache key of the turn.

**Red** — the round-2 rule (the requests of the Magpie provider alone) put
back into the harness:

```
$ python3 -m unittest tests.test_codex_resume.PickerSelectionTests -v
FAIL: test_the_turn_of_a_thread_of_another_provider_is_found
AssertionError: unexpectedly None : the turn of the alpha provider was not found
Ran 5 tests in 0.000s
FAILED (failures=1)
```

That is the shape of the supervisor's failure ("unexpectedly None : the
resumed turn reached no endpoint") reproduced without a pseudo terminal.

**Green** — the harness searches every provider:

```
$ python3 -m unittest tests.test_codex_resume.PickerSelectionTests -v
test_a_turn_of_an_unknown_thread_is_not_accepted ... ok
test_the_auxiliary_request_of_codex_is_not_mistaken_for_the_turn ... ok
test_the_provider_scoped_rule_of_round_two_misses_the_turn ... ok
test_the_turn_of_a_thread_of_another_provider_is_found ... ok
test_the_turn_that_carries_the_prompt_wins ... ok
Ran 5 tests in 0.000s
OK
```

The class covers the finding (the turn of a thread of another provider is
found), the shape of the old rule (kept as the red), the auxiliary request of
Codex (not mistaken for the turn), the choice between two requests of the
same thread (the one that carries the prompt wins), and a turn of an unknown
thread (not accepted).

## The pty check: blocked here, run by the supervisor

This sandbox allocates no pseudo terminal, so the picker scenario cannot run
here:

```
$ python3 -c "import pty; pty.openpty()"
OSError: out of pty devices

$ python3 -c "import os; os.open('/dev/ptmx', os.O_RDWR)"
PermissionError: [Errno 1] Operation not permitted: '/dev/ptmx'
```

The harness records that as the blocker of the scenario and the test skips
with it:

```
opening a pseudo terminal failed: out of pty devices; opening /dev/ptmx failed: Operation not permitted (errno 1)
```

The supervisor's pty-capable host runs the same command:

```
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
```

**No result of that re-run is claimed here:** it cannot be run in this
sandbox, and nothing in this report stands in for it. What the re-run has to
show is the scenario with `status: ran`, the step list without the browsing
step, `update_prompt_seen: false`, and the picker assertion holding for
whichever row the picker highlights — the resumed turn carrying that thread's
own saved provider, model, and reasoning effort.

## Checks

| Check | Result |
| --- | --- |
| `python3 -m unittest tests.test_codex_resume -v` | 37 tests, OK, 10 skipped (the opt-in runtime class) |
| `python3 -m unittest discover -s tests -p "test_codex_resume.py" -v` | 37 tests, OK, 10 skipped — the deterministic discovery starts no Codex CLI and no pty |
| `DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v` | 37 tests, OK, 1 skipped (the pty picker: blocked in this sandbox) |
| the round-2 provider scope put back into the harness | 1 failure: "the turn of the alpha provider was not found" (the red) |
| `python3 tests/codex_resume_runtime.py` | the report of the run: the picker target thread is created (`exit: 0`, `created: true`), the four synthetic threads are in `known_threads` with their own provider, model, and effort, and the picker scenario is `blocked` with the pty error |
| `/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume` | clean (the command itself did not change in this round) |
| `git diff --check` | clean |
| the pty picker | **blocked**: this sandbox allocates no pseudo terminal (the errors above); the supervisor's host runs it |

No install, download, push, reset, stash, or network fetch was made. The real
`~/.codex`, its sessions, its authentication, and the real
`~/.codex/magpie.config.toml` were never read or written; every run used a
synthetic home under this ticket's TMPDIR, every fixture uses a placeholder
credential, and the fake providers bound ephemeral loopback ports, never 3425.

## Remaining risks

- The picker path is still unproven **in this sandbox**; it is the
  supervisor's pty-capable host that runs it, and the result of that re-run is
  not part of this report.
- The picker's row order is the picker's own. The assertion no longer depends
  on it, but the *report* of a run still cannot say which row was resumed: it
  says which thread was resumed, by its cache key.
- The picker scenario creates one thread of its own before the run, so the
  picker lists the synthetic sessions of the other scenarios as well. A row
  of any of them may be the highlighted one; every one of them is in
  `known_threads` with its own saved provider, model, and effort.
- The identifier of a thread is its `prompt_cache_key`. A Codex release that
  mints a new key on resume would make the turn "belong to an unknown
  thread" and fail the assertion loudly rather than silently.
- Everything else of round 2 stands: the picker depends on the behaviour of
  Codex 0.169.0's picker and on the command needing 0.169.0 or newer, the
  credential reaches Codex through the environment, an aliased Magpie profile
  degrades the command to a plain resume, and the neutral layer does not
  carry Magpie's model catalog.

---

# Round 4 — the picker waits for the loaded session list

Workspace and branch are unchanged:
`/Users/joey/SHELL/dotfiles.fix-macos-codex-preserving-resume`, branch
`fix/macos-codex-preserving-resume`, base/integration tip `1aa75c9`. Nothing
was committed; the supervisor commits. The round-3 collection rule is
accepted and was not touched: the picker run still collects the requests of
every fake provider, still identifies the resumed thread by its
`prompt_cache_key`, and still asserts on that thread's own provider, model,
and effort. The new deterministic `PickerSelectionTests` still pass on the
supervisor's host.

## The finding (red)

The supervisor's re-run of the round-3 work on its pty-capable host:

```
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
...
FAIL: test_the_picker_in_a_pty_resumes_the_thread
AssertionError: 'failed' != 'ran'
- failed
+ ran
 : the thread view did not render
Ran 37 tests in 111.404s
FAILED (failures=1)
```

The driver's own steps show where it stopped:

```
status: failed
error: the thread view did not render
steps: ["the picker rendered", "accepted the highlighted row",
        "the thread view rendered: timed out"]
update_prompt_seen: false
```

So the picker rendered, the Return was sent, and the thread view never came:
the Return was sent while the picker was still the picker.

## The cause

The picker renders in two stages, and the screen the driver captured shows
both of them:

```
Resume a previous session Filter: Cwd All Status: Active Archived Sort: Updated Created
Type to search Loading sessions… ──────────── 0 / 0… · 0% ─ enter resume esc start new …
› 2s ago ● picker target thread 5s ago ● alpha thread 8s ago ● magpie thread 12s ago ● plain magpie session
1 / 4
```

The header and the footer are there at once, so the wait for the picker ends
while the list is still loading ("Loading sessions…", "0 / 0… · 0%"). The
Return is sent in that state, no row is accepted, and the picker stays on
screen: the list that follows is the rows, and the counter "1 / 4" is the
first moment at which a row can be chosen. `PICKER_MARKERS` contains the
title "Resume a previous session", which is why the wait ended too early; in
round 2 the arrow keys had given the list the time it needed before the
Return, and round 3 dropped the arrow keys — so the wait became the only
thing between the picker and its Return.

## The fix

| File | Change |
| --- | --- |
| `tests/codex_resume_runtime.py` | the new rule `session_list_loaded(text)` and the new wait step "the session list loaded" between the picker and its Return |
| `tests/test_codex_resume.py` | the new deterministic class `PickerListTests` (5 tests): the rule holds for a loaded list and fails for a loading one |
| `docs/MAGPIE.md`, `docs/adr/0015-neutral-codex-resume-layer.md` | the picker drive is described with the wait for the loaded list; the fallback model metadata is documented as a limitation |

1. **Wait until the session list has rows before the Return.** The rule
   reads the counter of the picker: the list is loaded when the counter has a
   non-zero total ("1 / 4"), and the counter of the loading stage
   ("0 / 0… · 0%") has a total of zero, so it can never satisfy the rule.
   The rule cannot be satisfied while the list is loading: a counter of
   "0 / 0" has no total and "0 / 4" has no highlighted row, so only a
   counter with a highlighted row out of a non-zero total ("1 / 4") ends the
   wait.
2. **The update-prompt guard and the separate writes are kept.** The driver
   still sends no key at all before the picker has rendered, still aborts the
   run when the update prompt is on the screen, and still writes the prompt
   text and its Return in writes of their own.
3. **The highlighted row is still accepted, and no row and no order is
   claimed.** The driver still sends no arrow key and still accepts the row
   the picker highlights; the assertion is still a property of the thread
   that was actually resumed.
4. **The rule has a deterministic test of its own**, in the spirit of
   `PickerSelectionTests`: it needs no Codex and no pseudo terminal. It
   holds for a loaded list, it fails for a loading list ("0 / 0… · 0%"), it
   fails for a counter without a total, and it shows the defect of the
   round-3 driver — the markers of the picker are on the loading screen, so
   they alone never tell a loaded list.

The step list of the run is now "the picker rendered", "the session list
loaded", "accepted the highlighted row", "the thread view rendered", "wrote
the prompt in a write of its own", "submitted the prompt in a write of its
own".

## Red and green (deterministic)

**Red** — the new class against the round-3 harness:

```
$ python3 -m unittest tests.test_codex_resume.PickerListTests -v
ERROR: test_a_loading_list_is_not_loaded (tests.test_codex_resume.PickerListTests.test_a_loading_list_is_not_loaded)
AttributeError: module 'tests.codex_resume_runtime' has no attribute 'session_list_loaded'
...
Ran 5 tests in 0.003s
FAILED (errors=7)
```

**Green** — with the rule and the wait:

```
$ python3 -m unittest tests.test_codex_resume.PickerListTests -v
test_a_counter_without_a_total_is_not_loaded ... ok
test_a_loaded_list_is_loaded ... ok
test_a_loading_list_is_not_loaded ... ok
test_the_counter_of_the_loading_stage_is_never_satisfied ... ok
test_the_picker_markers_alone_do_not_tell_a_loaded_list ... ok
Ran 5 tests in 0.000s
OK
```

## The supervisor's re-run of the fixed sequence

On the supervisor's pty-capable host, with the wait for the loaded list and
everything else unchanged, the same scenario reports:

```
status: ran
steps: ["the picker rendered", "the session list loaded",
        "accepted the highlighted row", "the thread view rendered",
        "wrote the prompt in a write of its own",
        "submitted the prompt in a write of its own"]
```

The resumed turn reached the **magpie** provider with the model
`gpt-6.1-terra` and the effort `high`, and its `prompt_cache_key` is the one
of the picker-target thread, whose own saved model and effort are the same.
The second request (effort `medium`, its own cache key) is Codex's own
auxiliary call and stays apart from the turn.

## The pty check: blocked here, run by the supervisor

This sandbox allocates no pseudo terminal, so the picker scenario cannot run
here:

```
$ python3 -c "import pty; pty.openpty()"
OSError: out of pty devices

$ python3 -c "import os; os.open('/dev/ptmx', os.O_RDWR)"
PermissionError: [Errno 1] Operation not permitted: '/dev/ptmx'
```

The harness records that as the blocker of the scenario and the test skips
with it:

```
opening a pseudo terminal failed: out of pty devices; opening /dev/ptmx failed: Operation not permitted (errno 1)
```

The supervisor's pty-capable host runs the same command:

```
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
```

**No result of that re-run is claimed from this sandbox:** it cannot be run
here, and nothing in this report stands in for it.

## The documentation task: the fallback model metadata

The neutral layer carries provider definitions only. A thread whose model the
active catalog does not know — every Magpie group id — therefore runs with
Codex's fallback model metadata, and Codex says so:

```
warning: Model metadata for `magpie-only/group-openai-stack` not found.
Defaulting to fallback metadata; this can degrade performance and cause issues.
```

What the fallback changes is the metadata Codex assumes about the model: the
context window it assumes, the model-specific tool modes, and the web search
tool. What still holds is the routing: the saved provider, the saved model,
and the saved reasoning effort are all used, so a thread created with effort
`high` sends effort `high` after the resume.

The catalog is not carried. It can be delivered through the same CLI channel
(`-c model_catalog_json=<absolute path>` removes the warning), but an
explicit catalog resolves a model by its exact slug alone and replaces the
active catalog for the whole process, so carrying it would take the model
metadata away from the other threads resumed in the same run.

This is now a limitation in the resume section of `docs/MAGPIE.md` and a
consequence in ADR `0015-neutral-codex-resume-layer.md`, one short paragraph
in each place. No behaviour and no code changed for it.

## Checks

| Check | Result |
| --- | --- |
| `python3 -m unittest tests.test_codex_resume -v` | 42 tests, OK, 10 skipped (the opt-in runtime class) |
| `python3 -m unittest discover -s tests -p "test_codex_resume.py" -v` | 42 tests, OK, 10 skipped — the deterministic discovery starts no Codex CLI and no pty |
| `DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v` | 42 tests, OK, 1 skipped (the pty picker: blocked in this sandbox); the other 41 tests of the run passed against the installed Codex 0.169.0 |
| `python3 -m unittest tests.test_codex_resume.PickerListTests -v` | 5 tests, OK (and 7 errors before the rule existed: the red) |
| `/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume` | clean (the command itself did not change in this round) |
| `git diff --check` | clean |
| the pty picker | **blocked**: this sandbox allocates no pseudo terminal (the errors above); the supervisor's host runs it |

No install, download, push, reset, stash, or network fetch was made. The real
`~/.codex`, its sessions, its authentication, and the real
`~/.codex/magpie.config.toml` were never read or written; every run used a
synthetic home under this ticket's TMPDIR, every fixture uses a placeholder
credential, and the fake providers bound ephemeral loopback ports, never 3425.

## Remaining risks

- The picker path is still unproven **in this sandbox**; it is the
  supervisor's pty-capable host that runs it.
- The wait for the list reads the counter of the picker ("1 / 4"). A Codex
  release that renders the counter differently (no counter, or a counter
  without a total while the rows are there) would make the driver time out
  and fail loudly, not silently accept nothing.
- The screen buffer is cumulative, so the rule cannot tell "the list has
  rows" from "the list had rows once": a Codex release that clears the list
  afterwards would still let the Return through. The picker of 0.169.0 does
  not do that.
- The fallback model metadata of a model outside the active catalog is
  documented, not fixed: the context window Codex assumes, the
  model-specific tool modes, and the web search tool are Codex's fallback
  values for such a model, and the catalog is deliberately not carried.
- Everything else of rounds 2 and 3 stands: the picker's row order is the
  picker's own, the identifier of a thread is its `prompt_cache_key`, the
  credential reaches Codex through the environment, an aliased Magpie profile
  degrades the command to a plain resume, and the command needs Codex
  0.169.0 or newer.

---

# Round 5

Two findings of the managed command, both measured with a fake Codex that
records its argv. The fake Codex is the one of `tests/test_codex_resume.py`:
it answers `--version` with `codex-cli 0.169.0` and records the argv of the
resume. The synthetic home holds a `magpie.config.toml` with a placeholder
credential; the real `~/.codex` was never read or written.

## Finding 1: a user override of a key the command owns was discarded in silence

### The measurement (red)

```
$ dotfiles-codex-resume -c model_providers.magpie.base_url=http://127.0.0.1:1/v1
exit=0
argv:
  resume --all --include-non-interactive
  -c model_providers.magpie.base_url=http://127.0.0.1:1/v1
  -c model_providers.magpie.name="magpie"
  -c model_providers.magpie.base_url="http://127.0.0.1:39411/v1"
  -c model_providers.magpie.wire_api="responses"
  -c model_providers.magpie.http_headers.x-openai-actor-authorization="magpie"
  -c model_providers.magpie.env_key="DOTFILES_CODEX_RESUME_MAGPIE_TOKEN"
```

The user's value reached Codex and was then overwritten by the command's own
definition, because the command appends its definitions after the user's
overrides and Codex applies the overrides in order. Nothing was said and the
exit status was 0. The table is not a preference: the command derives
`model_providers.magpie` from Magpie's own profile and attaches the gateway
credential to that provider, so an override of it would reroute the thread
away from its saved provider and would carry the credential to another
endpoint.

### The fix

The refusal block of the command now owns the table as well. A key of a
configuration override is refused when it is `model_providers.magpie` or lies
inside `model_providers.magpie.`, with exit status 2 and a message that names
the reason:

```
dotfiles-codex-resume: refusing -c model_providers.magpie.base_url=http://127.0.0.1:1/v1: the command owns the model_providers.magpie provider definition; an override of it would reroute the thread away from its saved provider.
```

Codex is not started at all in that case. The trimmed-key rule is unchanged
and applies to the new rule as well: Codex trims the key of an override
before it applies it, so `-c ' model_providers.magpie.base_url = "…"'` selects
the same key and is refused the same way.

Every other `model_providers.` key is left alone. A provider the command does
not generate is the user's own business:

```
$ dotfiles-codex-resume -c model_providers.other.base_url=http://127.0.0.1:9/v1
exit=0
argv: … -c model_providers.other.base_url=http://127.0.0.1:9/v1 -c model_providers.magpie.name="magpie" …
```

## Finding 2: the usage text did not match what `--last` does

### The measurement (red)

```
$ dotfiles-codex-resume --last 01a1eff0-1111-2222-3333-444455556666
exit=0
argv:
  resume --all --include-non-interactive --last 01a1eff0-1111-2222-3333-444455556666
```

Codex's own rule (`finalize_resume_interactive` in codex 0.169.0) is that
with `--last` and no prompt the session id is reinterpreted as the *prompt*
of the most recent thread. The command passed its positional through
unchanged, so the id was typed as the prompt of the most recent thread,
silently, while the usage text promised the opposite ("`--last` continues the
most recent thread", with the first positional documented as the session id).

### The fix

The usage text now describes the real rule: without `--last` the first
positional is the session id and the second is the prompt; with `--last` the
first positional is the prompt of the most recent thread, exactly as
`codex resume` reads it.

The silently wrong combination is refused. A `--last` whose first positional
is a session id (a UUID) exits 2 with a message that names the fix:

```
dotfiles-codex-resume: refusing --last 01a1eff0-1111-2222-3333-444455556666: with --last, codex resume reads the first positional as the prompt of the most recent thread, not as a session id; drop --last to resume that thread.
```

A `--last` with an ordinary prompt keeps working, and a session id without
`--last` keeps working. The order of the arguments the command hands to Codex
did not change, and the command does not re-interpret the positionals: it
passes them through and Codex reads them. Only the UUID shape of the first
positional is inspected, and only to refuse the combination.

## The tests

Seven new deterministic tests in `tests/test_codex_resume.py`:

| Test | What it holds |
| --- | --- |
| `test_a_magpie_provider_override_is_refused` | three overrides of the owned table are refused with status 2, the message names the table and the saved provider, and Codex is not started |
| `test_a_spaced_magpie_provider_override_is_refused` | the spaced and tabbed forms are refused the same way (the trimmed-key rule) |
| `test_another_provider_override_still_reaches_codex` | `-c model_providers.other.base_url=…` still reaches Codex |
| `test_the_usage_describes_the_rule_of_last` | the usage text names the rule of `--last` and the fix |
| `test_last_with_a_session_id_is_refused` | the refusal with its message and no Codex run |
| `test_last_with_an_ordinary_prompt_keeps_working` | a prompt with `--last` still resumes |
| `test_a_session_id_without_last_keeps_working` | a session id without `--last` still resumes |

Red then green, measured with the pre-fix script (the fixed script was
backed up, the two rules and the usage text were reverted in a copy, and the
copy was run in place of the command):

```
before the fix:  Ran 29 tests … FAILED (failures=7)
  test_a_magpie_provider_override_is_refused (×3 subtests)
  test_a_spaced_magpie_provider_override_is_refused (×2 subtests)
  test_last_with_a_session_id_is_refused
  test_the_usage_describes_the_rule_of_last
after the fix:   Ran 49 tests … OK (skipped=10)
```

The two "keeps working" tests passed before the fix as well: they are the
guards that the new rules do not narrow what worked.

## The documentation

`docs/MAGPIE.md` (the resume section) now states the rule of the positionals
and of `--last`, and the refusal of an override of the provider table the
command owns, next to the refusals of rounds 1 to 4.

## Checks

| Check | Result |
| --- | --- |
| `python3 -m unittest tests.test_codex_resume -v` | 49 tests, OK, 10 skipped (the opt-in runtime class) |
| `python3 -m unittest discover -s tests -p "test_codex_resume.py"` | 49 tests, OK, 10 skipped |
| `DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v` | 49 tests, OK, 1 skipped (the pty picker: blocked in this sandbox); the other 48 passed against the installed Codex 0.169.0 |
| `/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume` | clean |
| `git diff --check` | clean |
| the pty picker | **blocked**: this sandbox allocates no pseudo terminal (the errors below); the supervisor's host runs it |

The pty check cannot run in this sandbox:

```
$ python3 -c "import pty; pty.openpty()"
OSError: out of pty devices

$ python3 -c "import os; os.open('/dev/ptmx', os.O_RDWR)"
PermissionError: [Errno 1] Operation not permitted: '/dev/ptmx'
```

The harness records that as the blocker of the scenario and the test skips
with it:

```
opening a pseudo terminal failed: out of pty devices; opening /dev/ptmx failed: Operation not permitted (errno 1)
```

**No result of that check is claimed from this sandbox:** the supervisor's
pty-capable host runs the same command.

No install, download, push, reset, stash, or network fetch was made. The real
`~/.codex`, its sessions, its authentication, and the real
`~/.codex/magpie.config.toml` were never read or written; every run used a
synthetic home under this ticket's TMPDIR, every fixture uses a placeholder
credential, and the fake providers bound ephemeral loopback ports, never 3425.

## Remaining risks

- The picker path is still unproven **in this sandbox**; it is the
  supervisor's pty-capable host that runs it.
- The refusal of the owned provider table is unconditional: it also refuses an
  override of `model_providers.magpie.*` when the command generated no
  definition of its own (no Magpie profile, an aliased profile, or a device
  definition of its own). The command owns that table by contract, and the
  contract is stated in the message, but a user who wants to override the
  device's own Magpie definition has to drop the wrapper.
- The session-id shape of the first positional is detected as a UUID. Codex
  also accepts a session *name* as a first positional, and a name with
  `--last` is passed through as a prompt as well; only the UUID form is
  refused, as the finding requires.
- The refusal of `--last` with a session id fires before the version check
  and before the provider layer is read, so it is the same for every Codex
  the command supports.
- Everything else of rounds 1 to 4 stands: the credential reaches Codex
  through the environment, an aliased Magpie profile degrades the command to
  a plain resume, the fallback model metadata of a model outside the active
  catalog is documented and not fixed, and the command needs Codex 0.169.0 or
  newer.
