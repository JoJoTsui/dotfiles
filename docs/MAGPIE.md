# Magpie model gateway

Magpie is the model gateway this deployment runs. It listens on
`127.0.0.1:3425`, serves the OpenAI, Anthropic, and Gemini compatible APIs,
and routes every request to a **model provider**: a vendor account or API key
whose models the gateway serves under `provider/model`.

The repository owns the *intent*: which providers exist, which models each
routing group holds, and which agent uses which group. Magpie owns the
*credentials and the generated state*: the provider keys, the accounts, the
usage store, Pi's `models.json`, DSH's Magpie route, and Codex's separate
Magpie profile and model catalog. Codex's base configuration and authentication
remain device-owned; the deployment guards both files against changes.

## Ownership

| Owner | Owns | Never owns |
| --- | --- | --- |
| The repository | the eight catalogs, Claude Code's settings, Pi's default provider and model, the bootstrap switch, the Codex content guard | any credential, any generated agent file |
| Magpie | provider keys and accounts, the usage store, Pi's `~/.pi/agent/models.json`, DSH's Magpie route, Codex's `~/.codex/magpie.config.toml` and `magpie-models.json` | the intent: which models a group holds, Codex's base config and authentication |
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
for the role lookup and appends it to the model id the role resolves to, so
`conductor.kimi:max` becomes `kimi-code-cn/k3.1-pro:max`. A group reference
carries no effort, because a group keeps its own routing. A group without a
suffixed member keeps Magpie's `effort=agent` default.

A row names a group the deployment owns: the apply creates it and keeps its
members, routing and stays current. A gateway route the deployment only offers
is not a group and is declared in `families.tsv`.

### `families.tsv` — `name|id|purpose`

A gateway route the deployment offers in the pickers without owning it. The
gateway holds the route, its routing and its members; the deployment names it
and never writes it. `name` is the name `magpie visible` reports and accepts
for the route, and `id` is the model id the gateway publishes for it, the form
a client and the picker use. A visible row names the route by `name`, a picked
row by `id`, and the status reports the route under its `name` with the `id` it
must be published under.

### `wiring.tsv` — `agent|group|owner|enabled`

`owner` is `repo` when the deployment writes the agent's configuration by
hand, `magpie` when Magpie generates it, and `inherited` when the agent
follows another agent. Codex is wired only through Magpie's separate-profile
mode; Claude Code's settings remain repo-owned. An explicit bootstrap agent
selection excluding Codex preserves its profile, visibility, and picked models.
A standalone `dotfiles-magpie apply` has no selection and uses the enabled
catalog rows.

### `visible.tsv` — `agent|names`

`names` is a comma-separated list of declared group ids, Magpie provider
ids, and the names of the gateway routes in `families.tsv`. The apply runs
`magpie visible <agent> <names>` after the groups and
before the agent wiring, and only when the narrowing differs from what
`magpie visible <agent>` reports. It never passes `--only-picked`: that
freezes the current list and would hide a model starred later. A provider id
in a row lets that provider's picked models through; the exact set is
`picked.tsv`. `status` prints the live narrowing as `visible|agent|names`.

### `picked.tsv` — `agent|entries`

`entries` is the per-agent "only models I pick" list: a group entry is
`group/<id>`, a model entry is `provider/model`, and a gateway route is the
model id the gateway publishes for it. Every entry must be inside
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

1. Validate the catalogs, capture the content digests of Codex's base
   configuration and authentication, and preflight separate-profile collisions
   before installing a CLI or changing the gateway. The preflight refuses a
   linked or
   non-directory Codex home, a linked or non-regular profile or catalog path,
   a generated file with another name, a profile path whose link count cannot
   be read, and an unrecorded profile or catalog.
2. Ensure the gateway answers: `magpie status --json`. On the real account
   home the app is opened and waited for, and a headless host starts
   `magpie serve` and waits for it. A gateway that still does not answer
   fails the step with the command that fixes it; a platform without Magpie
   is skipped before this point.
3. Plan proxy, plugins, and providers; fail preflight for missing required
   credentials before changing gateway settings.
