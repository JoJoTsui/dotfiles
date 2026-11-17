# Magpie model gateway

Magpie is the model gateway this deployment runs. It listens on
`127.0.0.1:3425`, serves the OpenAI, Anthropic, and Gemini compatible APIs,
and routes every request to a **model provider**: a vendor account or API key
whose models the gateway serves under `provider/model`.

The repository owns the *intent*: which providers exist, which models each
routing group holds, and which agent uses which group. Magpie owns the
*credentials and the generated state*: the provider keys, the accounts, the
usage store, Pi's `models.json`, and DSH's Magpie route. Codex belongs to
neither side and is never written.

## Ownership

| Owner | Owns | Never owns |
| --- | --- | --- |
| The repository | the five catalogs, Claude Code's settings, Pi's default provider and model, the bootstrap switch, the Codex hash guard | any credential, any generated agent file |
| Magpie | provider keys and accounts, the usage store, Pi's `~/.pi/agent/models.json`, DSH's Magpie route | the intent: which models a group holds |
| Neither | `~/.codex/config.toml` and `~/.codex/auth.json`, the official OpenCode, Kimi Code, and MiniMax Code configurations | — |

## Install and adopt

The Homebrew cask owns the app and the gateway process. The deployment adopts
the cask and never installs it:

```bash
brew install --cask magpie   # the operator's step; the deployment never installs it
```

The deployment adopts the cask and records the floor it accepts
(`0.1.4325`); it never installs the cask and never upgrades it. Every apply
reports the app it found, and a missing or old app is a warning rather than a
failure: the gateway may still answer from an earlier install.

The repository owns two managed commands:

- `~/.local/bin/magpie` runs the binary the app ships, so the CLI and the GUI
  are one install. It prints the cask command when the app is missing.
- `~/.local/bin/dotfiles-magpie` is the deployment's half of the gateway:
  `apply`, `status`, and `providers`.

The app owns the gateway and its login item. The deployment never installs
`magpie daemon`; it verifies `magpie status --json` and, on the real account
home, opens the app once when nothing answers. On macOS a gateway that still
does not answer fails the step, with the command that fixes it: a deployment
never leaves Claude Code or Pi wired to a gateway that is not there.

## The switch

The step is on by default on macOS and off on every other platform.

```bash
bash bootstrap.sh --no-magpie          # turn the step off for one run
DOTFILES_MAGPIE=false bash bootstrap.sh   # turn the step off for one run
bash bootstrap.sh --plan | grep magpie    # what the run would do
```

`--plan` reports `"magpie": true|false` and lists the `magpie-apply` action.
Every run prints why the step was skipped: the platform has no Magpie, the
step is disabled, or the mode applies files and installs agents without the
gateway (`--apply-only`, `--agents-only`).

## The catalogs

The catalogs live in `deployment/magpie/` and are the only place the model
intent is written. A vendor rename is a config edit, not a code change. Each
one reaches the managed command through a `{{ include }}` wrapper under
`dot_config/dotfiles/magpie/`, so the deployment and `dotfiles-magpie` read
the same bytes.

### `providers.tsv` — `role|magpie provider|key source|required`

| Field | Meaning |
| --- | --- |
| role | the repository name of one model provider; a group member and a model candidate's provider prefix refer to it |
| magpie provider | the Magpie preset that owns the provider's accounts |
| key source | `codex-account`, `env:NAME`, or `json:PATH:KEY` |
| required | `yes` when the provider must exist, `no` when its absence is only reported |

### `models.tsv` — `role|candidate ids|required`

The candidates are the model ids the gateway may serve for that role, in
preference order. A trailing `?` marks a candidate optional: it is reported
and skipped when the gateway does not serve it. A required role with no live
model fails the apply with the model list the gateway serves.

### `groups.tsv` — `id|members|routing|stays|listed|purpose`

A member is a model role or `group/<id>` for another group. `drain` spends a
member's accounts until they are used up, moves to the next member, and never
returns to an earlier one. `listed=no` keeps a group out of the agent pickers
while it stays reachable as another group's member, but it also removes the
models the group names from `/v1/models`; the deployment therefore keeps
`group/chatgpt` listed so the next apply can still resolve its members.

