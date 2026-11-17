# Magpie model gateway

## Problem Statement

Every coding agent on this device holds its own vendor URL, key, and model
choice. Claude Code points at a LAN GLM gateway, Pi at MiniMax China, Codex at
ChatGPT, and the repo's `client-settings` merge writes those choices for every
host. Four paid accounts — ChatGPT Pro, OpenCode Go, Kimi Code China, MiniMax
China — are usable only from whichever agent was hand-configured for them, a
quota exhaustion surfaces to the agent as an error instead of moving to the
next account, and there is no single place to see what each agent is spending.
A new host has to be hand-wired again.

DeepSeek Harness (`dsh`) and its TUI (`dsh-tui`) are installed on this device
but not managed: the `dsh` command is missing, `dsh-tui` is absent, and neither
has an installation record, a pinned version, or a launcher. `pnpm`, which
`dsh-tui` needs on first run, is not installed at all.

## Solution

The deployment owns one Magpie **model gateway** on `127.0.0.1:3425`. The repo
declares which model providers exist, which models each routing group holds and
in what order, and which agents are wired to which group; Magpie holds the
credentials, the generated agent artifacts, and its usage store. Claude Code
runs on `group/conductor`, Pi and `dsh` run on `group/workhorse`, and ChatGPT
is a standalone group used only as the conductor's last resort. Codex stays on
its own ChatGPT Pro configuration and is never written.

`dsh` and `dsh-tui` become ordinary managed agents (frozen Bun projects, no
Herdr integration kind), and `pnpm` becomes a pinned Pixi common tool.

## User Stories

1. As the device owner, I want one local gateway that every wired agent uses, so that vendor keys and URLs live in one place and no agent config holds a secret.
2. As the device owner, I want Claude Code on `group/conductor`, so that it stays on Kimi K3.1 Pro until that plan is used up, then DeepSeek V4.1 Flash, then the ChatGPT group.
3. As the device owner, I want Pi and `dsh` on `group/workhorse`, so that MiniMax M3.1 Flash carries coding turns and DeepSeek V4.1 Flash takes over when MiniMax is used up.
4. As the device owner, I want ChatGPT in its own group and only reachable as the conductor's last member, so that the Pro plan is not spent while Kimi or DeepSeek still have quota.
5. As the device owner, I want the group membership and model ids in editable catalogs, so that a vendor model rename is a config edit, not a code change.
6. As the device owner, I want a missing required model to fail the apply by name, and an optional model marked `?` to be skipped, so that failover order never silently loses a member.
7. As the device owner, I want provider credentials read from the stores that already hold them, so that I do not paste the same key twice.
8. As the device owner, I want the Kimi Code China plan key kept in a device-owned 0600 file, so that a rebuild can re-add the provider without the key entering git or a log.
9. As the device owner, I want Magpie's provider traffic to go through the local Clash Verge proxy at `127.0.0.1:7897`, so that providers unreachable directly still answer, while loopback gateway traffic stays direct.
10. As the device owner, I want the deployment to adopt the Homebrew Magpie cask and own a `magpie` launcher, so that the CLI and the GUI are one install and the CLI is on PATH.
11. As the device owner, I want the GUI app to own the gateway process, so that there is one owner of port 3425 and no competing daemon.
12. As the device owner, I want Magpie deployed by default on macOS and disabled with one flag, so that a fresh Mac is wired without a manual step and a host that cannot run it says so.
13. As the device owner, I want the repo's client-settings merge to write Claude Code's Magpie endpoint and model, so that bootstrap and Magpie never fight over the same file.
14. As the device owner, I want `magpie pi group/workhorse` to generate Pi's `models.json`, so that context windows, costs and thinking levels stay Magpie's data rather than a hand-copied table.
15. As the device owner, I want `magpie dsh group/workhorse` to add a Magpie route while leaving DSH's official `llm-deepseek` row intact, so that I can switch back to the official DeepSeek provider at any time.
16. As the device owner, I want `dsh` and `dsh-tui` installed as pinned Bun agents with launchers, so that they are managed like Pi and OpenCode.
17. As the device owner, I want `pnpm` pinned through Pixi, so that `dsh-tui`'s first run does not depend on an unmanaged runtime.
18. As the device owner, I want a before/after hash guard on `~/.codex/config.toml`, so that no Magpie step can silently repoint ChatGPT Pro.
19. As the device owner, I want timestamped 0600 backups of every client file Magpie touches, so that a bad apply is reversible without git.
20. As the device owner, I want `dotfiles-magpie status` to report the gateway, proxy, providers, group order and agent wiring, so that drift is visible without opening the app.
21. As the device owner, I want the official OpenCode, Kimi and MiniMax agent configurations left byte-for-byte alone, so that I can keep using those agents directly outside Magpie.
22. As the device owner, I want the apply to say which credentials are missing and why, so that a half-configured gateway is never mistaken for a healthy one.
23. As the device owner, I want simulated-home applies to use a fake Magpie and never launch the GUI, so that the deployment tests stay offline and hermetic.
24. As a future maintainer, I want a glossary distinction between an installation provider and a model provider, so that the two meanings of "provider" never collapse again.