4. Select the separate Codex profile, before the gateway changes, the backup,
   and the provider registration: read the scope with the read-only getter
   `magpie codex scope`, and select it with `magpie codex scope profile` when
   it is not selected yet. The getter has to succeed and answer `Codex
   applies to default` or `Codex applies to profile`; a getter that fails
   stops the run even when it printed an answer. The pinned CLI refuses that
   change while the ordinary Codex integration is connected, so the run stops
   there; the deployment disconnects and retags nothing. The base
   configuration and authentication content digests are compared after the
   selection whether the command succeeded or failed, and the run reports a
   change rather than claiming the ordinary integration was preserved.
5. Back up client files and register a missing credential-free ChatGPT account
   provider, then check that Codex's configuration is unchanged.
6. Resolve the model roles against `GET /v1/models`. If this fails after the
   account provider was registered, the provider and backup remain; client
   wiring and recorded deployment state have not been changed.
7. Write the proxy when it differs and ensure the pinned plugins. `magpie
   plugin list --json` reports `.loaded[].spec`, so an absent package is
   installed and a loaded-but-off one is turned on.
8. Measure the ChatGPT account's allowance, before a group that drains the
   account is wired. `magpie accounts codex --json` reports each allowance
   window, its used and remaining share, and when it resets. A spent account
   is not a failure: the group drains to its next member. The run says so,
   because a group that looks healthy and serves a different member than the
   operator expects is the failure this avoids.
9. Ensure the groups: `magpie group add`, or `magpie group set` when the
   member order, the routing mode or the stay mode differs. The gateway's
   answer is compared on all three, so a group whose routing drifted is
   repaired instead of left as it is.
10. Write the per-agent picked list into Magpie's settings, only when it
    differs.
11. Narrow each agent: `magpie visible <agent> <names>`, only when it differs,
    and again for every agent whose picked list changed so the gateway serves
    the new list.
12. Wire selected Magpie-owned agents. For Codex, create a private profile
    placeholder before Magpie writes it, and verify the resulting profile and
    unchanged base config/authentication. Pi uses `magpie pi group/workhorse`;
    DSH uses `magpie dsh group/workhorse` only when selected.
13. Migrate the repo-owned client settings through the client-settings
    merger: Claude Code's gateway environment and `opus` alias, Pi's default
    provider and model. The step asks the merger whether the wiring would
    change a file before it backs up anything, so the backup holds the
    originals and a current device keeps its files and their modification
    times. The merge runs only after the gateway changes succeed.
14. Verify that DSH's official `llm-deepseek` row is unchanged and that both
    Codex's base configuration and authentication still hold the same content.
15. Write `~/.local/state/dotfiles/magpie/state.tsv` through a temporary file.

A run with nothing to change writes no files and keeps every modification
time.

## Codex: separate Magpie sessions

The separate profile leaves plain `codex` on the device's existing subscription
configuration. Start a **new** gateway session with:

```bash
codex -p magpie
```

The selected default is `group/openai-stack`; this is a separate invocation,
not a combined subscription/Magpie model picker. Magpie generates
`~/.codex/magpie.config.toml` and `~/.codex/magpie-models.json`. The profile
contains a gateway bearer credential and stays mode 0600. Keep its contents
out of terminal output, tickets, and Git. The deployment creates a private
placeholder because the pinned Magpie writer otherwise creates new files
with mode 0644.

Before its first write, apply refuses an existing unrecorded profile/catalog
or a symlink target. A successful apply records ownership; subsequent applies
validate the live provider, model, catalog reference, gateway URL, JSON
readability, and private profile mode rather than trusting recorded intent.
Excluding Codex leaves its files and gateway lists alone and retains its
last recorded ownership, so selecting it on a later apply does not make the
generated profile look like an unrecorded device file.

The preflight refuses a Codex home that is a symlink or not a directory, a
profile or catalog path that is a symlink or not a regular file, and a
generated file with another name. The pinned writer follows a symlink and
writes a file with other names in place, so both would change a file the
deployment does not own through an alias; the refusal keeps every alias's
bytes as they are. A profile path whose link count cannot be read is refused
as well: an unreadable count is not one link, so the run stops before it
changes anything rather than guessing. A device without a Codex home gets one
of its own: the deployment creates `~/.codex` privately (0700) and writes the
profile placeholder privately (0600), and never widens the permissions of a
home it finds. A recorded profile the pinned writer cannot parse is
preserved, and the run says so instead of overwriting it.

