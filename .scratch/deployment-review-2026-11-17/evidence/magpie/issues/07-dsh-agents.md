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

**Status:** done

- [x] Catalog validation passes for both rows and the plan lists both commands.
- [x] Installed launchers exist at `~/.local/bin/dsh`, `~/.local/bin/dsh-tui`, `~/.local/bin/dst` in a simulated install.
- [x] `bun install --frozen-lockfile` succeeds from a clean cache.
- [x] `dsh --version` and `dsh-tui --version` answer with pnpm on PATH.
- [x] `tests/test_agent_catalog.py` and `tests/test_common_providers.py` cover the new rows and pass.

## Comments

The two agents are ordinary managed agents: frozen Bun projects, no Herdr
kind, and a launcher each. `dsh` exposes `dsh`, `dsh-tui` exposes `dsh-tui`
and `dst`. Their minimum Node versions are the ones the packages declare
(24.9.0 for `@deepseek-ai/dsh`, 22.19 for the TUI). `pnpm` joins the common
catalog as `pnpm==12.21.0`, exposed as `pnpm`, so the TUI's first run finds a
managed runtime instead of an unmanaged one; conda-forge carries that build,
and it is the current release.

The locks were generated with the pinned Bun 1.4.2 (the catalog pin; the
device runs Homebrew's 1.4.4), taken from a throwaway Pixi environment so the
repository was not touched by an install. Both locks carry
`lockfileVersion: 2`, which is the format the pinned Bun writes and reads.

The proof ran in a temporary directory with the pinned Bun and pnpm on PATH:

- `bun install --frozen-lockfile` in the `dsh` project installed 589 packages
  and `dsh --version` answered `0.2.2-rc.1`.
- `bun install --frozen-lockfile` in the `dsh-tui` project installed 95
  packages. `dsh-tui --version` and `dst --version` answered
  `@deepseek-harness-tui/dsh-tui 0.20.1 (launcher)`.
- `dsh-tui doctor` reported `node` ok, `pnpm 12.21.0` ok, the profile not yet
  installed (the TUI bootstraps it on the first run) and no `DEEPSEEK_API_KEY`.
  The peer set launches under the frozen project, so the record keeps its
  provider.

The install blocks six postinstall scripts, because neither project trusts a
lifecycle script. The TUI's peer warnings (`@deepseek-ai/cordis@4.1.0` and
`@deepseek-ai/dsh-invariants@0.1.7-rc.2` outside the declared peer range) are
warnings, not failures, and the frozen install accepts the lock.

Tests run:

- `python3 deployment/update_versions.py verify --bun <pinned bun 1.4.2>` —
  passes, including the frozen-lock check for every agent, the new ones
  included.
- `python3 -m unittest test_agents test_agent_catalog test_common_providers` —
  pass. The new test drives a simulated install with a synthetic Bun and
  checks that `~/.local/bin/dsh`, `~/.local/bin/dsh-tui`, and
  `~/.local/bin/dst` exist and point at the frozen project.
- `bash bootstrap.sh --plan` lists `dsh` and `dsh-tui` with their packages,
  commands, and no Herdr kind, and lists `pnpm` in the common packages.
