# Ticket 13/14 gate results (supervisor, 2026-11-19)

The gate sequence is `ticket12-gate.md`. This file records what each step
measured on the integration branch `fix/deployment-review` after tickets 13
and 14 were merged. A skipped check is reported as skipped, never as a pass.

## 0. State under test

- Branch `fix/deployment-review`, tip `2386c99` ("compare the codex
  configuration by its content"), which merges `cb880df` (ticket 14) and
  `7b8bd31` (ticket 13).
- Working tree: the untracked `.scratch/` tracker, and
  `tests/test_worktrunk.py` with the ticket 17 fix applied but not committed
  (see the end of this file).
- Host: macOS 15.8.1, arm64, chezmoi v2.73.3, codex 0.169.0, python3 3.15.2,
  magpie app 0.1.4451 on 127.0.0.1:3425.

## 2. Deterministic checks

| check | result |
| --- | --- |
| `python3 -m unittest tests.test_magpie` on the merged state | 294 tests, 0 failures, 0 errors (699 s) |
| `python3 -m unittest discover -s tests -v` | 1129 tests, 29 failures, 14 errors, 123 skipped |
| `/bin/bash -n deployment/magpie.sh` | clean |
| `git diff --check` | clean |
| ShellCheck, shfmt | skipped: not installed on this host |

The whole-suite failures are the documented host scope: the Linux suite
asserts native-platform detection, the Windows architecture matrix, and the
Linux-only bring-up helper, and it fails by design on macOS. The
implementation module for both tickets (`tests/test_magpie.py`) passes in
full, and the macOS gate below is the platform-correct check.

One failure in the list is **not** host scope, and it was not caused by
tickets 13 or 14: `tests/test_worktrunk.py` drove the device's own
worktrunk CLI instead of its own stub, and it selected its clients through
the requested selection rather than the resolved one the step reads. The
plugin step therefore ran against the real `wt`, the recorded call list was
empty, and the test failed without exercising the step. The staleness
predates this review: at the baseline `e8de927` the test already set
`CLI_AGENTS` and `deployment/agents.sh` already used `DEPLOY_AGENTS` in
`agent_selected`. See ticket 17; the fix isolates the harness from the
device's CLI and asks for its clients the way the bootstrap asks for them.

## 3. Simulated homes

| profile | result |
| --- | --- |
| `--class t9k` | applied, exit 0 |
| `--class linux` | applied, exit 0 |

Both homes were deleted after the checks. The repository tracker
(`.scratch/`) does not land in the home: neither simulated home holds a
`.scratch` directory.

## 4. Native macOS gate

```
python3 tests/native_macos.py --arch aarch64 --role workstation \
  --agents kimi,pi,opencode,claude,codex,minimax,qoder \
  --report /private/tmp/dotfiles-native-macos-gate.json
```

Result: `native macOS aarch64 workstation: passed`. The gate excludes the
account Magpie wiring and cannot prove inference.

## 7. Protected application to the account home

The device state was recorded before the apply
(`/private/tmp/dotfiles-device-config-pre-apply.tsv`): the bytes, the SHA-256,
and the modification time of `~/.codex/config.toml`,
`~/.kimi-code/config.toml`, and `~/.kimi-code/tui.toml`.

The authorized public bootstrap ran once:

```
bash bootstrap.sh --source /Users/joey/SHELL/dotfiles --home /Users/joey \
  --agents kimi,pi,opencode,claude,codex,minimax,qoder
```

Result: exit 0, `dotfiles: applied macos-workstation to /Users/joey (copy
mode)`. The full log is `/private/tmp/dotfiles-real-apply.log`.

What the apply reported, in its own words:

```
dotfiles: magpie: the agent codex is wired to group/openai-stack
dotfiles: magpie: the client settings are wired to the gateway
dotfiles: magpie: the official DeepSeek row of every DSH profile is unchanged
dotfiles: magpie: the Codex configuration and authentication are unchanged
dotfiles: magpie: the state was recorded in /Users/joey/.local/state/dotfiles/magpie/state.tsv
```

`~/.local/state/dotfiles/magpie/state.tsv` records the verdict
`codex-guard|unchanged` and the run `applied|20261119T061505Z`. The
`prepare-shell` step ran after the Magpie step, which the earlier failed
apply never reached.

### The interrupted write from the earlier failure

The failed apply of 2026-11-19 left `codex-profile.pending` in the Magpie
state root. Its recorded fingerprints matched the files on the device
(`magpie.config.toml` `a5f18bb5…`, `magpie-models.json` `24697caa…`), so the
retry was permitted and the apply wrote them again. Nothing was adopted that
the interruption had not already written.

## 8. Live verification

The apply's own report is the live evidence the deployment produced, and it
is recorded verbatim in `/private/tmp/dotfiles-real-apply.log`:

| check | result |
| --- | --- |
| the gateway answers | `the gateway answers on http://127.0.0.1:3425` |
| the providers | chatgpt, opencode-go, kimi-code-cn, minimax-cn, openai, zed — all present |
| the codex agent | `the agent codex is wired to group/openai-stack` |
| the pi agent | `the agent pi is already wired to group/workhorse` |
| the claude agent | `the agent claude uses group/conductor` |
| the dsh agents | `the agent dsh is outside the selection and is left alone`, `the agent dsh-tui uses -` |
| the Codex configuration | `the Codex configuration and authentication are unchanged` |
| the DSH profile row | `the official DeepSeek row of every DSH profile is unchanged` |
| the state file | `the state was recorded in /Users/joey/.local/state/dotfiles/magpie/state.tsv`, with `codex-guard\|unchanged` and `applied\|20261119T061505Z` |

The apply also prepared the shell, which the failed apply never reached:
`dotfiles-shell-prepare: prepared Nushell startup` and
`dotfiles-history-prepare: prepared Nushell history`.

### What the live verification could not measure

From 14:17, after the apply finished, every command that needed Claude Code's
safety classifier failed with `codex/gpt-6.1-terra is temporarily unavailable
(timed out)`. The classifier's traffic goes to the local gateway
(`ANTHROPIC_BASE_URL=http://127.0.0.1:3425`) on the codex provider
(`CLAUDE_CODE_AUTO_MODE_MODEL=codex/gpt-6.1-terra`), while the session's own
route (`minimax-cn/MiniMax-M3.1-Flash`) kept answering and the gateway kept
serving the apply. The read-only fast path kept working, so the repository
was still inspectable, but the commands below could not be run. See ticket 16.

The commands that are still outstanding, for an operator with a working
shell:

```bash
# 1. the worktrunk plugin test, after the stale-selection fix
python3 -m unittest tests.test_worktrunk -v

# 2. the device configuration after the apply, against the pre-apply snapshot
bash /private/tmp/dotfiles-device-config-state.sh
diff /private/tmp/dotfiles-device-config-pre-apply.tsv \
     <(bash /private/tmp/dotfiles-device-config-state.sh)

# 3. the merge against the device's own file, in a throwaway home
bash /private/tmp/dotfiles-device-merge-check.sh

# 4. the live state: versions, managed commands, the Magpie profile, the gateway
bash /private/tmp/dotfiles-live-verify.sh

# 5. the gateway's own model list
curl -s http://127.0.0.1:3425/v1/models | jq -r '.data[].id'

# 6. the provider-preserving resume, with the synthetic runtime check only
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
```

The merge check was prepared before the outage and is the one measurement
that is still missing for ticket 14 on the real device: it copies the
device's own `~/.codex/config.toml` into a throwaway home, runs the public
merge seam there, and compares the bytes and the modification time. The
script did not reach the disk before the outage, so it is here:

```bash
#!/usr/bin/env bash
# Supervisor-side check on the real device: the client-settings merge must not
# rewrite a device configuration it does not change.
set -uo pipefail
repo=/Users/joey/SHELL/dotfiles
device=${DEVICE_CODEX_CONFIG:-$HOME/.codex/config.toml}
sim=$(mktemp -d /tmp/dotfiles-device-merge.XXXXXX)
trap 'rm -rf "$sim"' EXIT
mkdir -p "$sim/.codex" "$sim/.config/chezmoi" "$sim/.local/state" "$sim/.cache/tmp"
cp -p "$device" "$sim/.codex/config.toml"
printf '[data]\n    platform = "macos"\n    role = "workstation"\n    arch = "aarch64"\n    kimiApiKey = "REPLACE_ME"\n' \
    > "$sim/.config/chezmoi/chezmoi.toml"
before=$(shasum -a 256 "$sim/.codex/config.toml" | awk '{print $1}')
mtime_before=$(stat -f '%m' "$sim/.codex/config.toml")
cat > "$sim/merge.sh" <<EOF
export HOME=$sim
export DEPLOY_SOURCE=$repo
export DEPLOY_HOME=\$HOME
export DEPLOY_CHEZMOI=\$(command -v chezmoi)
export XDG_CONFIG_HOME=\$HOME/.config
export XDG_STATE_HOME=\$HOME/.local/state
export TMPDIR=\$HOME/.cache/tmp
fail() { printf 'dotfiles: %s\\n' "\$*" >&2; exit 1; }
source "\$DEPLOY_SOURCE/deployment/payload.sh"
source "\$DEPLOY_SOURCE/deployment/client-settings.sh"
deploy_client_settings 0 0 codex
EOF
bash "$sim/merge.sh" > "$sim/merge.log" 2>&1 && echo 'merge: exit 0' || { echo 'merge: FAILED'; tail -5 "$sim/merge.log"; }
after=$(shasum -a 256 "$sim/.codex/config.toml" | awk '{print $1}')
mtime_after=$(stat -f '%m' "$sim/.codex/config.toml")
printf 'sha256 before %s\nsha256 after  %s\nmtime before  %s\nmtime after   %s\n' \
    "$before" "$after" "$mtime_before" "$mtime_after"
if [ "$before" = "$after" ] && [ "$mtime_before" = "$mtime_after" ]; then
    echo 'result: the merge wrote nothing; the device bytes and the modification time survive'
else
    echo 'result: the merge REWROTE the device configuration'
fi
```

## 9. Cleanup

Both implementer worktrees are merged into `fix/deployment-review`:

| worktree | branch | commit |
| --- | --- | --- |
| `~/SHELL/dotfiles.fix-codex-content-guard` | `fix/codex-content-guard` | `7b8bd31` |
| `~/SHELL/dotfiles.fix-client-settings-toml-bytes` | `fix/client-settings-toml-bytes` | `cb880df` |

The archive tags and the worktree removal are the remaining cleanup step and
need the same shell access:

```bash
git tag archive/fix-codex-content-guard fix/codex-content-guard
git tag archive/fix-client-settings-toml-bytes fix/client-settings-toml-bytes
git rev-parse archive/fix-codex-content-guard archive/fix-client-settings-toml-bytes
git worktree remove /Users/joey/SHELL/dotfiles.fix-codex-content-guard
git worktree remove /Users/joey/SHELL/dotfiles.fix-client-settings-toml-bytes
git branch -d fix/codex-content-guard fix/client-settings-toml-bytes
```

Both worktrees are clean: `git ls-files -m` reports no modified tracked file
in the integration branch, and each worktree holds only the changes its
commit already carries. Nothing is pushed.

The first attempt at this cleanup failed: it derived the branch name from the
worktree name, so it looked for `fix/fix-codex-content-guard`, a branch that
does not exist. `git tag` then failed silently and the script left both
worktrees alone. The loop in `.scratch/deployment-review-2026-11-17/finish.sh`
now iterates the real branch names and derives the worktree path and the
tag name from them.

### The working tree right now

`tests/test_worktrunk.py` carries the ticket 17 fix, applied but **not
committed**: staging and committing need the same classifier route that was
down. The commit and the re-run are owed:

```bash
git add tests/test_worktrunk.py
git commit -F - <<'EOF'
[agents]: isolate the worktrunk plugin test from the device's own CLI

The plugin step resolves wt from the managed tool directory before the Pixi
one, so the ambient DOTFILES_COMMON_BIN pointed the test at the device's
real worktrunk. The stub that records the calls never ran, and the test
failed without exercising the step.

The harness now points DOTFILES_COMMON_BIN at the stub directory and asks
for its clients the way the bootstrap asks for them, through the requested
selection that resolve_agent_selection turns into the resolved one.

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
python3 -m unittest tests.test_worktrunk -v
```

### The one script that runs everything still owed

`.scratch/deployment-review-2026-11-17/commit-and-cleanup.sh` runs every
outstanding measurement in one pass, in this order:

| step | what it measures |
| --- | --- |
| 1 | the worktrunk plugin test, and the commit that depends on it |
| 1b | the classifier-route change (ticket 20), its suite, and its commit |
| 2 | the device configuration against the pre-apply snapshot |
| 3 | the merge against the device configuration |
| 4 | the live state, with the corrected agent command names |
| 5 | the gateway's model list, with and without the credential |
| 6 | the gateway's own answer for the groups, under both spellings |
| 6b | the authorized apply, so the device takes the new classifier route |
| 6c | the gateway again, after the apply |
| 7 | the provider-preserving resume, synthetic runtime only |
| 8 | the archive tags and the worktree removal |
| 9 | the final state |

Steps 5 and 6 are the ones that decide tickets 21, 22, and 20. Step 5 asks
the gateway the same question twice — once without a credential and once
with the deployment's own — because the recording that found the finding
used a bare `curl`, and if the gateway scopes its published list by
credential the finding is about the recording rather than about the groups.
It must capture the list whole, not filtered to `group/` ids, because the
`auto/` ids are the ones under test. Step 6 reads the `listed` field of the
four groups the gateway holds, and then asks for the same four names under
the gateway's own slash spelling: if a group and a family answer with the
same members, they are one object, and the ids collide.

Step 1b is the ticket 20 change: the suite that covers it runs first, and
the commit follows only when the suite is green. Step 6b is the authorized
public bootstrap, the same command the gate ran, so the device's Claude Code
settings take the new classifier route through the merge — the only writer
of that file — rather than through a hand edit. Step 6c reads the gateway
again afterwards, which is what says whether the apply publishes the three
groups ticket 21 is about: if it does, the cause is the member-only
comparison; if it does not, the correspondence ticket 22 records is the
cause.

Two scratch scripts the earlier steps need were materialized from this
record: `live-verify.sh` (the agent command names corrected to the
catalog's `mcode`) and `merge-check.sh` (the merge seam check that was
only inline here).

Nothing is pushed by that script, and it leaves a worktree alone when it
holds uncommitted content or when its branch is not merged.

## 10. Findings from the live verification that are not yet fixed

These came out of the live run on 2026-11-19 and are recorded as tickets.
None of them is a regression of tickets 13 or 14.

| finding | ticket | state |
| --- | --- | --- |
| the Codex profile's `model` key drifted after the apply, and the status reports it | 18 | needs-diagnosis |
| the catalog names three `luna` models the gateway retired | 15 | needs-info; the gateway's model list is now recorded |
| the gateway still holds a group whose members it no longer serves | 19 | needs-diagnosis; blocked by 15 |
| the gateway holds three groups it does not publish as models | 21 | needs-diagnosis |
| the classifier and the auxiliary aliases are pinned to one provider's route | 20 | decided 2026-11-20; the route is the gateway's Terra family; the change is in the working tree |
| the docs and the catalog spell the same four routing sets two ways | 22 | needs-diagnosis; a second candidate cause for 21 |

One line in the earlier live report needs correcting: `minimax absent` was
the supervisor's own verification script asking for `command -v minimax`,
but the agent catalog exposes that agent as `mcode`
(`deployment/agents/providers.tsv`). The line said nothing about the
deployment. The script now asks for `mcode`.

### Ticket 21 came out of the same model list

The gateway's `/v1/models` serves five group ids:

```
group/auto-gpt-6-astra
group/chatgpt
group/conductor
group/openai-stack
group/workhorse
```

and not `group/auto-gpt-6-1-sol`, `group/auto-gpt-6-1-terra`, or
`group/auto-gpt-6-luna`, although `magpie group <id>` answers for all three
with their members. A group the picker offers must be a model id the
gateway serves; these three are offered by `visible.tsv` and `picked.tsv`
for every agent.

The source shows why the deployment cannot notice. The apply's group loop
compares **only the member list** (`deployment/magpie.sh`, the
`magpie-apply.groups` step), while the write it issues carries four fields:

```bash
magpie_run group set "$group" "models=$desired" "routing=$routing" "stays=$stays" "listed=$listed"
```

`routing`, `stays`, and `listed` travel with the write and nothing reads
them back, so a group whose members already match is never rewritten and
its `listed` value is never corrected. `docs/MAGPIE.md` records that
`listed=no` also removes the models the group names from `/v1/models`.

The hypothesis is that the three unpublished groups carry a stale `listed`
and the one published group whose membership the last apply rewrote
(`auto-gpt-6-astra` — the catalog's optional `codex/gpt-6-astra?`
candidate beside `codex/gpt-6.2-astra` is the shape a catalog takes when
the newer model replaced the older one) got `listed=yes` with the write.
The gateway's own answer decides it; the measurement is one read of
`magpie group auto-gpt-6-1-sol`.

### Ticket 19's status half is proved by the source

`magpie_status` builds its `known` list from `magpie_catalog_model_ids` —
the **catalog's** model ids, not the gateway's live ones — and never calls
`magpie_models_fetch`. It compares the gateway's group membership against
the repository's intent, so a member the gateway does not serve is a
catalog member too and nothing looks wrong. The apply gets this right
already: it fetches `/v1/models` first and resolves the roles against the
live list, which is how it reported `auto-gpt-6-luna` as incomplete.

The same area carries a dead parameter. `magpie_group_models` is called as
`magpie_group_models "$output" "$known"` in both the apply and the status,
and its own comment says the report "is read by looking for them" — but the
function body uses only `$1`, so the known-model filter it was meant to
apply is missing.

### The docs and the catalog spell the same four routing sets two ways

Reading `docs/MAGPIE.md` against `deployment/magpie/groups.tsv` on 2026-11-20
found a second candidate cause for ticket 21. The docs describe the four GPT
auto families with slash ids — `auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`,
`auto/gpt-6-luna`, `auto/gpt-6-astra` — and the catalog declares four groups
with dash ids — `auto-gpt-6-1-sol`, `auto-gpt-6-1-terra`, `auto-gpt-6-luna`,
`auto-gpt-6-astra`. Resolving the catalog's roles through `models.tsv`
reproduces the doc's description member for member and effort for effort,
including the astra row's optional `codex/gpt-6-astra?` candidate, which is
the doc's "falls back to its older GPT-6 Astra".

Neither spelling exists in the other file: `git grep "auto-gpt-6" -- docs/`
returns nothing, and `git grep "auto/" -- deployment/magpie/` returns nothing.
The divergence has been there since the catalog was introduced — at commit
`8d78073`, the first commit whose `groups.tsv` carries these four rows, the
catalog already read `auto-gpt-6-1-sol` and the document already read
`auto/gpt-6.1-sol`.

Read a slash and a dot as dashes and all four correspond without exception,
so the two files describe one set of four routing sets under two spellings
of the same names. The doc's ids are character-for-character the family ids
the gateway serves for three of the four — `auto/gpt-6.1-sol`,
`auto/gpt-6.1-terra`, `auto/gpt-6-luna` — while the fourth is named
`auto/gpt-6-astra` where the gateway serves `auto/gpt-6.2-astra`. That
contradicts the doc's own sentence that the ids "remain stable when a
provider moves to a newer model", so one of the two records is wrong.

The correlation with ticket 21 is exact. Three of the four deployment
groups flatten onto a family id the gateway serves, and those three are
exactly the three that are not published; the fourth flattens onto
`auto/gpt-6-astra`, which the gateway does not serve, and it is published.
It is a correlation and not a mechanism: a published group is `group/<id>`
and a native family is `auto/<model>`, so the two are in different
namespaces and no literal id collision is possible. The tracker records no
mechanism the source does not support, and step 6 of the operator script now
asks the gateway for both spellings of each name, which distinguishes the
readings outright — `magpie group` reads a group, so an answer for the
slash form means the doc's ids are the gateway's own.

### The classifier route is pinned to one provider

`deployment/client-settings/claude-settings.json.tmpl` pins
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`, and
`CLAUDE_CODE_AUTO_MODE_MODEL` to `codex/gpt-6.1-terra`, the ChatGPT-plan
provider, mirrored by `MAGPIE_CLAUDE_AUX_MODEL` in `deployment/magpie.sh`.
The catalog already has the group that would fix it —
`auto-gpt-6-1-terra|chatgpt.terra:high,openai.terra:high|drain|auto|yes` —
but the gateway does not publish that group id, so the fix cannot be the
group until ticket 21 explains why. The gateway does serve its own
`auto/gpt-6.1-terra` id, which is not in any deployment catalog row.

## 11. The classifier outage is still in effect

Every command that needs Claude Code's safety classifier failed from 14:17
on 2026-11-19 through the end of this session, with the same message:

```
codex/gpt-6.1-terra is temporarily unavailable (timed out), so auto mode
cannot determine the safety of Bash right now.
```

The pattern is not random. Commands on the read-only fast path
(`git rev-parse --short HEAD`, `echo`) succeed; every command that needs the
classifier fails. The `Edit` and `Write` tools fail the same way, while
`Read` does not.

The classifier's route is `codex/gpt-6.1-terra` through the gateway
(`ANTHROPIC_BASE_URL=http://127.0.0.1:3425`), on the codex provider, which
is the ChatGPT account. Ticket 16 records the finding; the account's
remaining quota is still unmeasured, because the tool that would measure it
is the tool the outage blocks.

This is why the test run, the commit, and the cleanup are still owed rather
than finished.

### The outage continued into 2026-11-20, and the route was decided

The outage was still in effect on 2026-11-20, in the same shape: `Read` and
an edit inside the repository were allowed, and every command with a side
effect — `Bash`, `Write`, an edit outside the repository, a background shell
— was denied with the same message. What the outage did *not* stop is the
supervisor's own reading and editing, so the ticket 20 change was made in the
working tree while the shell was unavailable:

| file | change |
| --- | --- |
| `deployment/client-settings/claude-settings.json.tmpl` | the three auxiliary and classifier values |
| `deployment/magpie.sh` | `MAGPIE_CLAUDE_AUX_MODEL` and its comment |
| `docs/AGENT_SETTINGS.md`, `docs/MAGPIE.md` | the route the documents name |
| `tests/test_magpie.py`, `tests/test_magpie_auxiliary_models.py` | the expectations that name it |

The operator decided the route: `auto/gpt-6.1-terra`, the gateway's own
Terra family, which routes Codex first and then OpenAI. It is a served model
id today — Claude Code's gateway discovery listed it in the device's
capability list — and a direct `openai/gpt-6.1-terra` was the alternative,
which answers today but keeps the single-account defect in a new place.

Nothing is committed and nothing is applied yet. The operator script runs the
suite for the change, commits it when the suite is green, and then runs the
authorized apply so the device's settings take the route through the merge.


## 12. The operator script ran on 2026-11-20 (supervisor)

The script in §9 ran to the end, in this session, with the classifier outage
still in effect for the Claude Code session that wrote it. The log is
`/private/tmp/dotfiles-commit-and-cleanup.log`; the apply's own log is
`/private/tmp/dotfiles-real-apply-2026-11-20.log`.

| step | result |
| --- | --- |
| 1 | the worktrunk test: 6 tests, OK. Committed as `7ce7b90` |
| 1b | the classifier suite: 299 tests, OK, 564 s. Committed as `1c2e309` |
| 2 | skipped by the script — the snapshot helper is not executable |
| 3 | skipped by the script — the merge check is not executable |
| 4 | the live state: versions, the managed commands, the profile, the gateway |
| 5 | the published model list, with and without the credential: the same list |
| 6 | the four groups under both spellings: the answers that decide tickets 20, 21 and 22 |
| 6b | the authorized apply: exit 0. The device carries `auto/gpt-6.1-terra` for the three auxiliary and classifier keys |
| 6c | the gateway after the apply: the same published list as in step 5 |
| 7 | the provider-preserving resume: 50 tests, OK |
| 8 | the archive tags resolve; the worktree removal needed the `__pycache__` files inventoried first |
| 9 | the final state: two commits, one worktree, no push |

Steps 2 and 3 were skipped by the script's executable-bit checks, not by a
failure. Both were run by hand afterwards and both pass:

- the device configuration against the pre-apply snapshot differs in one
  file, `~/.codex/config.toml`, and the difference predates this apply: the
  apply's own backup of that file (11:10:31) is byte-identical to the file
  on disk now, so the apply did not change it;
- the merge seam check: `merge: exit 0`, the same sha256 and the same
  modification time before and after, so the client-settings merge writes
  nothing to the device's Codex configuration.

The worktree cleanup needed one step the script did not take: both worktrees
held only ignored `__pycache__` bytecode, and the script's inventory treats
ignored files as content, so it left both alone. The bytecode was removed,
the worktrees were removed without `--force`, and both branches were deleted;
their archive tags (`archive/fix-codex-content-guard`,
`archive/fix-client-settings-toml-bytes`) resolve.

### The measurement that decides tickets 20, 21 and 22

The gateway answers the deployment's own group ids with the *family's* id:

| asked for | answered with | published as |
| --- | --- | --- |
| `auto-gpt-6-1-sol` | `auto/gpt-6.1-sol` | `auto/gpt-6.1-sol` |
| `auto-gpt-6-1-terra` | `auto/gpt-6.1-terra` | `auto/gpt-6.1-terra` |
| `auto-gpt-6-luna` | `auto/gpt-6-luna` | `auto/gpt-6-luna` |
| `auto-gpt-6-astra` | `group/auto-gpt-6-astra` | `group/auto-gpt-6-astra` |

The published list is identical before and after the apply, so the apply is
not what publishes or withholds a group. `listed` is not the cause either:
the gateway's answer carries `routing` and `stays` but no `listed` field,
and the catalog's `listed=yes` was already in force. The three groups the
deployment declares as `auto-gpt-6-1-sol`, `auto-gpt-6-1-terra` and
`auto-gpt-6-luna` are the gateway's own families, served under the family's
id, and `group/<deployment id>` is never a model id of its own. The astra
group escapes because the gateway's astra family is version-stamped
(`auto/gpt-6.2-astra`).

### The allowance, measured after the apply

The route change is applied, and the route is still dark today, for a reason
the route cannot fix:

```
magpie accounts
● codex   xuzy1992.joey@gmail.com  · prolite 7d 100% ↻19h56m tomorrow 07:12
● zed     JoJoTsui                 · Student
```

An OpenAI request answers "You have no credits remaining". Both members of
the Terra family are exhausted, so the family cannot answer — but a drain
group does fall through an exhausted member: `group/conductor`
(codex → openai → kimi-code-cn/k3.1-pro) and `group/openai-stack` both
answered, through Kimi. So the family is the right route and it will answer
as soon as one of its two providers can; a new Claude Code session is denied
every checked action until then, because the classifier's route is dark, not
because it is pinned to one provider.

The routes that answer right now are `group/conductor`, `group/workhorse`,
`kimi-code-cn/k3.1-pro` and `minimax-cn/MiniMax-M3.1-Flash`.

## 13. The classifier route moved to the workhorse group (2026-11-20)

The Terra family behind the route could not answer: the ChatGPT-plan account
is spent until 2026-11-21 07:12 UTC+8 and OpenAI has no credits, so both
members of `auto/gpt-6.1-terra` were exhausted. The operator moved the
classifier and the two background aliases to `group/workhorse`, the cheap
group over two providers that answers today.

Committed as `4246c6a`; the suite is green (299 tests, 0 failures). The
authorized apply exited 0, and the device's Claude Code settings carry
`group/workhorse` for `ANTHROPIC_DEFAULT_HAIKU_MODEL`,
`ANTHROPIC_SMALL_FAST_MODEL` and `CLAUDE_CODE_AUTO_MODE_MODEL`, with
`magpie ls` reporting the same three values.

The route is verified end to end: a fresh Claude Code session ran a Bash
command and got its output (`classifier-ok`), and the review tab's agent,
restarted onto the new settings, ran one too (`review-tab-ok`). The outage
is over for new sessions. The old session's transcript is intact and can be
resumed with `claude --resume 03a0f81b-8524-49b8-84e0-f654d579e647`.

## 14. The macOS gates re-run against the final source (2026-11-20)

- The fresh native installation gate passed at commit `162327d`: seven checks
  (native runtime and architecture, profile detection, default installation 1,
  default installation 2, pinned commands and pending history, ordinary native
  configuration discovery, native shell, instruction, CodeGraph and
  encrypted-history behavior), 1230 s, an empty cache, a clean working tree,
  and the four behavior suites at 13, 18, 9 and 9 tests with no skips. The
  report is `/private/tmp/dotfiles-native-macos-2026-11-20.json`.
- Both simulated applies passed against the same source: `--class t9k`
  (linux-remote-compute) and `--class linux` (linux-workstation), each with
  `DOTFILES_CHEZMOI_BIN` set to the host's chezmoi. Without it the legacy
  profile installs its Linux binary, which cannot execute on this Mac — a
  host-scope mismatch in the invocation, not a deployment defect. Both
  simulated homes rendered the shell files as regular files and passed the
  standalone Nushell check (`nu --config … -c 'print "ok"'` → `ok`), and both
  were removed afterwards.
- The Bun global copy of the pi package, left by an unsuccessful
  `bun add -g`, is gone: `bun remove -g @earendil-works/pi-coding-agent`.
  The managed launcher still resolves `pi` to the frozen project's 1.5.2.
  Two global copies remain and are reported, not removed: the claude-code
  copy at 2.1.326 and the minimax code copy at 0.6.12, the latter being the
  only provider of `mcode-tools`.

## 15. The routing ownership, the findings, and the allowance (2026-11-20)

Committed as `a1a0873`. The suite is green (309 tests in the Magpie
modules, 52 in the isolation modules). The authorized apply exited 0, and the
device's status is green.

- The three groups the gateway owns are retired from the catalog and offered
  under the ids it publishes. The device's picked list now carries
  `auto/gpt-6.1-sol`, `auto/gpt-6.1-terra` and `auto/gpt-6-luna` instead of
  the `group/auto-gpt-6-1-*` ids the gateway never served.
- The apply compares a group's routing and stays as well as its member order,
  so a drifted group is repaired instead of reported as healthy.
- The status reports a group the gateway does not publish, a group that holds
  an unserved member, and a route the deployment offers under an unpublished
  id as findings, and fails on them. On this device: five groups published,
  three routes published, no finding.
- The apply measures the ChatGPT allowance before it wires a group that
  drains the account, and the status reports it:
  `allowance|chatgpt|none left|resets 2026-11-21T07:12:37+08:00`.

## 16. The headless Linux gate (2026-11-20)

OrbStack 29.8.2 runs the pinned source in read-only amd64 containers for
Ubuntu 20.04 and 24.04, four CPUs and eight GiB each. The gate's artifacts
are under `/private/tmp/dotfiles-linux-gate-2026-11-20*`.

- The first run failed on a stale check: the gate asserted that a fresh
  home's Claude Code settings carry a placeholder credential, an expectation
  from the GLM-era template. The deployment migrated to Magpie, where the
  client credentials live in the gateway's own store, so the check read a
  file that no longer holds one. It now reads the file that carries the
  placeholder and asserts that the Claude Code settings carry no credential
  while the gateway is absent (`e6ff25e`).
- The second run passed the bootstrap, the managed files and installed pins,
  and the fetched skill discovery on both releases, and failed the
  reapplication check on both: it reports one changed managed file,
  `.config/git/ignore`. The deployment's state does not show the change: on
  the retained homes a further reapplication leaves the file's content and
  mode unchanged and leaves `chezmoi managed` listing the same seventy files,
  and the gate's own snapshot function around a reapplication reports no
  change. The cause is not established; the run is recorded as a failure.
- The native Windows gate stays unavailable on this host: there is no
  Windows runtime and no PowerShell.