The scope is read with the read-only getter `magpie codex scope` and selected
with `magpie codex scope profile` before the gateway changes, the backup, and
the provider registration. The getter answers `Codex applies to default` or
`Codex applies to profile`; an answer the deployment cannot read stops the
run, so the installed Magpie CLI has to report the scope. The getter has to
succeed: an answer printed by a command that failed is not a scope, and the
run stops before the gateway changes. The pinned CLI refuses the selection
while the ordinary Codex integration is connected (`magpie: disconnect Codex
from magpie first, then change what it applies to`), so the run stops there
and leaves the ordinary integration as it is: nothing is disconnected,
retagged, or rewritten. The base configuration and authentication content
digests are compared after the selection whether the command succeeded or
failed, so a failed selection that still changed a file is reported as a
change, and the run only says the configuration and authentication are
unchanged when the comparison shows it. The deployment never writes the
ordinary configuration itself.

An interrupted write leaves `codex-profile.pending` under the Magpie state
root. Its fingerprints permit retry only while the generated files match
exactly and both targets still pass the ownership checks. Status shows
`wiring|codex|recoverable` with an instruction to rerun apply, even when
the interrupted run left a valid profile on disk. An unexplained edit or
deletion, an unrecorded collision, or an aliased target is reported as
`wiring|codex|blocked`. Inspect the protected backup and the reported
paths before resolving a block. Both states make status nonzero because
the apply has not established current ownership and wiring.

### Resume without switching a thread's provider

Resume a thread with the managed command:

```bash
dotfiles-codex-resume
```

It runs `codex resume --all --include-non-interactive`, so the picker lists
every working directory and the resumable Exec/AppServer threads. The
positionals are passed through and Codex reads them: without `--last` the
first positional is the session id and the second is the prompt; with
`--last` the thread is the most recent one and the first positional is the
prompt of that thread, exactly as `codex resume` reads it. A session id
together with `--last` is refused with a message that names the fix — drop
`--last` to resume that thread — because Codex would otherwise type the id
as the prompt. `--cd`, `--no-alt-screen`, and `--no-daemon` are passed
through as well; they change where the session runs, not which provider the
thread uses. Archived threads are not resumable and are not
offered. `codex exec resume` always sends resolved settings and is not a
substitute for this command.

The command adds a **provider-definitions-only** layer. It never sets
`model`, `model_provider`, or `model_reasoning_effort`, so Codex restores the
thread's own saved provider, model, and reasoning effort. The definitions come
from Magpie's own `~/.codex/magpie.config.toml` at run time: the deployment
never owns, copies, or persists the gateway credential. The provider table
reaches Codex as command-line configuration overrides, and the credential
reaches it through the environment with the provider's `env_key` mechanism, so
it never enters argv, a deployment-owned file, a log, a report, or this
repository. A base configuration that already defines `model_providers.magpie`
wins: the device's own definition is left alone. Without a Magpie profile the
command degrades to a plain resume and says so on stderr.

The two files it reads are refused when they are aliased, the same way the
deployment's Codex boundary refuses an aliased path: a symlink, a path that is
not a regular file, and a file with another name are never read through the
link. The command degrades to a plain resume with a message on stderr instead,
and it applies the same rule to a linked Codex home.

Plain `codex` keeps the subscription defaults for a new session, and
`codex -p magpie` keeps the gateway defaults for a new session. Neither is
changed by the resume command.

The Herdr-scoped launcher uses this command for a restore, because a thread
that saved another provider cannot be resumed by the plain route: `codex-herdr
resume <id>` runs `dotfiles-codex-resume --no-daemon <id>`, and a fresh
launch keeps the plain `codex --no-daemon` route. See
[Herdr](HERDR.md).

The command refuses the overrides that would defeat the preservation, with a
message that names it: `--model`, `--model-provider`, `-c model=…`,
`-c model_provider=…`, `-c model_reasoning_effort=…`, and `--profile`. They
are refused, not ignored. The key of a configuration override is compared the
way Codex compares it: Codex trims the key before it applies the override, so
`-c ' model = "gpt-6.1-sol"'` selects the very same setting and is refused as
well.

