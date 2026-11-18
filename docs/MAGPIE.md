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
| The repository | the seven catalogs, Claude Code's settings, Pi's default provider and model, the bootstrap switch, the Codex hash guard | any credential, any generated agent file |
| Magpie | provider keys and accounts, the usage store, Pi's `~/.pi/agent/models.json`, DSH's Magpie route | the intent: which models a group holds |
| Neither | `~/.codex/config.toml` and `~/.codex/auth.json`, the official OpenCode, Kimi Code, and MiniMax Code configurations | — |

## Install and adopt

The Homebrew cask owns the app and the gateway process. The deployment adopts
the cask and never installs it:

```bash
brew install --cask magpie   # the operator's step; the deployment never installs it
```

The deployment adopts the cask and records the floor it accepts
(`0.1.4325`); it never installs the cask and never upgrades it. When its
application binary is absent, the deployment installs the pinned native CLI
instead. The macOS release assets are pinned but have not been executed in the
native verification for this change.

The repository owns two managed commands:

- `~/.local/bin/magpie` runs the application binary when it is present, or the
  installed native CLI when it is absent. It never replaces either binary.
- `~/.local/bin/dotfiles-magpie` is the deployment's half of the gateway:
  `apply`, `status`, `providers`, `test`, `start`, `stop`, and `install`.

The app owns its gateway and login item. The deployment never installs
`magpie daemon`; it verifies `magpie status --json` and, on the real account
home, opens the app once when nothing answers. Without the app it uses the
native CLI lifecycle below. The step does not newly wire Claude Code or Pi
before a gateway answers; existing wiring is preserved. If the app is installed
later, stop any deployment-owned gateway with `dotfiles-magpie stop` before
starting the application so the two do not compete for the same port.

## The native CLI on Linux, WSL, and app-absent macOS

Linux and WSL use the native Magpie CLI; macOS uses it when the app is absent.
The release catalog
`deployment/magpie/releases.tsv` owns the version every target shares and the
SHA-256 digest that verifies each asset:

```text
name|version|target|url|sha256
```

The catalog carries Linux, macOS, and Windows targets, so the version and
digests of one release live in one place. The deployment never resolves a
release at run time: the URL and the digest are the pin. Downloaded bytes are
verified before installation, and a failed download never touches a working
CLI.

The CLI lives at `~/.local/share/dotfiles/magpie/bin/magpie`, beside the
engine, so the managed command and the deployment step run one binary. The
engine and the catalogs reach the Linux and WSL homes through the source
application; the native Windows home keeps them out, because the PowerShell
adapter owns that side.

### The headless lifecycle

The lifecycle is explicit, and it never assumes a desktop or a working
systemd:

- `dotfiles-magpie start` starts `magpie serve` in the background, writes the
  pid and the log under `~/.local/state/dotfiles/magpie/gateway/`, and waits
  until the gateway answers.
- `dotfiles-magpie stop` stops the gateway the deployment started.
- `dotfiles-magpie install` installs the pinned native release.

The deployment writes no systemd unit, no login item, and no registry key.
`magpie daemon install` exists upstream and is the operator's own choice; the
deployment never runs it. A gateway that does not answer fails the step with
the command that starts it; the step does not newly wire clients before the
gateway answers. The lifecycle uses only `gateway.pid` to identify its
process. An unrecognized or stale record is preserved and blocks a new start;
inspect and reconcile that file before starting again. Existing gateway logs
are preserved and a new log is used when the usual log already exists.

The direct command requires the native account home for gateway operations:
`apply`, `status`, `providers`, `test`, `start`, and `stop`. It also rejects a
platform selector that does not match the native OS. `install` remains available
in a synthetic home; gateway commands refuse that home rather than probing the
shared loopback port. This boundary does not isolate an independently invoked
Magpie CLI.

The gateway the deployment starts does not inherit the deployment's proxy
environment: that instance is temporary, and a gateway that kept it would
reach the vendors through a port that stops with the deployment. For the same
reason the deployment never writes a temporary proxy endpoint into the
gateway's own settings.