A model role may pin a reasoning effort as `role:<effort>`, where the effort
is one of `none|minimal|low|medium|high|xhigh|max`. The deployment strips it
for the role lookup and appends it to every model id the role resolves to, so
`conductor.kimi:max` becomes `kimi-code-cn/k3.1-pro:max`. A group reference
carries no effort, because a group keeps its own routing. A group without a
suffixed member keeps Magpie's `effort=agent` default.

### `wiring.tsv` — `agent|group|owner|enabled`

`owner` is `repo` when the deployment writes the agent's configuration by
hand, `magpie` when Magpie generates it, and `inherited` when the agent
follows another agent. The deployment never wires Codex, and it never lets
Magpie write Claude Code's settings.

### `visible.tsv` — `agent|names`

`names` is a comma-separated list of declared group ids and Magpie provider
ids. The apply runs `magpie visible <agent> <names>` after the groups and
before the agent wiring, and only when the narrowing differs from what
`magpie visible <agent>` reports. It never passes `--only-picked`: that
freezes the current list and would hide a model starred later. A provider id
in a row exposes the models starred for that provider; Magpie's `pickedModels`
stars stay the app's state. `status` prints the live narrowing as
`visible|agent|names`.

### `plugins.tsv` — `name|source|version|enabled`

One row per community plugin the deployment pins: the short name
`magpie plugin on|off` takes, the npm package, the exact version, and whether
the deployment ensures it. The deployment installs an absent package with
`magpie plugin add npm:<source>@<version>`, turns an installed-but-off plugin
on with `magpie plugin on <name>`, and never updates or removes a present one.
The plugin is community-owned: the repository only pins and installs it.

A plugin that signs in to a provider needs a human sign-in after it is
installed. For the Zed plugin that is `magpie plugin login zed`, or the
**Plugins** page of the Magpie app. The deployment never runs the sign-in.
`status` reports the plugin as `plugin|<name>|loaded`, `off`, or `missing`.

## The apply order

`magpie-apply` runs after `install-agents` and before `prepare-shell`, so the
app, the agents, and the client settings exist before the gateway is wired.

1. Validate the catalogs.
2. Ensure the gateway answers: `magpie status --json`. On the real account
   home the app is opened and waited for. A gateway that still does not answer
   fails the step with the install/open command; a non-macOS host is skipped
   before this point.
3. Resolve the proxy and write it with `magpie settings set proxy` only when
   it differs.
4. Ensure the pinned plugins, before the providers: `magpie plugin list
   --json` reports `.loaded[].spec`, so an absent package is installed and a
   loaded-but-off one is turned on.
5. Ensure the providers in catalog order.
6. Resolve the model roles against `GET /v1/models`.
7. Ensure the groups: `magpie group add`, or `magpie group set` when the
   member order differs.
8. Narrow each agent: `magpie visible <agent> <names>`, only when it differs.
9. Wire the Magpie-owned agents: `magpie pi group/workhorse` and
   `magpie dsh group/workhorse`.
10. Verify that DSH's official `llm-deepseek` row is unchanged and that the
    Codex configuration still hashes the same.
11. Write `~/.local/state/dotfiles/magpie/state.tsv` through a temporary file.

A run with nothing to change writes no files and keeps every modification
time.

## Provider credentials

The deployment reads the stores that already hold the credentials, so the same
key is never pasted twice. The value is used once, to add the provider, and
never reaches a log, a report, or the repository.

| Source | Store | Notes |
| --- | --- | --- |
| `codex-account` | a ChatGPT account Magpie reads | `magpie accounts codex --json`; the apply never runs `accounts add` or `accounts import` |
| `env:NAME` | `~/.config/dotfiles/magpie.env` | mode 0600, parsed and never sourced by a shell profile |
| `json:PATH:KEY` | a JSON store on the device | read only, by a dotted key path |

### The Kimi Code China key

The Kimi Code China plan key is created at
<https://www.kimi.com/code/console> and stored as `KIMI_CODE_CN_API_KEY` in
`~/.config/dotfiles/magpie.env`:

```bash
mkdir -p ~/.config/dotfiles
printf 'KIMI_CODE_CN_API_KEY=<the key>\n' > ~/.config/dotfiles/magpie.env
chmod 600 ~/.config/dotfiles/magpie.env
```

