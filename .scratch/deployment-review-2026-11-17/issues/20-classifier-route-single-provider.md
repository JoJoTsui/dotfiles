# 20: The safety classifier is pinned to one provider's route

Status: ready-for-agent — closed on 2026-11-20: the change is committed as
`1c2e309`, the suite is green, and the device carries the new route
Blocked by: none — found while the same outage blocked the review itself
Related: 21 and 22 — the group's id may collide with the gateway's own
`auto/gpt-6.1-terra` family, which changes what the fix should be

**What to build:** the classifier and the auxiliary tiers must survive the
exhaustion of the account they are pinned to.

- [x] `deployment/client-settings/claude-settings.json.tmpl`: the classifier
      and the auxiliary aliases route through the gateway's Terra family,
      which carries a second provider, so a spent ChatGPT account does not
      take the whole tool-safety path with it.
- [x] The device's Claude Code settings carry the new route, written by the
      client-settings merge and not by a hand edit.

## What happened

From 14:17 on 2026-11-19 to the end of the review session, every command that
needed Claude Code's safety classifier failed:

```
codex/gpt-6.1-terra is temporarily unavailable (timed out), so auto mode
cannot determine the safety of Bash right now.
```

The read-only fast path kept working (`git rev-parse`, `echo`), and so did
`Read`. Every `Bash`, `Write`, `Edit`, `Agent`, and MCP call failed, which
is what left the worktrunk test unrun and the cleanup undone.

The template pins three settings to one model on one provider
(`deployment/client-settings/claude-settings.json.tmpl`):

```
"ANTHROPIC_DEFAULT_HAIKU_MODEL": "codex/gpt-6.1-terra",
"ANTHROPIC_SMALL_FAST_MODEL": "codex/gpt-6.1-terra",
"CLAUDE_CODE_AUTO_MODE_MODEL": "codex/gpt-6.1-terra",
```

`codex` is the ChatGPT-plan provider. `openai` is a separate provider with
its own API key, and the gateway serves `openai/gpt-6.1-terra` at the same
time. The apply wired Codex to `group/openai-stack`, whose first member is
`group/chatgpt`, and `group/chatgpt` holds `codex/gpt-6.1-terra` — so the
ChatGPT plan is spent first by the routing, and the classifier is the one
route that depends on it exclusively.

The effect is disproportionate. One account's weekly quota being spent makes
the *tool-safety* path of a developer tool fail, which in turn stops every
command in every session that uses it. The deployment reports
"the provider chatgpt is present", which is a statement about the account's
existence, not about its remaining quota.

## What the catalog already has

`deployment/magpie/groups.tsv` declares a group for exactly this shape:

```
auto-gpt-6-1-terra|chatgpt.terra:high,openai.terra:high|drain|auto|yes|GPT-6.1 Terra: codex, openai
```

Its routing mode is `drain`: spend a member's accounts until they are used
up, move to the next member, never return to an earlier one. That is the
behaviour the classifier needs — when the ChatGPT account is exhausted, the
route moves to the OpenAI account, and the safety classifier keeps
answering.

The work tiers already point at a group (`group/conductor`), so a group id
is a value Claude Code accepts for a tier. The classifier is the only one of
the three that names a single provider's model.

## The open question that has to be answered first

The gateway's own model list did **not** serve the group
`group/auto-gpt-6-1-terra`. It served:

```
group/auto-gpt-6-astra
group/chatgpt
group/conductor
group/openai-stack
group/workhorse
```

and not `group/auto-gpt-6-1-sol`, `group/auto-gpt-6-1-terra`, or
`group/auto-gpt-6-luna`, even though the deployment's status reports those
three groups as existing and holding members, and the recorded state holds
their members:

```
group|auto-gpt-6-1-terra|codex/gpt-6.1-terra:high,openai/gpt-6.1-terra:high
```

So the group exists in the gateway and holds the right members, but the
gateway does not publish it as a servable model. Until that is explained, a
change that points the classifier at the group would point it at something
the gateway does not serve — the same class of failure as ticket 19.

Two questions, and the second is the one that matters:

1. why does the gateway not publish `group/auto-gpt-6-1-terra` while it
   publishes `group/auto-gpt-6-astra` and `group/chatgpt`; and
