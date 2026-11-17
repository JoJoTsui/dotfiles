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

**Status:** ready-for-agent

- [ ] `bash -n deployment/magpie.sh` passes; shellcheck-clean where the repo's other deployment scripts are.
- [ ] Each step prints a `dotfiles: magpie: …` line and sets a `DEPLOY_STEP` label.
- [ ] `MAGPIE_BIN` substitution is used by every magpie invocation.
- [ ] No command writes `~/.codex/config.toml`, `~/.claude/settings.json`, `~/.pi/agent/settings.json` or `~/.dsh/profiles/*` directly.
- [ ] Unit tests with a fake `magpie` cover order, failure, idempotence and the Codex abort.

## Comments