An override of the provider table the command owns, `model_providers.magpie.*`,
is refused as well. That table is derived from Magpie's own profile and the
gateway credential is attached to it, so an override of it would reroute the
thread away from its saved provider and would hand the credential to another
endpoint; the command appends its own definitions after the user's overrides,
so such an override would be overwritten in silence. A provider the command
does not generate is the user's own business: `-c model_providers.other.…`
still reaches Codex.

The command needs Codex 0.169.0 or newer and refuses an older one with a
message that names both versions. Below 0.169.0 the app server required the
saved provider of a thread to equal the provider of the current configuration,
so a neutral layer alone was not enough to resume a thread of another
provider. A newer Codex has to be checked again before it is claimed.

The command needs a `python3` with the standard-library `tomllib` module
(Python 3.11 or newer), because it reads Magpie's provider definition with
it. It resolves the interpreter the way the deployment resolves one
(`$MAGPIE_PYTHON`, `$DOTFILES_COMMON_BIN/python3`, `$PIXI_HOME/bin/python3`,
then `python3` on `PATH`) and refuses to start when no candidate has the
module: a guessed provider definition would reroute the thread through a
provider nobody verified.

**Verification boundary:** restoring a saved provider also requires its
definition in the effective configuration, and a selection layer would replace
the saved settings instead of restoring them. The synthetic runtime check
below establishes both facts for Codex 0.169.0. Existing session metadata
stays unchanged: the command neither retags a session nor writes into the
Codex home. These observations concern device Codex 0.169.0, which is also the
repository pin; another version needs its own check.

The synthetic run used a fresh Codex home, two fake loopback providers with
the Responses API over SSE, and threads with a different saved provider,
model, and reasoning effort each. The resumed turn reached the thread's own
endpoint with the thread's saved model and effort, while the two failures the
same run has to avoid were observed first: a saved-versus-requested provider
mismatch through the Magpie profile, and a Magpie thread without the provider
definition. The live gateway on `127.0.0.1:3425` was not part of the run: the
fake providers bound ephemeral loopback ports, and the real Codex home, its
sessions, and its authentication were never read. See
[the neutral resume layer ADR](../adr/0015-neutral-codex-resume-layer.md).

The interactive picker path is proven on a pty-capable host: the driver waits
for the picker to render, waits for the session list to load, accepts the row
the picker highlights, waits for the thread view, writes the prompt, and
submits it, each in a write of its own, because text and Return in one write
are read as a paste. The wait for the list is a step of its own, because the
picker renders in two stages: its header and its footer are on the screen
while the list is still loading ("Loading sessions…", the counter
"0 / 0… · 0%"), and a Return sent in that state accepts no row. The list has
rows when the picker shows its counter with a non-zero total ("1 / 4"). The
driver sends no arrow key: the picker orders the list and picks the
highlighted row itself, so no row of its own can be named, and no row is
claimed. The acceptance is a property: whichever row the picker highlights,
the resumed turn carries that thread's own saved provider, model, and
reasoning effort.
The synthetic home turns the startup update check off, so the update prompt of
a fresh Codex home cannot be accepted by the driver.

A turn produces more than one request at the provider: Codex sends a request
of its own for the thread title, and that request carries the configuration's
own reasoning effort. It is not the resumed turn. The check therefore asserts
on the request whose `prompt_cache_key` matches the thread's creation
request, and the auxiliary request is recorded separately. Every fake
provider is searched for that request: the picker may highlight a row of any
provider, and the turn of a thread of another provider reaches that
provider's endpoint, not the Magpie one.

The runtime class of `tests/test_codex_resume.py` is opt-in, because it needs
the real Codex CLI and a pseudo terminal. It runs with:

```bash
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v
```

The deterministic part of the suite (the fake-Codex unit tests) always runs,
and `tests/verify_portable.py` never starts the real CLI or a pty.

**Known limitation:** the credential reaches Codex through the environment, so
the shell commands the resumed agent runs inherit it, the same way the other
`env_key` providers of this device already do. The command does not override
`shell_environment_policy`: a merge would replace the device's own list
instead of extending it.