## Implementation Decisions

### Ownership split

- **Deployment owns**: the Homebrew cask adoption, the `~/.local/bin/magpie`
  launcher, `dotfiles-magpie`, the provider/group/model catalogs, Claude Code's
  hand-written settings, Pi's default provider/model, the bootstrap switch, and
  the Codex hash guard.
- **Magpie owns**: provider keys and accounts, its usage store, routing
  decisions, Pi's generated `~/.pi/agent/models.json`, and DSH's Magpie route.
  These are never committed and never edited by the repo.
- **Neither owns**: Codex's `~/.codex/config.toml` and `auth.json`, and the
  official OpenCode, Kimi Code and MiniMax Code configurations.

### New catalogs

`deployment/magpie/providers.tsv` — `role|magpie provider|key source|required`:

```
chatgpt|codex|codex-account|yes
opencode-go|opencode-go|json:~/.local/share/opencode/auth.json:opencode-go.key|yes
kimi-code-cn|kimi-code-cn|env:KIMI_CODE_CN_API_KEY|yes
minimax-cn|minimax-cn|json:~/.pi/agent/auth.json:minimax-cn.key|yes
```

`json:` sources are read only. `env:` sources come from
`~/.config/dotfiles/magpie.env`, mode 0600, never sourced by a shell profile.

`deployment/magpie/models.tsv` — `role|candidate ids|required`, one row per
role, candidates comma-separated in preference order; a trailing `?` on an id
marks it optional:

```
chatgpt.sol|codex/gpt-6.1-sol|yes
chatgpt.terra|codex/gpt-6.1-terra|yes
conductor.kimi|kimi-code-cn/k3.1-pro|yes
conductor.deepseek|opencode-go/deepseek-v4.1-flash|yes
workhorse.minimax|minimax-cn/MiniMax-M3.1-Flash|yes
```

`deployment/magpie/groups.tsv` — `id|members|routing|stays|listed|purpose`;
members are role names or `group/<id>`:

```
chatgpt|chatgpt.sol,chatgpt.terra|drain|auto|no|standalone ChatGPT plan group
conductor|conductor.kimi,conductor.deepseek,group/chatgpt|drain|auto|yes|Claude Code
workhorse|workhorse.minimax,conductor.deepseek|drain|auto|yes|Pi and dsh
```

`drain` is Magpie's "Until used up": a member's accounts are spent in order and
an earlier member is never revisited after it rests. `listed=no` keeps the
ChatGPT group out of agent pickers while still allowing `group/chatgpt` as a
member.

`deployment/magpie/wiring.tsv` — `agent|group|owner|enabled`:

```
claude|group/conductor|repo|yes
pi|group/workhorse|magpie|yes
dsh|group/workhorse|magpie|yes
dsh-tui|-|inherited|yes
```

### Apply algorithm (`magpie-apply`)

Runs after `install-agents` and `apply-source` (so the cask, agents and client
settings exist), before `prepare-shell`, only on macOS by default.

1. Validate all four catalogs: field counts, known presets, no key material,
   unique group ids, every member role exists, every `group/` member exists.
2. Snapshot `~/.codex/config.toml`'s SHA-256, and copy `~/.claude/settings.json`,
   `~/.pi/agent/settings.json`, `~/.pi/agent/models.json`,
   `~/.dsh/profiles/*/cordis.patch.yml` and the Codex config into
   `~/.local/state/dotfiles/magpie/backups/<UTC>/` at 0600 (keep the last 10).
