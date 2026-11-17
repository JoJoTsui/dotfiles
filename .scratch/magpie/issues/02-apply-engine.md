# 02: Magpie apply engine

**What to build:** `deployment/magpie.sh` with the apply path from the spec: backups, Codex guard, gateway readiness, proxy, provider ensure, model resolution, group ensure, agent wiring, and state write. It is sourced by `deployment/installers.sh` and callable directly. Every external `magpie` call goes through a single `magpie_run` helper that honours `MAGPIE_BIN` so tests can substitute a fake binary.

Required behaviour:
- Snapshot and guard `~/.codex/config.toml` with SHA-256; abort on change.
- Back up Claude, Pi, DSH and Codex files at 0600 under `~/.local/state/dotfiles/magpie/backups/<UTC>/`, keeping ten.
- Resolve the proxy from `proxyUrl`, else `with-proxy --print-url`, and write it with `magpie settings set proxy` only when different.
- Ensure the four providers; a missing credential names the source and variable, and is fatal only when the provider backs an enabled group.
- Resolve each model role against `/v1/models`; required role with no match fails with the live list; `?` candidates are reported and skipped.
- Create or update groups with `drain`/`auto`, and `listed=no` for `chatgpt`.
- Wire `pi` and `dsh`; never call `magpie claude`, `magpie codex`, `magpie accounts add` or `magpie accounts import`.
- Open the app only on the real account home (`installer_real_account_home`) and only when `magpie status --json` says nothing is running.
- Write `~/.local/state/dotfiles/magpie/state.tsv` atomically.
- A second run with nothing to change writes nothing and leaves mtimes alone.

**Blocked by:** 01.

**Status:** done

- [x] `bash -n deployment/magpie.sh` passes; shellcheck-clean where the repo's other deployment scripts are.
- [x] Each step prints a `dotfiles: magpie: …` line and sets a `DEPLOY_STEP` label.
- [x] `MAGPIE_BIN` substitution is used by every magpie invocation.
- [x] No command writes `~/.codex/config.toml`, `~/.claude/settings.json`, `~/.pi/agent/settings.json` or `~/.dsh/profiles/*` directly.
- [x] Unit tests with a fake `magpie` cover order, failure, idempotence and the Codex abort.

## Comments

`deployment/magpie.sh` now holds the whole engine and is sourced by
`deployment/installers.sh`. Sourcing it declares functions only. Every
external call goes through `magpie_run`, which honours `MAGPIE_BIN`, so the
tests drive a fake CLI that records its argv.

The apply runs in the spec's order: catalogs, gateway, proxy, providers, model
resolution, groups, wiring, Codex guard, state. The gateway address comes from
`magpie status --json`; the app is opened only on the real account home, and
only when nothing answers. The proxy comes from the template's `proxyUrl`,
then from `with-proxy --print-url`, and it is written only when it differs
from `magpie settings get proxy`.

A credential is read from the store the catalog names and never reaches a log:
an `env:` source is parsed out of `~/.config/dotfiles/magpie.env` without
sourcing the file, a `json:` source is read by a dotted key path, and a
`codex-account` source is satisfied by `magpie accounts codex --json`. The
apply never runs `accounts add` or `accounts import`. A missing required
credential names its source and its variable, and it fails the run only when
the provider backs a group an enabled agent uses; the other groups are still
built and the missing member is reported.

A model role resolves against `GET /v1/models` on the gateway, read with
`curl --noproxy '*'`. A candidate marked `?` that the gateway does not serve
is reported and skipped. A role whose provider the gateway does not know is
unresolved, so the group that holds it stays incomplete instead of losing a
member. A required role with no live model fails with the model list the
gateway serves.

Groups are created with `magpie group add` and updated with `magpie group
set`, both with `models=`, `routing=drain`, `stays=auto` and `listed=`. The
member order of a live group is read from the report by looking for the ids
the catalog knows, so a group that already holds the wanted order is left
alone.

Before any change the engine copies `~/.claude/settings.json`,
`~/.pi/agent/settings.json`, `~/.pi/agent/models.json`, `~/.codex/config.toml`
and every `~/.dsh/profiles/*/cordis.patch.yml` into
`~/.local/state/dotfiles/magpie/backups/<UTC>/` at 0600 and keeps the newest
ten. The Codex configuration is hashed before the changes and hashed again
after them; a change aborts the apply and keeps the backup. The state is
written to `~/.local/state/dotfiles/magpie/state.tsv` through a temporary file
and `mv -f`, and only when it differs from the recorded state, so a second run
writes nothing and keeps every modification time.

Tests run:

- `bash -n deployment/magpie.sh` — passes.
- `python3 -m unittest tests.test_magpie -v` — 19 tests, all pass. The apply
  tests drive a fake `magpie` and a loopback gateway: the providers, groups
  and wiring are created, `magpie settings set proxy` runs once, no `codex`,
  `claude`, `accounts add` or `accounts import` command is issued, a missing
  credential fails with the variable name, a second apply writes nothing, a
  Codex change during the apply aborts and keeps the backup, and the Codex
  configuration is byte-identical afterwards.
- `shellcheck deployment/magpie.sh` — not run: shellcheck is not installed on
  this device (it belongs to the optional developer bundle).

Correction after the review: the proxy endpoint keeps the template's
`proxyUrl` for a remote address, and a loopback endpoint is resolved at call
time through `with-proxy --print-url`, because a local port belongs to
whichever proxy client the device runs (Clash Verge on 7897, the deployment
proxy on 7890) and not to the operating system. `with-proxy --print-url`
remains the fallback when the template names no endpoint. The rule keeps the
repo's own proxy invariant and makes the gateway use the proxy that is
actually running.