## The switch

The gateway wiring step is on by default on macOS, Linux, and WSL. The native
Windows adapter installs the CLI by default but does not wire a gateway.

```bash
bash bootstrap.sh --no-magpie          # turn the step off for one run
DOTFILES_MAGPIE=false bash bootstrap.sh   # turn the step off for one run
bash bootstrap.sh --plan | grep magpie    # what the run would do
```

`--plan` reports `"magpie": true|false` and lists the `magpie-apply` action.
Every run prints why the step was skipped: the platform has no Magpie, the
step is disabled, or the mode applies files and installs agents without the
gateway (`--apply-only`, `--agents-only`).

A disabled or skipped step never wires the clients. The Claude Code and Pi
templates carry the gateway settings only for the migration merge inside
`magpie-apply`, after the gateway answers and the originals are backed up;
every ordinary client-settings merge renders without them. A device that was
wired by an earlier deployment keeps its working settings when a later run
disables or skips the step.

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
| key source | `codex-account`, `plugin-account`, `env:NAME`, or `json:PATH:KEY` |
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
in a row lets that provider's picked models through; the exact set is
`picked.tsv`. `status` prints the live narrowing as `visible|agent|names`.

### `picked.tsv` — `agent|entries`

`entries` is the per-agent "only models I pick" list: a group entry is
`group/<id>` and a model entry is `provider/model`. Every entry must be inside
the agent's `visible.tsv` row; the catalog validation rejects one that is not.
The apply writes the list into Magpie's own settings
(`~/.config/magpie/settings.json`, key `pickedModels`) with a Python merge
that preserves every other key and every other agent's picks, at 0600, then
runs `magpie visible` so Magpie saves and serves it. This is the one write the
deployment makes into Magpie's store; the app's **Agents** page edits the same
key when the operator ticks a model. `status` prints
`picked|agent|<n> entries`.

The shipped agent picks follow this Mac's provider selections: Codex and OpenAI
6.2 Sol/Astra and 6.1 Sol/Terra; Zed 6.1 Sol and 6 Luna; Kimi Code K3.1 Pro
and Kimi for Coding; OpenCode Go DeepSeek V4.1 Flash; and MiniMax M3.1 Flash.
The older GPT-6 Astra is not exposed by the currently selected providers, so
the agent picks use GPT-6.2 Astra.

### `plugins.tsv` — `name|source|version|enabled`

One row per community plugin the deployment pins: the short name
`magpie plugin on|off` takes, the npm package, the exact version, and whether
the deployment ensures it. The deployment installs an absent package with
`magpie plugin add npm:<source>@<version>`, turns an installed-but-off plugin
on with `magpie plugin on <name>`, and never updates or removes a present one.
The plugin is community-owned: the repository only pins and installs it.
Magpie 0.1.4351 reports an empty fresh-home list as `[]`; after installation,
it reports an object with `loaded` and `plugins`. Both empty-list and object
responses are accepted. An unreadable response still stops the apply before
any plugin install.

A plugin that signs in to a provider needs a human sign-in after it is
installed. For the Zed plugin that is `magpie plugin login zed`, or the
**Plugins** page of the Magpie app. The deployment never runs the sign-in.
`status` reports the plugin as `plugin|<name>|loaded`, `off`, or `missing`.

## The apply order

`magpie-apply` runs after `install-agents` and before `prepare-shell`, so the
app, the agents, and the client settings exist before the gateway is wired.

1. Validate the catalogs.
2. Ensure the gateway answers: `magpie status --json`. On the real account
   home the app is opened and waited for, and a headless host starts
   `magpie serve` and waits for it. A gateway that still does not answer
   fails the step with the command that fixes it; a platform without Magpie
   is skipped before this point.
3. Resolve the proxy and write it with `magpie settings set proxy` only when
   it differs.
4. Ensure the pinned plugins, before the providers: `magpie plugin list
   --json` reports `.loaded[].spec`, so an absent package is installed and a
   loaded-but-off one is turned on.