2. does the gateway's own `auto/gpt-6.1-terra` id — which it *does* serve —
   already provide the cross-provider fallback, making the deployment's
   group redundant for this purpose.

`auto/gpt-6.1-terra` is in the gateway's model list and is not in any
deployment catalog row. If it is the gateway's built-in cross-provider route
for the Terra family, then the deployment's `auto-gpt-6-1-terra` group
duplicates it, and the fix for both this ticket and ticket 19 is to
understand the gateway's own `auto/` family before adding more groups.

The measurement is one read of the gateway's own answer about the group and
about `auto/gpt-6.1-terra`. It must not be guessed from the names.

## What ticket 22 adds to this ticket

Ticket 22 found that `docs/MAGPIE.md` describes the four GPT auto groups
under ids that are character-for-character the gateway's own family ids —
`auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`, `auto/gpt-6-luna`,
`auto/gpt-6-astra` — while `deployment/magpie/groups.tsv` declares the same
four routing sets under flattened ids, `auto-gpt-6-1-sol` and the rest. The
doc and the catalog have never agreed, and neither spelling exists in the
other file.

That makes this ticket's second question sharper. If the doc's ids are the
gateway's own families, then the deployment's `auto-gpt-6-1-terra` group is
a duplicate of the gateway's `auto/gpt-6.1-terra` family, and pointing the
classifier at the gateway's id would route through a family the gateway
already publishes and already owns — with no new group and no unpublished
id involved. If the doc's ids are a misnaming of the deployment's own
groups, then the deployment's group must be made publishable before it can
carry the classifier.

The discriminator is two reads:

```bash
magpie group auto-gpt-6-1-terra
magpie group auto/gpt-6.1-terra
```

`magpie group` reads a group. If the gateway answers the slash form, that
form names a group the deployment never created and the doc's ids are the
gateway's own. If the gateway rejects it as not a group — the expected
answer, since `auto/gpt-6.1-terra` is a model id and not a group id — then
the doc's ids are model ids the gateway serves, and the catalog's rows are
a duplicate of routing the gateway already owns.

Either way the change is one value in one template, mirrored in
`MAGPIE_CLAUDE_AUX_MODEL` in `deployment/magpie.sh`, and both must change
together — the constant is what `magpie_client_wiring_state` compares
against, so a change to one and not the other makes the status report drift
that does not exist.

## The decision that follows

Once the gateway's behaviour is known, there are two shapes:

- **point the classifier at a group** that the gateway serves and that has a
  second member, so the fallback is the deployment's own routing; or
- **point the classifier at the gateway's `auto/` family id**, and let the
  gateway own the cross-provider fallback.

The second hands the fallback to Magpie, which already owns its routing. The
first keeps the fallback in the repository's catalogs, where the deployment
can see and change it. The ownership table in `docs/MAGPIE.md` says the
repository owns "which models a routing group holds"; it does not say the
repository owns the gateway's internal routing. The operator decides.

Either way the change is one value in one template, mirrored in
`MAGPIE_CLAUDE_AUX_MODEL` in `deployment/magpie.sh`, and both must change
together — the constant is what `magpie_client_wiring_state` compares
against, so a change to one and not the other makes the status report drift
that does not exist.

## The outage, live on the device (2026-11-20)

The failure is not only historical. On 2026-11-20 the pinned route was still
`codex/gpt-6.1-terra`, and the denial was still happening:

```
codex/gpt-6.1-terra is temporarily unavailable (timed out), so auto mode
cannot determine the safety of Bash right now.
```

What the outage reaches, measured by trying each channel:

| channel | result |
| --- | --- |
| `Read` (any path) | allowed |
| `Edit` on a file inside the repository | allowed |
| `git rev-parse`, `git grep` (read-only) | allowed |
| `Bash` with `python3`, `curl`, `git status`, `git diff`, `ls` | denied |
| `Write` (any path) | denied |
| `Edit` on a file outside the repository | denied |
| `Monitor` (any command with a side effect or a network call) | denied |

So the denial is not a refusal of a particular command. It is the absence of
the classifier that every command with a side effect depends on, and it stops
the deployment work: the worktrunk test, the commits, the gateway
measurements, and the apply.

## What the device already knows about the routes

