# 22: The docs and the catalog spell the same four routing sets two ways

Status: ready-for-agent — closed on 2026-11-20: one spelling per routing
set, and the catalog offers the gateway's routes under the ids it publishes
Blocked by: none — found while reading `docs/MAGPIE.md` against
`deployment/magpie/groups.tsv` on 2026-11-20

**What to build:** one spelling per routing set, in the docs and in the
catalog, and every id the picker offers must be an id the gateway serves.

- [x] `docs/MAGPIE.md`: the four GPT auto groups are named with ids that
      exist in no catalog row and in no group the gateway holds.
- [x] `deployment/magpie/groups.tsv`: the four auto rows either keep the ids
      the documentation names, or the documentation names the ids the catalog
      uses. One of the two must give.
- [x] The relationship between the four deployment groups and the gateway's
      own four `auto/` families is established, so ticket 21's cause is
      known.

## What the source shows

`docs/MAGPIE.md` describes four GPT auto groups with slash ids:

```
- `auto/gpt-6.1-sol`: codex → openai → zed, all medium
- `auto/gpt-6.1-terra`: codex → openai, both high (the Zed Student plan refuses Terra)
- `auto/gpt-6-luna`: codex → openai → zed → opencode go, agent effort
- `auto/gpt-6-astra`: Codex 6.2 Astra → OpenAI 6.2 Astra, agent effort; each
  provider falls back to its older GPT-6 Astra when it is available
```

`deployment/magpie/groups.tsv` declares four groups with dash ids:

```
auto-gpt-6-1-sol|chatgpt.sol:medium,openai.sol:medium,zed.sol:medium|drain|auto|yes|GPT Sol: codex, openai, zed
auto-gpt-6-1-terra|chatgpt.terra:high,openai.terra:high|drain|auto|yes|GPT-6.1 Terra: codex, openai
auto-gpt-6-luna|chatgpt.luna,openai.luna,zed.luna,opencode.luna|drain|auto|yes|GPT-6 Luna: codex, openai, zed, opencode go
auto-gpt-6-astra|chatgpt.astra,openai.astra|drain|auto|yes|GPT-6 Astra: codex, openai
```

These are the same four routing sets. Resolving the catalog's roles through
`deployment/magpie/models.tsv` reproduces the doc's description member for
member and effort for effort:

| doc | catalog row | resolved members | doc's words |
| --- | --- | --- | --- |
| `auto/gpt-6.1-sol` | `auto-gpt-6-1-sol` | `codex/gpt-6.1-sol:medium`, `openai/gpt-6.1-sol:medium`, `zed/gpt-6.1-sol:medium` | codex → openai → zed, all medium |
| `auto/gpt-6.1-terra` | `auto-gpt-6-1-terra` | `codex/gpt-6.1-terra:high`, `openai/gpt-6.1-terra:high` | codex → openai, both high |
| `auto/gpt-6-luna` | `auto-gpt-6-luna` | `codex/gpt-6-luna`, `openai/gpt-6-luna`, `zed/gpt-6-luna`, `opencode-go/gpt-6-luna` | codex → openai → zed → opencode go, agent effort |
| `auto/gpt-6-astra` | `auto-gpt-6-astra` | `codex/gpt-6.2-astra`, `openai/gpt-6.2-astra` | Codex 6.2 Astra → OpenAI 6.2 Astra, agent effort |

The astra row is the sharpest: `models.tsv` gives `chatgpt.astra` the
candidates `codex/gpt-6.2-astra,codex/gpt-6-astra?` — the optional
candidate is the doc's "falls back to its older GPT-6 Astra" — and the
group row carries no `:effort`, which is the doc's "agent effort".

Neither spelling exists in the other file. `git grep "auto-gpt-6" -- docs/`
returns nothing; `git grep "auto/" -- deployment/magpie/` returns nothing.
The catalog's four ids appear in `groups.tsv`, `visible.tsv`, and
`picked.tsv` and in no document; the doc's four ids appear in
`docs/MAGPIE.md` and in no catalog row. Whether the gateway holds a group
under the doc's slash spelling is one of the measurements below, not a fact
the source settles.