5. Ensure the providers in catalog order.
6. Resolve the model roles against `GET /v1/models`.
7. Ensure the groups: `magpie group add`, or `magpie group set` when the
   member order differs.
8. Write the per-agent picked list into Magpie's settings, only when it
   differs.
9. Narrow each agent: `magpie visible <agent> <names>`, only when it differs,
   and again for every agent whose picked list changed so the gateway serves
   the new list.
10. Wire the Magpie-owned agents: `magpie pi group/workhorse` and
    `magpie dsh group/workhorse`.
11. Migrate the repo-owned client settings through the client-settings
    merger: Claude Code's gateway environment and `opus` alias, Pi's default
    provider and model. The step asks the merger whether the wiring would
    change a file before it backs up anything, so the backup holds the
    originals and a current device keeps its files and their modification
    times. The merge runs only after the gateway changes succeed.
12. Verify that DSH's official `llm-deepseek` row is unchanged and that the
    Codex configuration still hashes the same.
13. Write `~/.local/state/dotfiles/magpie/state.tsv` through a temporary file.

A run with nothing to change writes no files and keeps every modification
time.

## Provider credentials

Magpie owns provider accounts and keys. The apply uses an existing provider
as it is and never passes a key to a command. The provider catalog's source
fields describe the device stores; the `providers` status command can check
whether those sources resolve without reporting their values.

| Source | Store | Notes |
| --- | --- | --- |
| `codex-account` | a ChatGPT account Magpie reads | `magpie accounts codex --json`; the apply never runs `accounts add` or `accounts import` |
| `env:NAME` | `~/.config/dotfiles/magpie.env` | mode 0600, parsed and never sourced by a shell profile |
| `json:PATH:KEY` | a JSON store on the device | read only, by a dotted key path |
| `plugin-account` | a provider a pinned plugin serves | signed in with `magpie plugin login <provider>` or the app's Plugins page; optional, as `zed` is |

### Provisioning a missing provider

On macOS, Linux, and WSL, the pinned `magpie provider add` accepts a key as a
command-line argument, which other processes may see. The apply does not use
that interface for key-based providers. For a missing required provider used by
an enabled group, it stops before changing gateway settings, plugins, or
providers and names each preset to provision; a missing optional provider is
reported without stopping the apply.
Add the named presets using the TUI's masked key entry, then apply again:

```bash
magpie tui
```

For example, the Kimi Code China preset uses the plan key from
<https://www.kimi.com/code/console>. Do not put the key in a shell command or
argument. An existing provider remains untouched, and the credential-free
`codex-account` provider can still be added by the apply.

## Proxy behaviour

The gateway can use a device proxy for provider traffic; loopback traffic to
the gateway stays direct.

`MAGPIE_PROXY_URL` takes precedence, followed by an explicitly supplied
`HTTP_PROXY_URL`. Otherwise, a custom template `proxyUrl` is used as supplied.
The template's default `http://127.0.0.1:7890` is a placeholder: the apply
asks `with-proxy --print-url-if-available` for an explicit `PROXY_HTTP` or an
observed local listener, probing 7897 then 7890. A listening port does not
prove that it belongs to a proxy or can reach a provider. If no endpoint is
available, the apply preserves the existing gateway setting and reports that it
is unchanged.
The ordinary `with-proxy --print-url` retains its fallback for shell callers.
The gateway setting is written only when the selected endpoint differs.

For a proxy on another port, set `HTTP_PROXY_URL` before deployment, or set the
proxy once by hand:

```bash
magpie settings set proxy http://127.0.0.1:7897
```

The deployment's own proxy instance is temporary: it starts with the
deployment and stops with it. A gateway that keeps that endpoint would reach
the vendors through a dead port, so the deployment writes it nowhere. Only the
exact URL the deployment started, while its `DEPLOY_PROXY_PID` is still
recorded, counts as that temporary instance. A proxy the device already runs
is preserved even on the deployment's usual ports (7890-7894): when the
deployment reuses one, `DEPLOY_PROXY_URL` names it but no PID is recorded, so
the apply writes it into the gateway like any other device proxy.

