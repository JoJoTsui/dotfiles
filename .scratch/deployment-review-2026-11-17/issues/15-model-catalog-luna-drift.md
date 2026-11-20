# 15: The model catalog names three models the gateway no longer serves

Status: ready-for-agent — closed on 2026-11-20: the Luna group and its
four roles are retired
Blocked by: none — found while executing the authorized apply of 2026-11-19

**What to build:** the repository's model catalog must name models the
gateway serves. The `luna` rows name three ids the live gateway retired, and
the group that holds them is dropped as incomplete.

- [x] `deployment/magpie/models.tsv`: the `chatgpt.luna`, `openai.luna`, and
      `opencode.luna` rows name candidates the gateway does not serve.
- [x] `deployment/magpie/groups.tsv`: the group `auto-gpt-6-luna` holds
      `chatgpt.luna,openai.luna,zed.luna,opencode.luna`, and one unresolved
      member makes the whole group incomplete, so the group is empty.
- [x] The catalog names the current ids, or the group is retired, so that the
      picker shows no empty group.

## What the authorized apply measured

The apply of 2026-11-19 resolved the roles against the live gateway and
reported:

```
dotfiles: magpie: the model role chatgpt.luna has no live model; skipped
dotfiles: magpie: the optional model codex/gpt-6-astra is not served; skipped
dotfiles: magpie: the model role openai.luna has no live model; skipped
dotfiles: magpie: the optional model openai/gpt-6-astra is not served; skipped
dotfiles: magpie: the model role opencode.luna has no live model; skipped
dotfiles: magpie: the group auto-gpt-6-luna is incomplete; one of its members has no credential
dotfiles: magpie: the group auto-gpt-6-luna holds
```

So the gateway does not serve `codex/gpt-6-luna`, `openai/gpt-6-luna`, or
`opencode-go/gpt-6-luna`. It does serve `zed/gpt-6-luna`: the role
`zed.luna` is not in the skipped list and `zed/gpt-6-luna` appears in every
agent's pick list.

The models the gateway did serve, as the apply resolved them:

| provider | live ids |
| --- | --- |
| codex | gpt-6.1-sol, gpt-6.1-terra, gpt-6.2-sol, gpt-6.2-astra |
| openai | gpt-6.1-sol, gpt-6.1-terra, gpt-6.2-sol, gpt-6.2-astra |
| zed | gpt-6.1-sol, gpt-6-luna |
| kimi-code-cn | k3.1-pro, kimi-for-coding |
| opencode-go | deepseek-v4.1-flash |
| minimax-cn | MiniMax-M3.1-Flash |

The catalog already names `gpt-6.2-sol` and `gpt-6.2-astra` for the conductor
and astra roles, so the repository's lineup is one generation ahead for those
providers and behind for the luna rows.

## Why the whole group disappears

`magpie_group_models_for` (`deployment/magpie.sh`) resolves every member and
returns nothing when one member's role is unresolved. That is deliberate: a
group with an unresolved member is incomplete and is not applied. The cost is
that the one live member of `auto-gpt-6-luna`, `zed/gpt-6-luna`, is dropped
with the three that are gone, and the agent's picker lists a group that holds
nothing.

The rule itself is not wrong: a group that promises a model the gateway does
not serve should not be created. What is stale is the catalog.

## Open question — answered on 2026-11-19

The gateway's own model list was read during the live verification, and it
answers the question directly. The gateway serves, on
`http://127.0.0.1:3425/v1/models`:

| provider | live ids |
| --- | --- |
| codex | gpt-6.1-sol, gpt-6.1-terra, gpt-6.2-sol, gpt-6.2-astra |
| openai | gpt-6.1-sol, gpt-6.1-terra, gpt-6.2-sol, gpt-6.2-astra |
| zed | gpt-6.1-sol, gpt-6-luna |
| kimi-code-cn | k3.1-pro, kimi-for-coding |
| opencode-go | deepseek-v4.1-flash |
| minimax-cn | MiniMax-M3.1-Flash |

The `luna` family is served by exactly one provider: `zed/gpt-6-luna`. There
is no `gpt-6.3-luna`, no renamed tier, and no second luna provider. The
gateway also serves an `auto/gpt-6-luna` id, which is the gateway's own
automatic routing for the family and not a catalog provider.

So the catalog cannot be repaired by substituting a newer id: the other three
providers do not expose a luna model at all. The catalog has two honest
options and the operator has to pick one:

- **narrow the group** to the one member the gateway serves, so the picker
  offers a group that routes to `zed/gpt-6-luna` and nothing else; or
- **retire the group** and its three dead roles, and let the picker offer the
  family through the gateway's own `auto/gpt-6-luna` id.

Narrowing keeps the repository's intent explicit. Retiring gives up the
repository's control of the family's routing. The catalog must not keep
naming model ids the gateway does not serve.

## The group the gateway still holds

The live status reports the group as the gateway holds it:

```
group|auto-gpt-6-luna|codex/gpt-6-luna,openai/gpt-6-luna,zed/gpt-6-luna,opencode-go/gpt-6-luna
```

while the recorded state of the last apply holds it empty:

```
group|auto-gpt-6-luna|
```

The gateway still holds the membership an earlier apply wrote. The current
apply refuses to update it, because a group with an unresolved member is
incomplete and is left alone rather than rewritten with a missing member.

The consequence is worse than an empty group: the picker lists the group,
the gateway routes to it, and three of its four members are models the
gateway does not serve. An agent that picks it waits on a route that cannot
answer. See ticket 19.

- 2026-11-20: Closed by retiring the group rather than by naming new ids.
  The Luna route is the gateway's own: it holds four members, three of them
  not served, and the deployment cannot repair a route it does not own. The
  row in `groups.tsv` and the four Luna roles in `models.tsv` are gone; the
  route is offered under the id the gateway publishes (`auto/gpt-6-luna`), so
  the picker shows a working route instead of an empty group.
