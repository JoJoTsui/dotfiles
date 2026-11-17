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

**Status:** ready-for-agent

- [ ] `python3 -m unittest tests.test_magpie -v` passes without network or a real Magpie.
- [ ] The existing suites pass on macOS, or the known host-scope failures are named in the ticket comment.
- [ ] No test reads the real `~/.config/magpie`, `~/.codex` or `~/.dsh`.
- [ ] A simulated-home apply creates only files under the simulated home.

## Comments