## Group semantics

`group/conductor` is the Claude Code group: `codex/gpt-6.2-sol` at medium,
then `openai/gpt-6.2-sol` at medium, then `kimi-code-cn/k3.1-pro` at max. It
does not contain GPT-6.1 Terra. Claude Code's auto-mode classifier is configured
separately as `codex/gpt-6.1-terra`. An isolated auto-mode check on this Mac
reached that model through Magpie; verify the route on each device before
applying, because an unavailable classifier causes checked actions to be denied.

`group/openai-stack` is the manual OpenAI stack that keeps Terra:
`group/chatgpt` (Codex Sol medium, Terra high), `openai/gpt-6.1-sol` medium,
`openai/gpt-6.1-terra` high, then Kimi max. `group/workhorse` is the Pi and
`dsh` group: MiniMax M3.1 Flash at max, then DeepSeek V4.1 Flash at max.
`group/chatgpt` holds the ChatGPT plan models at Sol medium and Terra high.

The four GPT auto groups route each model family across providers, Codex first.
The group IDs remain stable when a provider moves to a newer model:

- `auto/gpt-6.1-sol`: codex → openai → zed, all medium
- `auto/gpt-6.1-terra`: codex → openai, both high (the Zed Student plan refuses Terra)
- `auto/gpt-6-luna`: codex → openai → zed → opencode go, agent effort
- `auto/gpt-6-astra`: Codex 6.2 Astra → OpenAI 6.2 Astra, agent effort

The Luna router retains its catalog members, but Codex, OpenAI, and OpenCode Go
currently do not expose their Luna models in the GUI selections. An apply
therefore reports that router as incomplete until those models are picked.
The remaining groups are available to all three agents; only the default
differs. The picked list puts the preferred provider-prefixed models beside
the groups, so a failed route can be replaced by an exact provider/model on
the spot. A group member's `:effort` fixes the reasoning for that route; a
directly picked model uses the agent's own thinking level.

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

### DSH compaction

Magpie's CLI owns DSH's compaction model field. The deployment reads and sets
it only through `magpie dsh compact_model` and never edits
`~/.dsh/profiles/*/cordis.patch.yml`, so the field stays Magpie's and the DSH
profile keeps its operator-owned content. The apply backs up the previous
value before writing a new one and leaves it byte-for-byte when the choice is
already correct.

DSH compaction uses a fixed lightweight route, `group/workhorse` (the
`MAGPIE_DSH_COMPACT_TARGET` in `deployment/magpie.sh`), independently of the
group the enabled `dsh` wiring row starts its sessions on. Moving the DSH
session to a different tier must not drag background summarisation up with it,
so the wiring row is a gate, never the value. The field is set only when the
`dsh` row in `deployment/magpie/wiring.tsv` is both enabled and Magpie-owned;
a parked, inherited, or repo-owned row leaves it alone. A bootstrap agent
selection that leaves `dsh` out also leaves its visibility, picked models,
wiring, and compaction field alone. The recorded wiring omits DSH in that case,
so a later selection including `dsh` wires it normally. A standalone apply,
such as `dotfiles-magpie apply`, declares no agent selection and keeps the
wiring row as its gate.

A read the deployment cannot parse is not an unset field: the getter fails
closed unless the CLI reports `default` or a `magpie/<provider-or-group>/<model>`
choice, so an unreadable answer never turns into a guessed setting.
`dotfiles-magpie status` reports the live field, not the recorded
`dsh-compact` intent: it prints `dsh-compact|group/workhorse` when the field
matches the fixed target, `dsh-compact|drift (<value>)` when it holds a
different value (including `default` when unset), and
`dsh-compact|unreadable` when the getter answer cannot be parsed. Drift or
unreadability fails the status; a gated field prints no compaction line. The
gateway applies the override only to requests it classifies as DSH compaction;
a rejected or unavailable route falls back to the original request, and the
setting alone does not prove that any request used a cheaper model. Runtime
routing is not verified here: the fixture drives a fake CLI and a loopback
gateway, so these checks prove the field and its preservation, not how a real
compaction turn is served.