3. Ensure the gateway answers: `magpie status --json`. If not, and this is the
   real account home, `open -a magpie`, wait up to 30 s. Otherwise report the
   command to run and continue with a named warning.
4. Resolve the proxy: template `proxyUrl`, else `with-proxy --print-url`, else
   fail. Apply only when different: `magpie settings set proxy <url>`.
5. Ensure providers, in catalog order. A missing required credential names the
   source and the variable, and is a hard failure if the provider's models are
   in an enabled group. `codex-account` requires an account from
   `magpie accounts codex --json`; the apply never runs `accounts add`.
   Preset adds use `magpie provider add <preset> <key>`; an existing provider
   is left alone.
6. Resolve models from `GET /v1/models` (`curl --noproxy '*' -H 'Authorization:
   Bearer magpie'`). Each required role must match at least one candidate;
   an optional candidate that matches nothing is reported and skipped; a
   required role with no match fails with the actual model list.
7. Ensure groups: `magpie group <id>` uses its exit status for existence;
   create with `magpie group add <id> models=… routing=… stays=… listed=…`,
   otherwise `magpie group set <id> models=… routing=… stays=… listed=…`.
8. Wire `magpie`-owned agents: `magpie pi group/workhorse` and
   `magpie dsh group/workhorse`. Never `magpie claude` (the repo template owns
   Claude) and never `magpie codex`.
9. Re-read the Codex config hash and abort if it changed. Write
   `~/.local/state/dotfiles/magpie/state.tsv` (provider, group, model order,
   wiring timestamp) through a temporary file and `mv -f`.
10. Print a summary: gateway URL, proxy, providers present/missing, each group's
    resolved member order, and each agent's wiring.

A run with nothing to change writes no files and keeps every modification time.

### Claude Code

`deployment/client-settings/claude-settings.json.tmpl` becomes the Magpie
wiring: `env.ANTHROPIC_BASE_URL=http://127.0.0.1:3425`,
`env.ANTHROPIC_AUTH_TOKEN=magpie`, `model=group/conductor`, no
`ANTHROPIC_MODEL`, no `ANTHROPIC_DEFAULT_*_MODEL`, no `ANTHROPIC_SMALL_FAST_MODEL`,
no `CLAUDE_CODE_SUBAGENT_MODEL`. The exact remaining shape is transcribed from
what `magpie claude group/conductor` writes into a sandbox `CLAUDE_CONFIG_DIR`,
so the template and Magpie agree field for field. The GLM template data
(`glmBaseUrl`, `glmToken`) is removed from the template and from
`.chezmoi.toml.tmpl`; the legacy T9K adapters are outside this change.

### Pi

`deployment/client-settings/pi-settings.json.tmpl` sets
`defaultProvider=magpie` and `defaultModel=group/workhorse`, keeps the device's
`modelThinkingLevels`, and does not create `enabledModels`. Magpie generates
`~/.pi/agent/models.json`; the repo never templates it. `.pi/agent/models.json`
is added to `.chezmoiignore` as Magpie-owned.

### DSH and dsh-tui

`dsh` is a Bun agent (`@deepseek-ai/dsh`, command `dsh`), `dsh-tui` is a Bun
agent (`@deepseek-harness-tui/dsh-tui`, commands `dsh-tui,dst`), both
`selectable`, no Herdr kind. `magpie dsh group/workhorse` adds Magpie's route
among DSH's custom providers and starts new sessions on it; DSH's official
`llm-deepseek` row is left untouched, so selecting the DeepSeek row in DSH's
Models page switches back. `dsh-tui` has no separate wiring: it reads DSH's
profile. `~/.dsh-tui/settings.json` stays device-owned.

### pnpm

`pnpm==12.21.0` joins `deployment/common-tools.tsv` as `pnpm|pnpm==12.21.0|pnpm=pnpm|all`.
It is exposed through the Pixi common environment, so the `dsh-tui` launcher
finds it without a Homebrew dependency.

### Install and service

- macOS: `brew install --cask magpie` is adopted, never installed by the repo;
  a floor is recorded like other Homebrew records. `dot_local/bin/executable_magpie`
  execs `/Applications/magpie.app/Contents/MacOS/magpie "$@"`.
