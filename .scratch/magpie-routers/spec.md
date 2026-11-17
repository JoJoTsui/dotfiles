# Magpie router refresh

## Problem Statement

The Magpie gateway works, but the agent pickers still show every exposed model:
Claude Code, Pi and DSH each list 50-odd entries, so choosing the routed groups
is hard. The OpenAI API key added in Magpie is not part of any router, so a
ChatGPT quota exhaustion moves to Kimi or DeepSeek instead of the paid OpenAI
key. The catalogs cannot express a fixed reasoning level for a router member,
even though Magpie supports `provider/model:<effort>`. The Zed provider plugin
is installed by hand, and the provider-level test probes OpenCode Go's Gemini
endpoint instead of the DeepSeek model the routers actually use.

## Solution

- Add the `openai` provider and an `openai-stack` group:
  `chatgpt` weekly quota → `openai` API (sol, terra) → `kimi-code-cn/k3.1-pro:max`.
  `conductor` becomes the stack, so Claude Code drains the ChatGPT weekly
  window, then the OpenAI key, then Kimi at max reasoning. `workhorse` is
  unchanged (MiniMax → DeepSeek).
- Add a fifth catalog, `visible.tsv`, that narrows each agent to the groups it
  should see: `conductor,openai-stack` for Claude; `workhorse` for Pi and DSH.
  Stars stay Magpie's `pickedModels` device state; adding a provider id to a
  row exposes that provider's starred models.
- Add a `plugins.tsv` that pins and installs
  `@magpie-community/opencode-zed-auth@0.1.19`. The sign-in remains a human
  step (`magpie plugin login zed` or the app's Plugins page).
- Add `dotfiles-magpie test [role…]`, which sends a tiny completion to each
  model role's first live candidate. OpenCode Go is therefore tested through
  `opencode-go/deepseek-v4.1-flash`, never through its Gemini endpoint.
- Teach the group resolver `role:<effort>` (`none|minimal|low|medium|high|xhigh|max`):
  the effort is stripped for the role lookup and appended to the resolved
  model id, so `conductor.kimi:max` becomes
  `kimi-code-cn/k3.1-pro:max`. A group without a suffixed member keeps
  Magpie's `effort=agent` default.

## Catalogs

`providers.tsv` adds:

```
openai|openai|env:OPENAI_API_KEY|yes
```

`models.tsv` adds:

```
openai.sol|openai/gpt-6.1-sol|yes
openai.terra|openai/gpt-6.1-terra|yes
```

`groups.tsv` becomes:

```
chatgpt|chatgpt.sol,chatgpt.terra|drain|auto|yes|weekly ChatGPT quota
openai-stack|group/chatgpt,openai.sol,openai.terra,conductor.kimi:max|drain|auto|yes|weekly, then API, then Kimi max
conductor|group/openai-stack|drain|auto|yes|Claude Code
workhorse|workhorse.minimax,conductor.deepseek|drain|auto|yes|Pi and dsh
```

`visible.tsv` — `agent|names`, where a name is a group id or a provider id:

```
claude|conductor,openai-stack
pi|workhorse
dsh|workhorse
```

`plugins.tsv` — `name|source|version|enabled`:

```
zed|@magpie-community/opencode-zed-auth|0.1.19|yes
```

## Apply

- Validate the two new catalogs: known agents, group ids or provider ids,
  unique plugin names, a version, and no credential-looking value.
- Ensure the plugin before the providers: `magpie plugin list --json` and read
  `.loaded[].spec`; install with
  `magpie plugin add npm:@magpie-community/opencode-zed-auth@0.1.19` when the
  package is absent, and `magpie plugin on <name>` when it is loaded but off.
  A sign-in is not attempted.
- Resolve a group member by stripping an optional `:<effort>` before the role
  lookup, then appending it to the resolved model id. Validate the effort
  against Magpie's levels.
- After the groups, write each agent's visibility:
  `magpie visible <agent> <names>`. Do not enable `--only-picked`: it freezes
  the current list and would hide a model starred later. A visibility failure
  fails the apply.
- `dotfiles-magpie test` resolves each role's first live candidate from
  `/v1/models`, sends one `max_tokens: 16` completion, and prints
  `role|model|ok|ms` or `role|model|error|message`. `jq` is already a common
  tool.
- `status` reports `visible|agent|names` and `plugin|name|loaded|missing`.

## Testing

- Catalog validation for the new files and the `:effort` grammar.
- The fake Magpie records `visible` and `plugin` commands; the apply order
  asserts plugin → providers → groups → visible.
- The fake `/v1/models` serves the openai models; an `openai-stack` group
  resolves to `group/chatgpt, openai/gpt-6.1-sol, openai/gpt-6.1-terra,
  kimi-code-cn/k3.1-pro:max`.
- `dotfiles-magpie test` against a fake completion endpoint reports
  `conductor.deepseek|opencode-go/deepseek-v4.1-flash|ok`.
- The simulated t9k apply still renders no gateway values.

## Out of Scope

- The Zed sign-in itself; the plugin is installed, the browser login is the
  operator's.
- Magpie's `pickedModels` stars; the app owns them.
- OpenAI models beyond sol/terra; one `models.tsv` line adds another.
- A group-wide `effort=auto` classifier; the catalogs use `effort=agent` and
  per-member overrides.

## Seams

1. Catalog boundary: the four existing TSVs plus `visible.tsv` and
   `plugins.tsv`, validated before any `magpie` call.
2. Command boundary: `magpie_run` records every plugin/visible/group call for
   the fake.
3. Gateway API: `/v1/models` and `/v1/chat/completions` are the only endpoints
   the test command uses.