Until the key exists, the conductor group is incomplete: the apply still
builds the `chatgpt` and `workhorse` groups, reports the missing member by
name, and fails the run because a required credential is missing.
`dotfiles-magpie status` says so too. The key never enters git and never
enters a ticket comment.

## Proxy behaviour

The gateway's own traffic to the providers leaves through the device proxy;
the loopback traffic to the gateway stays direct.

The endpoint comes from the template's `proxyUrl`. A remote endpoint is used
as it is, because only the device knows it. A loopback endpoint is resolved
at call time through `with-proxy --print-url`, because a local port belongs to
whichever proxy client the device runs — Clash Verge on 7897, the deployment
proxy on 7890 — and not to the operating system. `with-proxy --print-url` is
also the fallback when the template names no endpoint. The value is written
with `magpie settings set proxy` only when it differs from the current one.

On a device whose proxy client runs on another port than the template names,
set `HTTP_PROXY_URL` before the deployment, or set the proxy once by hand:

```bash
magpie settings set proxy http://127.0.0.1:7897
```

## Group semantics

`group/conductor` is the Claude Code group, and it holds one member:
`group/openai-stack`. The stack drains the ChatGPT weekly quota, then the
paid OpenAI API key with `openai/gpt-6.1-sol` and `openai/gpt-6.1-terra`, then
Kimi K3.1 Pro at max reasoning. `group/workhorse` is the Pi and `dsh` group:
MiniMax M3.1 Flash, then DeepSeek V4.1 Flash. `group/chatgpt` holds the
ChatGPT plan models and is listed as its own group, so the Pro plan is spent
only when the stack's own members have no quota left.

The template sets `model: opus` and points every tier and subagent model at
`group/conductor`. Claude Code accepts the `opus` alias and resolves it
through `ANTHROPIC_DEFAULT_OPUS_MODEL`, so the gateway receives the group.
Do not pick a bare `group/<id>` in `/model`: Claude Code rewrites an
unrecognized main model to a bare alias. A bare alias without the tier
mapping names an Anthropic model the gateway does not serve. Claude Code may
save its own alias (`sonnet[1m]`) after a run and append `[1m]` to a tier; the
sonnet tier still maps to `group/conductor`, and Magpie strips the marker.

A model role contributes the models its candidates resolve to. `group/<id>`
stays a reference: the apply validates the referenced group's members but
passes `group/<id>` to Magpie, so that group keeps its own routing and listed
setting. A group with an unresolved member is left alone rather than created
with a missing member.

## Rollback

Before it changes anything, the apply copies the client files Magpie may
touch into `~/.local/state/dotfiles/magpie/backups/<UTC>/` at 0600 and keeps
the newest ten:

- `~/.claude/settings.json`
- `~/.pi/agent/settings.json`
- `~/.pi/agent/models.json`
- `~/.codex/config.toml`
- every `~/.dsh/profiles/*/cordis.patch.yml`

To roll back, copy a file from a backup over the live one. The Codex
configuration is never written by the deployment, and every apply hashes it
before and after the changes; a change aborts the run and keeps the backup.
`~/.local/state/dotfiles/magpie/state.tsv` records what the last apply did:
the providers, the groups with their model order, the wiring, the proxy, and
the Codex guard verdict.

## Other platforms

Magpie is a macOS application today. On Linux, WSL, and native Windows the
step reports `Magpie is not available on this platform` and completes, the
engine and the catalogs stay out of the home, and `dotfiles-magpie` refuses
in one line. Claude Code and Pi keep their device-owned endpoint and model
there: the client-settings templates branch on `.platform`, so no host is
pointed at a gateway it cannot run. The catalogs are shaped so a later pinned
native release can be added without changing the intent.

## The command

```bash
dotfiles-magpie apply       # apply the catalogs to the local gateway
dotfiles-magpie status      # gateway, proxy, providers, groups, wiring, guard
dotfiles-magpie providers   # the provider catalog and its credential sources
```

`status` is read-only and exits non-zero when a required piece is missing.
`providers` prints the catalog with the state of each credential source and
never a value.