Claude Code's gateway discovery wrote a capability list into the device's
`~/.claude/settings.json`, and it names every model the gateway served at the
time. It includes `auto/gpt-6.1-terra`, `auto/gpt-6.1-sol`, `auto/gpt-6-luna`,
and `auto/gpt-6-astra`, and it names no `group/auto-gpt-6-1-*` id. The
device's own model picker offers `auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`,
and `auto/gpt-6-luna` beside `group/auto-gpt-6-astra` — two spellings of the
same four routing sets in one list, which is what ticket 22 is about.

Both facts matter here: the family id `auto/gpt-6.1-terra` is a served model
id, so a route through it is reachable today, and it is the id the gateway
publishes for the routing set the catalog calls `auto-gpt-6-1-terra`.

## The decision (operator, 2026-11-20)

The operator chose the gateway's own Terra family, `auto/gpt-6.1-terra`, for
the classifier and the two auxiliary aliases.

Why that one: it is a served model id today — Claude Code's gateway discovery
listed it in the device's capability list — so the route is reachable, and the
gateway's family routes Codex first and then OpenAI, so a spent ChatGPT
account no longer takes the tool-safety path with it. The alternative, a
direct `openai/gpt-6.1-terra`, answers today too but keeps the single-account
defect in a new place. Keeping `codex/gpt-6.1-terra` was the third option and
was declined: it is the route that produced the outage.

The change is one value in one template, mirrored in `MAGPIE_CLAUDE_AUX_MODEL`
in `deployment/magpie.sh`, and both must change together — the constant is
what `magpie_client_wiring_state` compares against, so a change to one and not
the other makes the status report drift that does not exist. The two
documents that name the route change with it, and the two test modules that
name it change with it:

- `deployment/client-settings/claude-settings.json.tmpl` — the three values
- `deployment/magpie.sh` — `MAGPIE_CLAUDE_AUX_MODEL`
- `docs/AGENT_SETTINGS.md`, `docs/MAGPIE.md` — the route the documents name
- `tests/test_magpie.py`, `tests/test_magpie_auxiliary_models.py` — the
  expectations that name it

The device still carries the old route until the apply runs; the merge is
the only writer of the device's Claude Code settings, so the change reaches
it through the authorized apply and not through a hand edit.

## What the fix must not do

- It must not make the classifier optional. A failed classifier denies
  actions; that is the safe direction, and the outage is the symptom of the
  problem, not the shape of the fix.
- It must not change the work tiers. Those follow the wired group, and
  ticket 16's second half (asking the gateway for the ChatGPT account's
  remaining quota before wiring a drain group to it) is the other half of
  this finding.

## Comments

- 2026-11-20: The measurement the ticket was blocked on, read from the live
  gateway: `magpie group auto/gpt-6.1-terra` answers with the id
  `auto/gpt-6.1-terra`, `routing drain`, `stays auto`, and the members
  `codex/gpt-6.1-terra:high → openai/gpt-6.1-terra:high`. The family
  carries a second provider, so the ticket's premise holds. It is also the
  gateway's own family: the deployment's row `auto-gpt-6-1-terra` answers as
  that family, which settles tickets 21 and 22.
- 2026-11-20: The change is committed as `1c2e309` on `fix/deployment-review`
  — the template, `MAGPIE_CLAUDE_AUX_MODEL`, both documents, and the four
  test expectations that name the route. The suite is green: 299 tests, 0
  failures, 0 errors. The authorized apply exited 0.
- 2026-11-20: The device now carries the new route, written by the
  client-settings merge and not by a hand edit:
  `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL` and
  `CLAUDE_CODE_AUTO_MODE_MODEL` are all `auto/gpt-6.1-terra`, and
  `magpie ls` reports the same three values for Claude Code.
- 2026-11-20: What the route does not fix today, measured against the live
  gateway: the family cannot answer while *both* its members are exhausted.
  `magpie accounts` reports the ChatGPT-plan account at 100% (`7d`, next
  reset 2026-11-21 07:12 UTC+8), and an OpenAI request answers "no credits
  remaining". A drain group does fall through an exhausted member —
  `group/conductor` (codex → openai → kimi-code-cn/k3.1-pro) and
  `group/openai-stack` both answered, through Kimi — so the family is the
  right route, and it will answer as soon as one of its two providers can.
  A new Claude Code session is denied every checked action until then,
  because the classifier's route is dark, not because it is pinned to one
  provider.