The divergence has been there since the catalog was introduced. At commit
`8d78073` — the first commit whose `groups.tsv` carries these four rows —
the catalog already read `auto-gpt-6-1-sol` and the document already read
`auto/gpt-6.1-sol`. The two spellings were never one. The doc's astra id
was `auto/gpt-6-astra` from that first commit too; only its member
description later changed, when the catalog's astra role moved to
`gpt-6.2-astra`.

## Two readings, and the evidence for each

The doc's four ids and the catalog's four ids are the same names: read a
slash and a dot as dashes and all four correspond without exception.

| doc id | catalog group id | flattened onto |
| --- | --- | --- |
| `auto/gpt-6.1-sol` | `auto-gpt-6-1-sol` | `auto/gpt-6.1-sol` |
| `auto/gpt-6.1-terra` | `auto-gpt-6-1-terra` | `auto/gpt-6.1-terra` |
| `auto/gpt-6-luna` | `auto-gpt-6-luna` | `auto/gpt-6-luna` |
| `auto/gpt-6-astra` | `auto-gpt-6-astra` | `auto/gpt-6-astra` |

What the four ids *name* is what is open, and the source supports two
readings that call for different fixes.

**Reading A — the doc describes the deployment's groups, and misnames
them.** The evidence is the doc's vocabulary. `groups.tsv` explains that a
member "without one the group's default effort=agent applies", and the
doc's phrase for the luna and astra families is "agent effort" — the same
words, for the same property, on the two rows that carry no `:effort`. The
doc's per-member efforts ("all medium", "both high") are the catalog's
`:medium` and `:high` suffixes read one by one. And the doc's claim that
"The group IDs remain stable when a provider moves to a newer model"
describes the deployment's groups: `auto-gpt-6-astra` kept its id while its
member moved from `gpt-6-astra` to `gpt-6.2-astra`, which is what
`models.tsv` records (`codex/gpt-6.2-astra` with `codex/gpt-6-astra?`
beside it). Under this reading the documentation is simply misnamed, and
the fix is to correct `docs/MAGPIE.md` to the catalog's ids.

**Reading B — the doc describes the gateway's own four families, and the
catalog's four groups duplicate them.** The evidence is that three of the
doc's four ids are character-for-character the family ids the gateway
serves:

| doc id | served by the gateway | exact match? |
| --- | --- | --- |
| `auto/gpt-6.1-sol` | `auto/gpt-6.1-sol` | **yes** |
| `auto/gpt-6.1-terra` | `auto/gpt-6.1-terra` | **yes** |
| `auto/gpt-6-luna` | `auto/gpt-6-luna` | **yes** |
| `auto/gpt-6-astra` | `auto/gpt-6.2-astra` | no — the gateway version-stamps it |

Under this reading the repository maintains four groups that route each
GPT family across providers exactly as the gateway's own families already
do, and the fix is to retire the four rows and point the pickers at the
gateway's ids — the option ticket 15 already proposes for luna, applied to
all four.

The two readings differ in who owns the routing, which is the decision the
ownership table in `docs/MAGPIE.md` currently assigns to the repository
("the intent: which models a group holds"). They agree on the fact that
matters most: **the doc names four ids that exist in no catalog row.**

One discrepancy fits neither reading cleanly and is worth stating as a
fact about the records: the doc names the astra family `auto/gpt-6-astra`,
family-stamped like `auto/gpt-6-luna`, while the gateway's astra family was
read as `auto/gpt-6.2-astra`, version-stamped. The doc says the ids "remain
stable when a provider moves to a newer model", so the doc claims the
stable spelling and the live list shows a different one. One of the two
records is wrong, and the measurement below says which.

## The correlation this makes with ticket 21

Now compare each catalog group id, flattened, against the served family
ids:

| catalog group | flattened onto | a served family id? | published? |
| --- | --- | --- | --- |
| `auto-gpt-6-1-sol` | `auto/gpt-6.1-sol` | **yes** | **no** |
| `auto-gpt-6-1-terra` | `auto/gpt-6.1-terra` | **yes** | **no** |
| `auto-gpt-6-luna` | `auto/gpt-6-luna` | **yes** | **no** |
| `auto-gpt-6-astra` | `auto/gpt-6-astra` | no — the served one is `auto/gpt-6.2-astra` | **yes** |