**Known limitation (model metadata):** the layer carries provider definitions
only, so a thread whose model the active catalog does not know — every Magpie
group id — runs with Codex's fallback model metadata, and Codex says so
(`warning: Model metadata for `magpie-only/group-openai-stack` not found.
Defaulting to fallback metadata; this can degrade performance and cause
issues.`). The fallback changes what Codex assumes about the model: the
context window it assumes, the model-specific tool modes, and the web search
tool. The routing still holds: the thread's own saved provider, its saved
model, and its saved reasoning effort are used as they were saved. The
catalog is not carried: `model_catalog_json` resolves a model by its exact
slug alone and replaces the active catalog for the whole process, so carrying
it would take the model metadata away from the other threads resumed in the
same run.

The profile adapter has synthetic tests, and the approved Magpie 0.1.4404
macOS ARM64 download matches the release-catalog digest. That payload was
executed in an isolated synthetic home, with fabricated configuration and a
fake gateway address, never against the device home, the live gateway, or a
real credential. The run checked the payload digest before executing any of
its bytes and asserted every outcome it claimed: the scope getter's answer
(`Codex applies to default`, `Codex applies to profile`), the pinned CLI's
refusal while the ordinary integration is connected (`magpie: disconnect
Codex from magpie first, then change what it applies to`) with the base
configuration unchanged, the preserved mode of a private placeholder, the
writer's in-place write over a file with another name, the refusal over a
profile it cannot parse, the unchanged content of the base configuration and
authentication around the profile write, the address the profile
names, and the number of requests the fake gateway received. The live port
appeared in no output and in no generated file. It did not establish live
gateway resume, and it is not application acceptance.

