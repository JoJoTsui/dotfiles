# 07: dsh and dsh-tui as Bun agents, pnpm as a Pixi tool

**What to build:** Two agent records and two frozen Bun projects, plus one common tool:

- `deployment/agents/providers.tsv`:
  - `dsh|bun|@deepseek-ai/dsh|-|0.2.2-rc.1|exact|dsh|all|1|selectable|-|24.9.0|-|deployment/agents/dsh/bun.lock|-`
  - `dsh-tui|bun|@deepseek-harness-tui/dsh-tui|-|0.20.1|exact|dsh-tui,dst|all|1|selectable|-|22.19.0|-|deployment/agents/dsh-tui/bun.lock|-`
- `deployment/agents/dsh/{package.json,bun.lock}` and `deployment/agents/dsh-tui/{package.json,bun.lock}`, generated with the pinned Bun and installable with `bun install --frozen-lockfile`.
- `deployment/common-tools.tsv`: `pnpm|pnpm==12.21.0|pnpm=pnpm|all`.
- `bootstrap.sh --help` selectable-name list gains `dsh` and `dsh-tui`.

No Herdr kind: Herdr 0.9.5 has no dsh integration, so both records use `-`. Do not add a kind to `herdr-kinds.tsv`.

Prove in a temporary directory that `bun install --frozen-lockfile` installs both, `dsh --version` answers, and `dsh-tui --version` (or `dst --version`) answers with pnpm on PATH. If the TUI's peer set cannot launch under the frozen project, stop and report the exact failure; do not switch the record to a different provider silently.

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] Catalog validation passes for both rows and the plan lists both commands.
- [ ] Installed launchers exist at `~/.local/bin/dsh`, `~/.local/bin/dsh-tui`, `~/.local/bin/dst` in a simulated install.
- [ ] `bun install --frozen-lockfile` succeeds from a clean cache.
- [ ] `dsh --version` and `dsh-tui --version` answer with pnpm on PATH.
- [ ] `tests/test_agent_catalog.py` and `tests/test_common_providers.py` cover the new rows and pass.

## Comments