Three of the four deployment groups flatten onto a family id the gateway
serves, and those three are exactly the three that are not published. The
fourth flattens onto `auto/gpt-6-astra`, which the gateway does not serve,
and that group is the one that is published. The split is exact.

That is a prediction, not a coincidence, if the gateway resolves a group id
that names one of its own families: the group and the family become one
route, published under the family's id (`auto/gpt-6.1-sol`), and the group
id the deployment knows (`group/auto-gpt-6-1-sol`) is never a model id of
its own. The astra group escapes because the gateway's astra family carries
the version in its id, so the flattened name lands on an id the gateway does
not hold.

The competing explanation is ticket 21's: the three unpublished groups
carry a stale `listed`, and the astra group was published because the last
apply rewrote it. That explanation needs a history — which apply wrote which
group — that the tracker does not record. The flattening explanation needs
none, and it predicts the astra exception from the id itself.

**The namespace caveat.** A published group is `group/<id>` and a native
family is `auto/<model>`, so their strings differ and no literal id
collision is possible. Any aliasing must therefore happen inside the
gateway, when it resolves a group id against the family ids it owns. That
is a mechanism the source does not show, so the tracker records it as the
hypothesis the measurement decides, not as a finding.

## The measurement that decides it

Three reads, all cheap:

```bash
# 1. the whole model list, split by namespace
curl -s -H 'Authorization: Bearer magpie' http://127.0.0.1:3425/v1/models |
    jq -r '.data[].id' | sort

# 2. a group the deployment declares
magpie group auto-gpt-6-1-sol

# 3. the same name in the gateway's family namespace
magpie group auto/gpt-6.1-sol
```

- Read 1 must capture the list **whole**, not filtered to `group/` ids. The
  `auto/` ids are the ones under test, and the record must say which of the
  four families the gateway serves and under which spelling — in particular
  whether the astra family is `auto/gpt-6-astra` or `auto/gpt-6.2-astra`.
- Read 2 gives the `listed`, `routing`, and `stays` fields of the
  deployment's group. If it reports `listed=yes` — the catalog's value,
  which the write carries — then `listed` is not why the group is
  unpublished, and the flattening explanation stands over ticket 21's.
- Read 3 is the discriminator. `magpie group` reads a **group**. If the
  gateway answers the slash form, the two ids name one object and the
  flattening is proven outright. If the gateway rejects the slash form as
  not a group — the expected answer, since `auto/gpt-6.1-sol` is a model id
  and not a group id — then the group and the family are separate, the
  flattening is coincidental, and the `listed` reading decides.

The astra id in read 1 settles the rest. If the gateway serves
`auto/gpt-6.2-astra`, the astra group cannot be an alias of a family, and
it is published for that reason. If it serves `auto/gpt-6-astra`, the
astra group should have been an alias too, and something else explains its
publication — which would make ticket 21's `listed` reading the right one.

## What the fix is

The fix depends on which answer comes back, and the operator decides:

- **If the gateway resolves the two ids to one route**: the deployment's
  four groups duplicate routing the gateway already owns, and the fix is to
  retire them and point `visible.tsv` and `picked.tsv` at the gateway's
  `auto/` ids — which is the option ticket 15 already proposes for luna,
  applied to all four. The cost is that the repository gives up describing
  the families' member lists and efforts, which the ownership table in
  `docs/MAGPIE.md` currently assigns to the repository ("the intent: which
  models a group holds").
- **If the gateway keeps them separate** and the `listed` field explains the
  three: the fix is to widen the apply's comparison to read back `listed`,
  `routing`, and `stays`, and to make the status compare against the
  gateway's live model list (ticket 21 and ticket 19).
- **Under either**: `docs/MAGPIE.md` must be corrected to one spelling, and
  the doc's list must name ids that exist. Today it names four that exist
  nowhere, and it claims the astra family's id is `auto/gpt-6-astra` while
  the gateway's astra family is version-stamped `auto/gpt-6.2-astra`.

## Why this is not a cosmetic drift

- `visible.tsv` and `picked.tsv` offer `group/auto-gpt-6-1-sol`,
  `group/auto-gpt-6-1-terra`, and `group/auto-gpt-6-luna` to every agent.
  Three of the four groups the picker offers are not servable model ids
  (ticket 21).
- The four catalog rows are the repository's declaration of the GPT family
  routing, and the document is where an operator would look to see what
  those families do. It currently names four ids the deployment does not
  create, under a spelling that matches the gateway's own families for
  three of the four.
- Ticket 20's decision — whether to point the classifier at a repository
  group or at the gateway's own family — cannot be made from the current
  documents, because the documents do not say which of the two the
  repository's groups are.

## Comments

- 2026-11-20: The device's own Claude Code settings carry a gateway-discovery
  capability list that names `auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`,
  `auto/gpt-6-luna`, and `auto/gpt-6-astra` — the document's four spellings —
  and names no `group/auto-gpt-6-1-*` id. That list is a third record of the
  same fact, from a different reader than the documentation and the catalog.
- 2026-11-20: The operator chose `auto/gpt-6.1-terra` as the classifier route
  for ticket 20, on the strength of that list and of the document's own
  description of the family. A route through the family is only useful if the
  family carries the routing the document describes — Codex first, then
  OpenAI — so the decision reads Reading B: the document names the gateway's
  families, and the catalog's four groups duplicate routing the gateway
  already owns. The measurement in step 6 of the operator script still
  decides it outright, and the astra id in step 5 settles whether the
  document's fourth spelling is right.
- 2026-11-20: The device's model picker offers `auto/gpt-6.1-sol`,
  `auto/gpt-6.1-terra`, and `auto/gpt-6-luna` beside
  `group/auto-gpt-6-astra` — two spellings of the same four routing sets in
  one list. That is the harm in its plainest form: an operator reading the
  device cannot tell which of the two names the deployment owns.

- 2026-11-20: The discriminator answered. The gateway answers the slash
  form, and answers the deployment's dash form with the same object:

  | asked for | answered with | published? |
  | --- | --- | --- |
  | `auto-gpt-6-1-sol` / `auto/gpt-6.1-sol` | `auto/gpt-6.1-sol` | yes, as `auto/gpt-6.1-sol` |
  | `auto-gpt-6-1-terra` / `auto/gpt-6.1-terra` | `auto/gpt-6.1-terra` | yes, as `auto/gpt-6.1-terra` |
  | `auto-gpt-6-luna` / `auto/gpt-6-luna` | `auto/gpt-6-luna` | yes, as `auto/gpt-6-luna` |
  | `auto-gpt-6-astra` / `auto/gpt-6-astra` | `group/auto-gpt-6-astra` | yes, as `group/auto-gpt-6-astra` |

  So the group and the family are one object in the gateway's namespace for
  the first three, and Reading B holds: the catalog's four rows reproduce
  routing the gateway already owns, and the deployment's pickers offer the
  name the gateway does not serve. The document's spelling is the served one
  for three of the four; its fourth, `auto/gpt-6-astra`, is wrong — the
  gateway's astra family is `auto/gpt-6.2-astra`, and the served astra route
  is the group `group/auto-gpt-6-astra`.
- 2026-11-20: One spelling per routing set therefore means: the gateway's
  own id for sol, terra and luna (`auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`,
  `auto/gpt-6-luna`), the group's id for astra (`group/auto-gpt-6-astra`),
  and the catalog's four duplicate rows retired. The document must name
  those ids, and the catalog must stop declaring rows the gateway collapses.
  This is the ownership decision the ticket was waiting for, and it is the
  operator's: the repository would stop owning the routing of these three
  families and would own only the astra group.

- 2026-11-20: Closed with Reading B. Each of the four routing sets is named
  once: `docs/MAGPIE.md` names the ids the gateway publishes
  (`auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`, `auto/gpt-6-luna`) and the
  deployment's own group (`group/auto-gpt-6-astra`), the catalog no longer
  declares the three routes the gateway owns, and the new catalog
  `deployment/magpie/families.tsv` declares the routes the deployment offers
  by the name the gateway reports and the id it publishes. The document's
  fourth spelling, `auto/gpt-6-astra`, was wrong: the gateway's astra family
  is version-stamped, and the served astra route is the group
  `group/auto-gpt-6-astra`.