Primary sources: [Magpie's pinned profile adapter](https://github.com/yetone/magpie/blob/69233d6bcfda248a17b613a199e0f2735b0a3e08/internal/agent/codex_profile.go),
[Codex resume configuration](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/app-server/src/config_manager.rs#L521-L594),
and the installed Codex 0.169.0 `resume --help` output.

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
then `openai/gpt-6.2-sol` at medium, then `kimi-code-cn/k3.1-pro` at max. Each
Sol provider falls back to its 6.1 Sol when 6.2 is not served. It
does not contain GPT-6.1 Terra. Claude Code's auto-mode classifier is configured
separately as `group/workhorse`, the cheap group over two providers (MiniMax
M3.1 Flash, then DeepSeek V4.1 Flash). A classifier pinned to one provider's
model denies every checked action when that account is exhausted, which is
what happened on this Mac while the ChatGPT-plan quota was spent, so the
route is a group that drains to its next member. An isolated auto-mode check
on this Mac reached that route through Magpie; verify the route on each device
before applying, because an unavailable classifier causes checked actions to be
denied.

`group/openai-stack` is the manual OpenAI stack that keeps Terra:
`group/chatgpt` (Codex Sol medium, Terra high), `openai/gpt-6.1-sol` medium,
`openai/gpt-6.1-terra` high, then Kimi max. `group/workhorse` is the Pi and
`dsh` group: MiniMax M3.1 Flash at max, then DeepSeek V4.1 Flash at max.
`group/chatgpt` holds the ChatGPT plan models at Sol medium and Terra high.

The four GPT routes are each named once. Three belong to the gateway and the
deployment only offers them; the fourth is a group the deployment owns. The
gateway's routes keep the ids it publishes, and the deployment names them in
the pickers under those ids, so a picker entry is always an id the gateway
serves:

- `auto/gpt-6.1-sol`: codex → openai → zed, all medium
- `auto/gpt-6.1-terra`: codex → openai, both high (the Zed Student plan refuses Terra)
- `auto/gpt-6-luna`: codex → openai → zed → opencode go, agent effort
- `group/auto-gpt-6-astra`: Codex 6.2 Astra → OpenAI 6.2 Astra, agent effort; each
  provider falls back to its older GPT-6 Astra when it is available

`deployment/magpie/families.tsv` declares the three gateway routes: the name
`magpie visible` reports for each, the model id the gateway publishes for it,
and what the route is. The deployment offers them in the pickers and never
writes their routing, because the gateway owns it. The Sol, Terra and Luna
routes are the gateway's own, and the ids the deployment used for them
(`group/auto-gpt-6-1-sol` and its two siblings) are not model ids the gateway
serves: the gateway resolves those names to its routes and publishes them
under the ids above.

The Luna route holds members Codex, OpenAI and OpenCode Go do not currently
expose. The deployment does not own that route, so it neither repairs nor
reports its membership; the status reports the route itself, and reports a
group that holds an unserved member when the deployment owns that group. The
remaining groups are available to the catalog's four agents; only the default
differs. The picked list puts the preferred provider-prefixed models beside
the groups, so a failed route can be replaced by an exact provider/model on
the spot. A group member's `:effort` fixes the reasoning for that route; a
directly picked model uses the agent's own thinking level.

The template sets `model: opus` and maps the Fable, Opus, and Sonnet tiers to
`group/conductor`. The Haiku tier, legacy small-model alias, and auto-mode
classifier use `group/workhorse`; subagents inherit their parent model
unless the device sets its own override. Claude Code accepts the `opus` alias
and resolves it through `ANTHROPIC_DEFAULT_OPUS_MODEL`, so the gateway receives
the group.
Do not pick a bare `group/<id>` in `/model`: Claude Code rewrites an
unrecognized main model to a bare alias. A bare alias without the tier
mapping names an Anthropic model the gateway does not serve. Claude Code may
save its own alias (`sonnet[1m]`) after a run and append `[1m]` to a tier; the
sonnet tier still maps to `group/conductor`, and Magpie strips the marker.

A model role contributes the first candidate the gateway serves. `group/<id>`
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
so a later selection including `dsh` wires it normally. Status reports DSH as
excluded using the last applied selection instead of treating its unchanged
settings as drift. A standalone apply,
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
- `~/.codex/auth.json`
- `~/.codex/magpie.config.toml` and `~/.codex/magpie-models.json`, when present
- every `~/.dsh/profiles/*/cordis.patch.yml`
- `dsh-compact-model.txt`, the previous compaction model (0600)

To roll back a compaction choice, read `dsh-compact-model.txt` first. The
record may be blank, which means the previous field was unset: the pinned
CLI's `internal/cli/main.go` maps `default` to an empty field and the DSH field
setter clears it. For a blank record run `magpie dsh compact_model default`
to clear the override; for a non-blank record pass the recorded
`<provider-or-group>/<model>` ID to `magpie dsh compact_model
<provider-or-group>/<model>`. The DSH profile itself is never rewritten.
To roll back other files, restore the affected file from its protected backup,
retaining private permissions. A newly created Magpie Codex profile has no prior
file to restore: reconcile only the deployment-created profile/catalog and its
recorded ownership, preserving the base config, authentication, and all session
files. The separate profile's scope is Magpie's own preference: `magpie codex
scope` reads it, and `magpie codex scope default` puts the ordinary Codex
integration back in charge of what Magpie writes. The pinned CLI refuses that
change while the profile is wired, so the profile is disconnected first:
`magpie codex default` removes the generated profile and catalog, and `magpie
codex scope default` then returns the ordinary integration. Removing the
Magpie provider definition makes its threads unavailable until that definition
returns; it does not convert them to subscription threads.
The deployment never intentionally writes the base Codex configuration or
authentication. Every apply compares the parsed content of both before and
after the changes, so a configuration the device rewrote into another layout
is the same configuration and is not reported as a change; a real change
aborts the run and keeps the backup. The comparison needs a `python3` with
the standard library's `tomllib` module; without one the run falls back to
the byte digest, which is stricter, and says so once.
`~/.local/state/dotfiles/magpie/state.tsv` records what the last apply did:
the providers, the groups with their model order, the
wiring, the proxy, the DSH compaction group, and the Codex guard verdict.

A refused collision is not a rollback: the deployment leaves the file it found
as it is, so a profile or catalog with another name, a linked path, or a home
that is not a directory is still the device's own file after the refusal.

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
It reports the ChatGPT allowance as `allowance|chatgpt|<share> left|resets
<time>`, and reports a routing defect as a finding: a group the gateway does
not publish as `group/<id>`, a group that holds a member the gateway does not
serve, and a gateway route the deployment offers under an id the gateway does
not publish. Each finding fails the status, because a picker that offers a
route the gateway cannot serve is a silent failure.
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
