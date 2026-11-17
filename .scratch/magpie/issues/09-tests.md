# 09: Hermetic Magpie tests and simulated-home apply

**What to build:** Finish `tests/test_magpie.py` with a fake `magpie` binary on PATH and a fake `$HOME`:

- A recorder that appends every argv and serves canned `status --json`, `accounts codex --json`, `provider <id>`, `group <id>`, `settings get proxy`, and `/v1/models`.
- Apply-order assertion: proxy → providers (catalog order) → model resolution → groups → `magpie pi` → `magpie dsh` → state.
- Forbidden-command assertion: no `codex`, no `claude`, no `accounts add`, no `accounts import`.
- Missing required credential aborts; missing optional provider warns.
- Missing required model fails with the live list; a `?` candidate is skipped.
- Second apply writes nothing (state mtime and file list unchanged).
- Codex config changed mid-apply aborts and keeps the backup.
- Non-macOS apply reports the skip; `--apply-only`/`--agents-only` skip.
- Backups are 0600 and pruned to ten.

Update `tests/test_agents.py`, `tests/test_agent_catalog.py`, `tests/test_common_providers.py`, `tests/test_deployment.py`, and `tests/test_proxy.py` where the new action, agent rows, or plan field change their expectations.

**Blocked by:** 02, 03, 04, 05, 06, 07, 08.

**Status:** done

- [x] `python3 -m unittest tests.test_magpie -v` passes without network or a real Magpie.
- [x] The existing suites pass on macOS, or the known host-scope failures are named in the ticket comment.
- [x] No test reads the real `~/.config/magpie`, `~/.codex` or `~/.dsh`.
- [x] A simulated-home apply creates only files under the simulated home.

## Comments

`tests/test_magpie.py` is hermetic. The fake `magpie` is a Python script that
records every argv and serves the canned answers the apply expects: the
gateway status, the Codex accounts, the provider and group lookups, the proxy,
and the group reports. The gateway itself is a loopback HTTP server in the
test process that serves `/v1/models`. Every test runs against a temporary
home, so no test reads the real `~/.config/magpie`, `~/.codex`, or `~/.dsh`.

The suite covers the order the apply promises (proxy, providers in catalog
order, model resolution, groups, `magpie pi`, `magpie dsh`, state), the
forbidden commands, a missing required credential with the variable named, a
missing optional provider that only warns, a required model with no live match
that fails with the model list, an optional candidate that is reported and
skipped, a second apply that writes nothing and keeps every modification
time, a Codex change that aborts the apply and keeps the backup, the DSH
profile that stays byte-identical, the official DeepSeek row that fails the
apply when it changes, an apply on another platform that reports the skip, an
apply without a gateway that reports the skip, the backups at 0600 pruned to
ten, and the proxy resolution for a local and for a remote endpoint.

The other suites moved with the work: `tests/test_agents.py` names the two new
agents in the plan and drives a simulated install that produces the `dsh`,
`dsh-tui`, and `dst` launchers; `tests/test_agent_catalog.py` covers the two
new records and their absent Herdr kind; `tests/test_common_providers.py`
covers the `pnpm` row; `tests/test_version_updates.py` counts the new Bun
projects; `tests/test_deployment.py` reads the gateway values in the rendered
Claude settings; `tests/test_agent_payload.py` and
`tests/test_windows_deployment.py` expect the gateway token. The proxy suite
needed no change: the new `magpie-apply` section has its policy row.

The full suite on this macOS host:

- `DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest discover -s tests -v`
  — 669 tests, 28 failures and 14 errors. Every one of them is a host-scope
  failure on macOS: the local-history, legacy-shell, legacy-history, and
  host-up suites expect GNU `stat` and a Linux daemon stack, the agent
  integration suite expects GNU `stat`, the worktrunk plugin suite and the
  Windows and simulated-home checks in `test_deployment.py` fail the same way
  on `main`, and `test_macos.py` fails its Windows cell.
- The same run on `main` in a worktree of this repository ran 596 tests and
  produced the same 42 failures and errors. The branch adds 73 tests and no
  new failure: the five that the new agents and the gateway moved were fixed
  in `tests/test_version_updates.py` and `tests/test_deployment.py`, and one
  worktrunk test flaps between an error and a failure on both branches.
- `python3 -m unittest test_magpie -v` — 70 tests, all pass, without network
  access and without a real Magpie.
- The simulated-home applies from `AGENTS.md` (`--class t9k --apply-only` and
  `--class linux --apply-only`) succeed and print the skip reason; a
  simulated macOS apply places the engine, the catalogs, and the two
  commands under the simulated home only.
