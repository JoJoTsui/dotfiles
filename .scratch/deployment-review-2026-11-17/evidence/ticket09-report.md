# Ticket 09 report: isolated Codex profile safety

Worktree: `/Users/joey/SHELL/dotfiles.fix-macos-codex-profile-safety`
Branch: `fix/macos-codex-profile-safety`
Base (verified before the first edit): `37dc127d71d01097904f6c33b2aea4665791e50a`
("[agents]: isolate codex magpie profile wiring"), the same commit the
integration branch `fix/deployment-review` points at. Nothing was committed,
reset, stashed, pushed, or installed; the diff is left for the supervisor.

Integration tip movement: none. `fix/deployment-review` is still `37dc127`;
this branch is still based on it, with the work below uncommitted.

Chronology: the first attempt of this ticket wrote the ten initial
regressions and their fixes and was interrupted by a client timeout; its
work survived. The supervisor recovered its full-suite log (276 tests in
711.613s, OK) and verified two concrete defects through the public apply
seam. This attempt added the four public regressions for those defects and
one strengthened existing test, the minimal fixes, the assertion-enforcing
native-CLI scripts, and a fresh full-suite run of the final source.

## What the ticket asked for, and what this change does

* Public apply regressions first, then the minimal fix, at the approved public
  seam (`magpie_apply` through `tests/test_magpie.py`'s fake CLI).
* The generated profile and catalog are refused when the Codex home is a
  symlink or not a directory, when a profile path is a symlink or not a
  regular file, when the generated file has another name (a hard link), or
  when its link count cannot be read. Every refusal happens before the
  gateway, the backup, and the provider registration, and leaves the aliased
  bytes as they are.
* A device without a Codex home gets one of its own, private: `~/.codex` at
  0700 and the profile placeholder at 0600. The base configuration and
  authentication are never created or written.
* The scope is read with the pinned CLI's read-only getter and selected
  before the gateway changes. The getter has to succeed and answer in the
  pinned CLI's own shape; the pinned CLI's refusal while the ordinary Codex
  integration is connected now stops the run there; the deployment
  disconnects and retags nothing.
* The base configuration and authentication hashes are compared after the
  scope selection whether the command succeeded or failed, so a failed
  selection that still changed a file is reported as a change and the run
  never claims a preservation it did not observe.
* The pinned CLI was executed in an isolated synthetic home against a fake
  gateway address, with fabricated configuration and no credential. The
  scripts assert every outcome they claim and fail on a digest mismatch
  before the payload is executed.
* The ownership and rollback contract in `docs/MAGPIE.md` and ADR 0014 was
  updated to the verified behaviour.

## Changed files

| File | Change |
| --- | --- |
| `deployment/magpie.sh` | Codex home, link-count, scope getter, ordinary-connection and scope preflights; private Codex home creation; clearer failure for a profile the pinned writer cannot parse. |
| `tests/test_magpie.py` | Ten new public apply regressions in the first attempt, plus four more here for the fail-closed scope getter, the unreadable link count, and the scope setter that changes the base configuration or authentication, and one existing test strengthened with the evidence-based diagnostic; the fake CLI now mirrors the pinned getter's answer, its refusal, its refusal to write over a file it cannot parse, and a setter that changes the base configuration or authentication; the tests stage their temporary files in their own directory. |
| `docs/MAGPIE.md` | Apply order (the scope selection moved before the gateway changes), the Codex section (collisions, private creation, the scope preflight, the link count, the hash guards), the rollback contract, and the real-CLI evidence boundary. |
| `docs/adr/0014-magpie-owns-the-model-gateway.md` | The ownership consequences of the preflights and the scope selection. |

## Red-green record

Every cycle was one failing public test, then the minimal change, then the
same test green. The command was always:

```bash
cd /Users/joey/SHELL/dotfiles.fix-macos-codex-profile-safety
python3 -m unittest tests.test_magpie.MagpieApplyTests.<test name> -v
```

The five new cycles were run as:

```bash
python3 -m unittest tests.test_magpie.MagpieApplyTests.test_a_failed_codex_scope_getter_stops_the_apply_before_the_gateway_changes
python3 -m unittest tests.test_magpie.MagpieApplyTests.test_a_codex_scope_setter_that_changes_the_base_configuration_is_reported
python3 -m unittest tests.test_magpie.MagpieApplyTests.test_a_codex_scope_setter_that_changes_the_authentication_is_reported
python3 -m unittest tests.test_magpie.MagpieApplyTests.test_a_codex_profile_with_an_unreadable_link_count_is_refused_before_any_change
python3 -m unittest tests.test_magpie.MagpieApplyTests.test_a_refused_codex_scope_stops_the_apply_before_the_gateway_changes
```

The first ten cycles are in the earlier attempt of this ticket:

| # | Test | Red (observed) | Green |
| --- | --- | --- | --- |
| 1 | `test_a_linked_codex_home_is_refused_without_writing_through_the_link` | `AssertionError: 0 == 0` (the apply wrote the profile through the link) | ok |
| 2 | `test_a_hard_linked_codex_profile_is_refused_and_its_other_name_is_preserved` | `'other names' not found in '... an unrecorded Codex profile or model catalog already exists; preserving it'` | ok |
| 3 | `test_a_hard_linked_codex_catalog_is_refused_and_its_other_name_is_preserved` | same, the unrecorded rule answered instead of the link rule | ok |
| 4 | `test_a_recorded_codex_profile_with_another_name_is_refused_and_kept` | `AssertionError: 0 == 0` (the recorded hard-linked profile was adopted) | ok |
| 5 | `test_a_fresh_codex_home_is_created_privately` | `magpie.sh: ... /.codex/magpie.config.toml: No such file or directory` / `dotfiles: magpie: cannot create the private Codex profile` | ok |
| 6 | `test_a_codex_home_that_is_a_file_is_refused` | written with #5; the not-a-directory rule arrived with the linked-home rule in the same check block | ok |
| 7 | `test_a_connected_ordinary_codex_integration_stops_the_apply_before_the_gateway_changes` | `'ordinary Codex integration is connected' not found in 'magpie: disconnect Codex from magpie first, then change what it applies to\ndotfiles: magpie: cannot select the separate Codex profile'`, after `provider add`, `settings set`, `group add`, `visible` had run | ok |
| 8 | `test_a_refused_codex_scope_stops_the_apply_before_the_gateway_changes` | the same run of gateway mutations before the refusal | ok |
| 9 | `test_an_unreadable_codex_scope_stops_the_apply_before_the_gateway_changes` | `AssertionError: 0 == 0` (the scope was never read) | ok |
| 10 | `test_a_malformed_recorded_codex_profile_is_preserved_and_reported` | `AssertionError: True is not false` (the apply recorded a new state over the malformed profile) | ok |

Three existing tests changed with the behaviour they pin, and the changes are
in the same logical fix: the command order test now expects
`codex scope profile` before `provider add codex`, and the two tests that
pin the exact Codex command list now expect the read-only getter
(`codex scope`) before the selection.

### The second attempt: the two defects the supervisor verified

The supervisor verified both defects through the public Magpie apply seam.
Each got a public regression first, then the minimal fix.

| # | Test | Red (observed) | Green |
| --- | --- | --- | --- |
| 11 | `test_a_failed_codex_scope_getter_stops_the_apply_before_the_gateway_changes` | `AssertionError: 'cannot read the Codex scope' not found in 'dotfiles: magpie: the Codex configuration changed during profile wiring\n'` (the getter's failed command was ignored, its printed answer was taken as the scope, and the apply went on to mutate the gateway) | ok |
| 12 | `test_a_codex_scope_setter_that_changes_the_base_configuration_is_reported` | `AssertionError: 'the Codex configuration changed while selecting its profile' not found in 'dotfiles: magpie: cannot select the separate Codex profile; the ordinary Codex integration is connected or the scope cannot be changed safely, and the ordinary integration is left as it is\n'` (the hash guard was skipped on the failed command, and the message claimed a preservation nobody had checked) | ok |
| 13 | `test_a_codex_scope_setter_that_changes_the_authentication_is_reported` | `AssertionError: 'the Codex authentication changed while selecting its profile' not found in 'dotfiles: magpie: cannot select the separate Codex profile; ... and the ordinary integration is left as it is\n'` | ok |
| 14 | `test_a_codex_profile_with_an_unreadable_link_count_is_refused_before_any_change` | `AssertionError: 'link count' not found in 'dotfiles: magpie: the Codex profile did not retain the requested provider, model, catalog, gateway, and private mode\n'` (the unreadable link count was read as one link, so the run continued and the alias's bytes were changed before it failed) | ok |
| 15 | `test_a_refused_codex_scope_stops_the_apply_before_the_gateway_changes` (existing test, strengthened) | `AssertionError: 'the Codex configuration and authentication are unchanged' not found in 'dotfiles: magpie: cannot select the separate Codex profile; ... and the ordinary integration is left as it is\n'` | ok |

The three fixes in `deployment/magpie.sh`:
* `magpie_codex_scope_read` captures the getter's output and its exit status
  together. A getter that failed is a failure even when it printed
  `Codex applies to profile`. The answer is read in the pinned CLI's own
  shape (`<Name> applies to <profile|default>`, ANSI codes stripped), so an
  answer that is not that shape, or that contradicts itself, is a failure
  before any mutation.
* The preflight's link count is no longer guessed. A `stat` that cannot
  answer, or an answer that is not a number, fails the preflight closed
  before the backup, the provider registration, and the profile write. The
  GNU (`stat -c '%h'`) and BSD (`stat -f '%l'`) forms are both kept.
* The scope preflight compares the base configuration and authentication
  hashes after the selection whether the setter succeeded or failed, so a
  failed command cannot skip the guard, and the run only says the
  configuration and authentication are unchanged when the comparison shows
  it.

## The pinned CLI, in an isolated home

Payload: `/tmp/dotfiles-magpie-cli.9rXfZ6/payload/magpie`, copied to
`$TMPDIR/magpie-ticket09/magpie` and made executable there.
`sha256 2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132`
(the approved digest, matched before every run).

The supervisor's read-only scratch directory held the approved payload, the
fake gateway, and the two scripts; this attempt copied them into its own
`TMPDIR` before changing or running any of them:

```bash
S=/tmp/dotfiles-completion-supervisor.q3I96s/ticket-09b/tmp/magpie-ticket09
D="$TMPDIR/magpie-ticket09"; mkdir -p "$D"
cp "$S/magpie" "$S/fake_gateway.py" "$S/real_cli_check.sh" "$S/real_cli_hazards.sh" "$D/"
chmod +x "$D/magpie" "$D"/*.sh
shasum -a 256 "$D/magpie"
# 2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132  (the approved digest)
```

Isolation: `HOME` is a synthetic directory under `$TMPDIR`; `MAGPIE_ADDR`
points the CLI at a fake gateway on a private port (the address the CLI's
own help names for `--addr`/`MAGPIE_ADDR`); the fake gateway logs every
request it receives. `sandbox-exec` was tried in the first attempt and is
not permitted in this environment (`sandbox_apply: Operation not
permitted`); the nested attempt was not repeated, and the parent sandbox
was not relaxed. The run used the source-proven fake routing with the
guard below. The live gateway on `127.0.0.1:3425` was never contacted: the
CLI reported the fake address, the fake gateway received the only request,
the profile names the fake address, and the live port appears in no output
and in no generated file.

Both scripts were rewritten for this attempt so that a passing run is
evidence and a printed line is not: the payload digest is checked before any
byte of the payload is executed, every expected outcome, exit code, count,
and hash is asserted, the script exits non-zero when an assertion does not
hold, and the expected negative cases stay negative.

```bash
SCRATCH="$TMPDIR/magpie-ticket09" PAYLOAD="$TMPDIR/magpie-ticket09/magpie" PORT=3604 \
  bash "$TMPDIR/magpie-ticket09/real_cli_check.sh"     # exit 0
SCRATCH="$TMPDIR/magpie-ticket09" PAYLOAD="$TMPDIR/magpie-ticket09/magpie" PORT=3605 \
  bash "$TMPDIR/magpie-ticket09/real_cli_hazards.sh"   # exit 0
```

The three scripts are value-free and are kept in this worktree as well, so
the evidence survives the scratch directory:
`.scratch/ticket09-native-cli/real_cli_check.sh`,
`.scratch/ticket09-native-cli/real_cli_hazards.sh`,
`.scratch/ticket09-native-cli/fake_gateway.py`. The payload binary itself is
not copied into the worktree; the digest above identifies it.

Complete outputs (value-free; the logs are `$TMPDIR/logs/real-cli-check-3.log`
and `$TMPDIR/logs/real-cli-hazards-3.log`):

```
the payload digest matches the approved one before execution: sha256 2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132
== version ==            magpie 0.1.4404            [exit 0]
== status ==             "url": "http://127.0.0.1:3604", "addr": "127.0.0.1:3604"   [exit 0]
== scope getter, before ==   Codex applies to default   [exit 0]
== scope setter ==           ✓ Codex applies to profile [exit 0]
== scope getter, after ==    Codex applies to profile  [exit 0]
== profile write ==          ✓ Codex model group/openai-stack   [exit 0]
== the base configuration and authentication after the profile write ==
config.toml 551a3d47a87fa0ee028bd2b06f1596d267c601542d5e6db9ea960847bc30dfa1
auth.json   fd8aa55319e4139b8403ef1a6927738e84615c12fdc141fc638a173898496f99
== generated files ==
auth.json mode=600 bytes=62 sha256=fd8aa55319e4139b8403ef1a6927738e84615c12fdc141fc638a173898496f99
config.toml mode=644 bytes=51 sha256=551a3d47a87fa0ee028bd2b06f1596d267c601542d5e6db9ea960847bc30dfa1
magpie-models.json mode=644 bytes=543306 sha256=4c97c7dc2df12bdecac07bb19bd2bd4ade04e15f7e29e53aac272514bcbc6ddb
magpie.config.toml mode=644 bytes=643 sha256=b978aa7f6dff09d3700c07cc122015cc2cc847c93bb034363349bc75eea491b6
== the profile's keys (no values) ==
base_url  experimental_bearer_token  http_headers  model  model_catalog_json  model_provider  name  wire_api
== the gateway address the profile names ==   http://127.0.0.1:3604/v1
== the live gateway port in any output or generated file ==
the live port appears nowhere in the generated files
== the requests the fake gateway received ==   GET /     requests=1
OK: every assertion held
```

Write behaviour, one isolated home per case (the hazards script, exit 0):

```
== a private placeholder keeps its mode ==   profile mode=600, catalog mode=644
== a file with another name is written in place ==
   alias before: model = "device-model"
   alias after:  model = "group/openai-stack"      links=2
== a linked Codex home is written through ==
   the linked directory holds: magpie-models.json magpie.config.toml
== the ordinary integration refuses the scope change ==
   magpie: disconnect Codex from magpie first, then change what it applies to   [exit 1]
== a profile the writer cannot parse is preserved ==
   magpie: .../magpie.config.toml: line 1, column 19: expected character =     [exit 1]
   profile after: device-owned-bytes
== the rollback: disconnect the profile, then the scope itself is reset ==
   ✓ Codex model default / disconnected from magpie, back to what it had before
   Codex applies to profile      (the scope is Magpie's own preference)
   ✓ Codex applies to default    (after `codex scope default`)
OK: every assertion held
```

These four results are why the deployment refuses the linked home, the file
with another name, and the malformed profile, and why the scope is selected
before the gateway changes. The pinned writer follows a symlinked parent,
writes a file with other names in place, and refuses a file it cannot parse.

The fixture in `tests/test_magpie.py` was changed to match this demonstrated
behaviour, not to invent a contract: the getter answers `Codex applies to
default` / `Codex applies to profile`, the selection is refused while the
ordinary integration is connected, and the profile write is refused over a
file the writer cannot parse.

## Checks

| Check | Command | Result |
| --- | --- | --- |
| Full Magpie suite | `python3 -m unittest tests.test_magpie -v` | `Ran 284 tests in 570.272s` — `OK`, no skips. Log: `$TMPDIR/logs/full-suite-3.log`. (`MagpieCommandTests` derives from `MagpieApplyTests`, so each apply test runs twice: 142 unique tests, 284 in the run.) |
| Full Magpie suite, earlier attempt | `python3 -m unittest tests.test_magpie -v` | `Ran 276 tests in 711.613s` — `OK` (the supervisor recovered this log from the first attempt, `/tmp/dotfiles-completion-supervisor.q3I96s/ticket-09b/tmp/magpie-ticket09/full-suite-2.log`; it is the 276-test checkpoint result, not a quota failure) |
| Apply class | `python3 -m unittest tests.test_magpie.MagpieApplyTests` | `Ran 103 tests in 251.333s` OK |
| Bash syntax | `/bin/bash -n deployment/magpie.sh` | pass |
| Whitespace | `git diff --check` | pass |
| Shell linters | `shellcheck`, `shfmt` | not installed on this host; skipped, not installed |
| Neighbouring Magpie modules | not rerun | the earlier attempt ran them: 8 failures + 1 error, identical on the untouched checkpoint (they stage files through `mktemp` in `/tmp`, which this sandbox denies). Known and unrelated; not repeated. |
| Real CLI | the two scripts above | both exit 0 with every assertion held |

## Limitations and open risks

* No live gateway probe, no real-home apply, and no real credential were
  used. The mixed-provider resume check (provider definitions in the
  effective configuration) is still open and belongs to the later tickets.
* `sandbox-exec` is not permitted under the parent sandbox
  (`sandbox_apply: Operation not permitted`). The nested attempt was not
  repeated and the parent sandbox was not relaxed; the isolated run used the
  source-proven `MAGPIE_ADDR` fake routing instead. A parent run of the two
  reviewed scripts under a top-level sandbox that denies `3425` can
  re-establish the same evidence with the port denied as well.
* The pinned CLI tries to fetch its partner list from
  `https://usemagpie.ai/api/partners` when it runs. This sandbox has no
  internet, so the lookup failed (`no such host`) and the CLI continued; no
  gateway, credential, or device data was involved.
* The ordinary-connection preflight reads the base configuration for
  `model_provider = "magpie"`. That is the pinned CLI's own refusal
  condition; a refusal for any other reason (an account failover, for
  example) is caught by the pinned setter itself, which is attempted before
  the gateway changes.
* The deployment stops at the scope selection when the ordinary Codex
  integration is connected. The owner disconnects it in Magpie; the
  deployment never does.
* That ordinary-connection refusal says the ordinary integration is left as
  it is on the strength of the command order: only the read-only getter has
  run when it fires, so nothing could have changed the base files. The
  failed-setter path, where a command could have changed a file, is the one
  that now compares the hashes before it says anything about preservation.
* A recorded profile the pinned writer cannot parse fails at the write, after
  the gateway changes, and is preserved; the message says so. Detecting it
  earlier would need a TOML parser the deployment does not require.
* The suite runs on macOS; the repository's other suites assume a Linux
  x86_64 host and are out of scope here, as `AGENTS.md` states.

## Proposed commit message

```
[agents]: refuse aliased codex profile paths and select the scope early

Refuse a linked or non-directory Codex home, a linked or non-regular
profile path, and a generated file with another name before the gateway,
the backup, or the provider registration changes, so the pinned writer can
never change another file through an alias. A link count that cannot be
read fails the preflight closed instead of being read as one link. Create
a private Codex home when the device has none.

Read the Codex scope with the pinned CLI's read-only getter and select it
before the gateway changes, so the CLI's refusal while the ordinary Codex
integration is connected stops the run before any avoidable mutation; the
ordinary integration is never disconnected or retagged. A getter that
failed is a failure even when it printed an answer, and the base
configuration and authentication hashes are compared after the selection
whether the command succeeded or failed.

Cover the collisions, the private creation, the scope preflight, the
malformed profile, the failed getter, the unreadable link count, and the
scope setter that changes the base files with public apply regressions,
and update the ownership and rollback contract to the verified behaviour.
```