- The app owns the gateway and its login item. The deployment never installs
  `magpie daemon`; it verifies `magpie status` and, on the real account home,
  opens the app once when nothing answers.
- Other platforms: the step reports "Magpie is not available on this platform"
  and completes; the catalogs are shaped so a later pinned native release can
  be added.

### Bootstrap switch

`bootstrap.sh --no-magpie` and `DOTFILES_MAGPIE=false` disable the step;
otherwise it is on for macOS. `--plan` gains `"magpie": true|false`.
`magpie-apply` is appended to the action list after `install-agents`; it is
skipped under `--apply-only` and `--agents-only`, and says why.
`deployment/proxy-policy.tsv` gains `magpie-apply|yes|provider requests leave
through the device proxy`.

### `dotfiles-magpie`

`~/.local/bin/dotfiles-magpie` with `apply`, `status`, and `providers`:

- `apply` runs the same `magpie_apply` function the bootstrap step calls.
- `status` prints gateway, proxy, provider presence, group member order, agent
  wiring, and the last Codex guard result; it exits non-zero when a required
  piece is missing.
- `providers` prints the catalog with each credential source and whether it
  resolves, never the value.

## Testing Decisions

- **Catalog validation** is a pure function over the four TSVs, tested with
  synthetic rows (unknown preset, duplicate group, missing role, required model
  without a match, secret-looking value).
- **Apply** is tested against a fake `magpie` on PATH that records every argv
  and serves canned `status`, `accounts`, `provider`, `group`, and `/v1/models`
  responses. Assertions: exact command order, no `magpie codex`, no `magpie
  claude`, proxy set once, group member order, second run writes nothing.
- **Codex guard** is tested by mutating the fake Codex config during apply and
  asserting the apply aborts and keeps the backup.
- **Bootstrap**: `--plan` includes `magpie`; `--no-magpie` removes the action;
  non-macOS reports the skip; simulated-home apply never calls `open`.
- **Agent catalog**: the new `dsh`/`dsh-tui` rows pass the existing validators,
  produce launchers, and have no Herdr kind.
- **Live acceptance** on this device: real cask, real providers, real groups,
  `magpie provider test` for each required provider, `curl --noproxy '*'` on
  `/v1/models`, one tiny completion through each group, `~/.codex/config.toml`
  hash unchanged, official OpenCode/Kimi/MiniMax configs unchanged, and the
  STEP 1 backups present.

## Out of Scope

- The community Zed provider plugin (`@magpie-community/opencode-zed-auth`).
  Zed remains an agent that can consume Magpie, not a source.
- Wiring the official OpenCode, Kimi Code, MiniMax Code or Codex agents.
- Magpie profiles, intent routing, privacy masking, gateway keys for other
  machines, Docker, and the Linux/Windows native release.
- Removing the legacy T9K GLM adapters outside the shared client-settings
  template.

## Further Notes

- The Kimi Code China plan key is created at `https://www.kimi.com/code/console`
  and stored as `KIMI_CODE_CN_API_KEY` in `~/.config/dotfiles/magpie.env`.
  Until it exists, the conductor is incomplete and `status` says so; the apply
  still builds `chatgpt` and `workhorse` and reports the missing member.
- Model ids move. `models.tsv` is the only place they live; a vendor rename
  changes one line and `dotfiles-magpie apply` reports the resolved order.
- `dsh-tui` pulls a large peer set and needs `pnpm` on first run; the ticket
  must prove a frozen Bun install launches `dsh-tui --version` before the live
  wiring is attempted.
- Magpie may refresh Codex's OAuth token when it reads the ChatGPT account;
  that is the supported path and it writes the rotated token back. The guard
  covers `config.toml` only, never `auth.json`.

## Seams

1. **Catalog boundary** — four TSVs parsed by one validator; tests build
   synthetic catalogs without touching `$HOME`.
2. **Command boundary** — `magpie_apply` takes a runner (`MAGPIE_BIN`, `RUN`)
   so a fake binary records argv; no test needs the real gateway.
3. **Gateway API** — model resolution reads `/v1/models` once per apply; the
   same JSON is the acceptance evidence.