## Rollback

When gateway migration needs a backup, a full bootstrap saves the client files
as they were before deployment changed them. The temporary snapshot is removed
when bootstrap exits. The backup is stored at
`~/.local/state/dotfiles/magpie/backups/<UTC>/` at 0600; the newest ten are
retained:

- `~/.claude/settings.json`
- `~/.pi/agent/settings.json`
- `~/.pi/agent/models.json`
- `~/.codex/config.toml`
- every `~/.dsh/profiles/*/cordis.patch.yml`
- `dsh-compact-model.txt`, the previous compaction model (0600)

To roll back a compaction choice, read `dsh-compact-model.txt` first. The
record may be blank, which means the previous field was unset: the pinned
CLI's `internal/cli/main.go` maps `default` to an empty field and the DSH field
setter clears it. For a blank record run `magpie dsh compact_model default`
to clear the override; for a non-blank record pass the recorded
`<provider-or-group>/<model>` ID to `magpie dsh compact_model
<provider-or-group>/<model>`. The DSH profile itself is never rewritten.
To roll back other files, copy a file from a backup over
the live one. The Codex configuration is never written by the deployment, and
every apply hashes it before and after the changes; a change aborts the run
and keeps the backup. `~/.local/state/dotfiles/magpie/state.tsv` records what
the last apply did: the providers, the groups with their model order, the
wiring, the proxy, the DSH compaction group, and the Codex guard verdict.

## Other platforms

The native Windows adapter plans and installs the pinned Magpie CLI by default,
but does not start or wire a gateway, configure providers, or migrate clients.
The Unix engine and catalogs stay out of the Windows home, and
`dotfiles-magpie` is unavailable there. Claude Code and Pi retain their
device-owned endpoints and models. The Windows CLI changes have not yet passed
PowerShell or native Windows verification; see `docs/WINDOWS_DEPLOYMENT.md`.

## The command

```bash
dotfiles-magpie apply       # apply the catalogs to the local gateway
dotfiles-magpie status      # gateway, proxy, plugins, providers, groups, visibility, guard
dotfiles-magpie providers   # the provider catalog and its credential sources
dotfiles-magpie test        # one tiny completion per model role
dotfiles-magpie test conductor.deepseek   # one role
dotfiles-magpie start       # start the native gateway and wait until it answers
dotfiles-magpie stop        # stop the gateway this deployment started
dotfiles-magpie install     # install the pinned native CLI release
```

`status` is read-only and exits non-zero when a required piece is missing.
`providers` prints the catalog with the state of each credential source and
never a value.

`apply` runs the same engine as the deployment step and wires the
Magpie-owned agents. The repo-owned Claude Code and Pi settings migrate
through the deployment's client-settings merger, which the standalone
command does not carry; it reports that it leaves them to the deployment.

### `dotfiles-magpie test`

`test [role…]` sends one completion to each requested model role, or to every
role in `models.tsv` when none is named. A role is tested through the **first
candidate the gateway serves**, resolved from `GET /v1/models`, so OpenCode Go
is tested through `opencode-go/deepseek-v4.1-flash` and never through its
Gemini API. Each role gets one `max_tokens: 16` turn against
`/v1/chat/completions` with `Authorization: Bearer magpie`.

The report is one line per role:

```
role|model|state|detail
conductor.deepseek|opencode-go/deepseek-v4.1-flash|ok|412
```

`detail` is the round-trip in milliseconds on success and the gateway's own
message on failure. The command exits non-zero when any role fails, and an
unknown role fails by name before anything is sent. It never runs
`magpie provider test`: a provider-level probe reports the provider's own
endpoints, and the routers hold specific models of it.

The check costs one short turn per role — a handful of tokens against each
provider in the chain, no streaming, no tools.
