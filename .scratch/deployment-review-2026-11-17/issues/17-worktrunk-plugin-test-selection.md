# 17: The Worktrunk plugin test selected its clients with a stale variable

Status: ready-for-agent — closed on 2026-11-20, the test is green and the fix
is committed as `7ce7b90`
Blocked by: none — found while classifying the whole-suite failures of
2026-11-19

**What to build:** the test that proves the Worktrunk plugin is installed for
the selected clients must select them the way the deployment does.

- [x] `tests/test_worktrunk.py`: the harness sets the resolved selection the
      step reads, so the plugin install runs for the selected clients and the
      assertion sees the calls.

## The defect

`install_worktrunk_plugins` (`deployment/agents.sh`) installs the plugin for
every client the deployment selected:

```bash
for client in claude codex opencode pi; do
    agent_selected "$client" || continue
    ...
```

`agent_selected` reads `DEPLOY_AGENTS`, the *resolved* selection.
`resolve_agent_selection` fills it from `CLI_AGENTS`, the *requested*
selection, and only when it runs.

The test called the step directly and set only the requested selection:

```
CLI_AGENTS='claude,pi'
CLI_AGENTS_SET=true
```

so `DEPLOY_AGENTS` stayed empty, no client was selected, no plugin was
installed, and the recorded call list was empty:

```
Second list contains 2 additional elements.
First extra element 0:
'config plugins claude install --yes'

- []
+ ['config plugins claude install --yes', 'config plugins pi install --yes']
```

The test failed, and it failed for the wrong reason: it never exercised the
plugin step at all. A test that passes vacuously is worse than a test that
fails loudly.

## It predates this review's changes

At the review baseline `e8de927`, `deployment/agents.sh` already used
`DEPLOY_AGENTS` in `agent_selected` and `tests/test_worktrunk.py` already set
only `CLI_AGENTS`. The staleness came with the split between the requested
and the resolved selection, not with tickets 13 or 14.

## The fix

Two things were wrong, and the first one masked the second.

**The harness drove the device's own CLI.** `install_worktrunk_plugins`
resolves the binary in this order:

```bash
local wt="${DOTFILES_COMMON_BIN:-$PIXI_HOME/bin}/wt" client
[ -x "$wt" ] || wt="$PIXI_HOME/bin/wt"
```

The managed tool directory wins over the Pixi one. On this host
`DOTFILES_COMMON_BIN` is `~/.local/bin`, whose `wt` execs the real
`/opt/homebrew/bin/wt`, so the harness ran the device's worktrunk and the
stub that records the calls never ran at all. The harness now exports
`DOTFILES_COMMON_BIN` at the stub directory, so the step under test is the
stub.

**The selection was stale.** `agent_selected` reads `DEPLOY_AGENTS`, the
*resolved* selection, and `resolve_agent_selection` fills it from
`CLI_AGENTS`, the *requested* selection, when it runs. The harness set the
requested selection only, so `DEPLOY_AGENTS` stayed empty and no client was
selected. The harness now asks for its clients the way the bootstrap asks
for them, through `CLI_AGENTS` with `CLI_AGENTS_SET=true`, and lets the
sourcing of `deployment/agents.sh` resolve it.

Setting `DEPLOY_AGENTS` directly, the way `tests/test_magpie.py` does,
cannot work here: `deployment/agents.sh` overwrites it at source time, when
`resolve_agent_selection` runs. The first attempt at this fix did exactly
that and the test still failed.

The other two tests in the file — the one that proves a missing client is not
installed, and the one that proves a failing install ends the deployment —
depend on the same selection and are fixed by the same change.

## State (2026-11-19)

The change is applied in the working tree of `fix/deployment-review` and is
**not committed**: from 14:17 on 2026-11-19 every command that needed Claude
Code's safety classifier failed with `codex/gpt-6.1-terra is temporarily
unavailable (timed out)`, and the commit, the test run, and the stage all
need one. See ticket 16.

What the trace establishes without a run:

| test | selection | expected calls | after the fix |
| --- | --- | --- | --- |
| `test_selected_clients_receive_their_plugin` | claude, pi | `config plugins claude install --yes`, `config plugins pi install --yes` | the step loops `claude codex opencode pi` and skips the unselected ones: claude, then pi |
| `test_missing_clients_are_not_installed` | codex, opencode | `config plugins codex install --yes`, `config plugins opencode install --yes` | codex, then opencode |
| `test_a_failing_plugin_install_ends_the_deployment` | claude, pi | three attempts, then the deployment ends | `agent_retry` makes three attempts of the first client |

The re-run is still owed:
`python3 -m unittest tests.test_worktrunk -v`.

## Comments

- 2026-11-20: The re-run happened. `python3 -m unittest tests.test_worktrunk -v`
  — 6 tests, OK, 7.9 s. The harness now points `DOTFILES_COMMON_BIN` at the
  stub directory, so the step resolves `wt` from the stub and never from the
  device's own CLI, and it asks for the clients the way the bootstrap asks
  for them. Committed as `7ce7b90` on `fix/deployment-review`.
