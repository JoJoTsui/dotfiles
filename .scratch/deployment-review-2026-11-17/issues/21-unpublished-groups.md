# 21: Three routing groups exist in the gateway but are not published as models

Status: ready-for-agent — closed on 2026-11-20: the ids the pickers offer
are served ids, the apply re-asserts the routing, and the status reports an
unpublished group as a finding
Blocked by: none — found while reading the live gateway's model list on
2026-11-19
Related: 22 — a name collision with the gateway's own family ids, which
discriminates the two explanations below

**What to build:** a group the picker offers must be a model id the gateway
serves.

- [x] The reason `group/auto-gpt-6-1-sol`, `group/auto-gpt-6-1-terra`, and
      `group/auto-gpt-6-luna` are absent from `/v1/models` while the gateway
      holds them is identified.
- [x] The apply re-asserts a group's `routing`, `stays`, and `listed` when
      they differ in the gateway, not only when its member list differs.
- [x] The status reports a group that the gateway does not publish as a
      finding.

## What was measured

The gateway's own model list, read during the live verification:

```
group/auto-gpt-6-astra
group/chatgpt
group/conductor
group/openai-stack
group/workhorse
```

The deployment's status, minutes earlier, reported eight groups, of which
three are absent from that list:

```
group|auto-gpt-6-1-sol|codex/gpt-6.1-sol:medium,openai/gpt-6.1-sol:medium,zed/gpt-6.1-sol:medium
group|auto-gpt-6-1-terra|codex/gpt-6.1-terra:high,openai/gpt-6.1-terra:high
group|auto-gpt-6-luna|codex/gpt-6-luna,openai/gpt-6-luna,zed/gpt-6-luna,opencode-go/gpt-6-luna
group|auto-gpt-6-astra|codex/gpt-6.2-astra,openai/gpt-6.2-astra
```

So the gateway *holds* the three groups — `magpie group <id>` answers with
their members — and does not *publish* them as servable model ids. The
status prints each as a healthy group, because it reads the membership and
never asks whether the id is servable.

## The mechanism the source already shows

The apply's group loop (`deployment/magpie.sh`, the `magpie-apply.groups`
step) decides whether to write a group by comparing **only the member
list**:

```bash
if magpie_group_present "$group"; then
    output=$(magpie_run group "$group" 2>/dev/null || true)
    current=$(magpie_group_models "$output" "$known")
    if [ "$current" != "$desired" ]; then
        change="$change
group-set:$group"
```

The write, however, carries four fields:

```bash
magpie_run group set "$group" "models=$desired" "routing=$routing" "stays=$stays" "listed=$listed"
```

`routing`, `stays`, and `listed` travel with the write, and **nothing in
the comparison ever reads them back**. `magpie_group_models` parses the
gateway's member lines; no function reads the gateway's `listed` value for
a group.

So a group whose members already match but whose `listed` is wrong in the
gateway is never corrected, and the deployment never notices.

`docs/MAGPIE.md` records the consequence: "`listed=no` keeps a group out of
the agent pickers while it stays reachable as another group's member, but it
also removes the models the group names from `/v1/models`."

That is a complete and testable explanation of the observation:

- `group/auto-gpt-6-luna` was never rewritten by the last apply. The apply
  reported it incomplete — `group|auto-gpt-6-luna|` is empty in the recorded
  state — because three of its four members resolve to models the gateway
  does not serve, so the resolution returned nothing and the loop skipped
  it. Its membership in the gateway is what an earlier apply wrote. See
  ticket 19.
- `group/auto-gpt-6-1-sol` and `group/auto-gpt-6-1-terra` were written, but
  only when their membership changed. If an earlier apply created them with
  a different `listed`, nothing since has corrected it.
- `group/auto-gpt-6-astra` **is** published. Its catalog row resolves to
  `codex/gpt-6.2-astra,openai/gpt-6.2-astra`, and `models.tsv` carries the
  optional candidate `codex/gpt-6-astra?` beside `codex/gpt-6.2-astra` for
  the `chatgpt.astra` role — the shape a catalog takes when the newer model
  replaced the older one. A group the apply rewrites gets the whole write,
  `listed=yes` included; a group whose membership did not change keeps
  whatever it was created with.

That is the pattern the hypothesis predicts: published where the apply wrote
the group last, unpublished where the group has not been rewritten since.
Two things keep it a hypothesis. Whether the last apply in fact rewrote
`auto-gpt-6-astra` is not recorded — the apply reports a group it wrote, but
the report of the run that wrote it is not in this tracker. And the gateway's
own answer for one of the three groups decides it outright.

## The measurement

One read of the gateway's own answer for one of the three groups, with its
`listed` field, compared with the catalog's row:

```bash
magpie group auto-gpt-6-1-sol
```

If the answer reports `listed=no` where `groups.tsv` says `listed=yes`, the
hypothesis is confirmed and the fix is the comparison below. Nothing is
guessed from the names.

Ticket 22 adds a second candidate reading of the same measurement. Read a
slash and a dot as dashes and the deployment's four group ids land on the
gateway's own four family ids; three of the four are unpublished, and the
three are exactly the ones that land on a family the gateway serves. If
this read reports `listed=yes` — the catalog's value, which the write
carries — then `listed` is not the cause and the correspondence is. If it
reports `listed=no`, the `listed` explanation is the simpler one and
stands.

The correspondence is a correlation, not a mechanism: a published group is
`group/<id>` and a native family is `auto/<model>`, so the two live in
different namespaces and no literal id collision is possible. Ticket 22
records the measurement that distinguishes the two readings.

### The confound in the recording above

The model list quoted at the top was fetched with a plain `curl` and no
`Authorization` header:

```bash
curl -s http://127.0.0.1:3425/v1/models | jq -r '.data[].id'
```

The deployment's own fetch sends a bearer credential:

```bash
magpie_models_fetch() {
    ...
    curl --noproxy '*' --fail --silent --show-error --connect-timeout 5 --max-time 20 \
        -H 'Authorization: Bearer magpie' "$gateway/v1/models" 2>/dev/null
}
```

If the gateway scopes its published model list by credential, the two
answers differ, and the recorded list is the unscoped one. That would
explain the whole observation without any drift in `listed` at all — so
the recording above is evidence, not proof.

The measurement must therefore use the deployment's own fetch, not a bare
`curl`:

```bash
source deployment/magpie.sh
magpie_models_fetch "$MAGPIE_GATEWAY" | magpie_model_ids
```

If that list contains `group/auto-gpt-6-1-sol`, there is no publication
problem: the bare `curl` sees a narrower view, the deployment sees the
right one, and the finding is about the credential the recording used
rather than about the groups. If it does not, the groups are genuinely
unpublished and the `listed` reading decides the cause.

Both branches are worth running, in that order: the fetch is cheap and it
distinguishes the two explanations before the CLI is consulted.

## What the fix is

Two independent changes, both in `deployment/magpie.sh`:

1. **The comparison covers the fields the write carries.** The gateway's
   answer for a group reports its `routing`, `stays`, and `listed`; the
   deployment must read them and issue a `group set` when any of them
   differs from the catalog, not only when the member order differs.
2. **The status compares against what the gateway serves.** Today
   `magpie_status` builds its `known` list from `magpie_catalog_model_ids`
   — the *catalog's* model ids — and never asks the gateway for its live
   list, so a group holding an unserved member cannot be reported. The
   apply already does this correctly: it fetches `/v1/models` first and
   resolves the roles against it. The status needs the same input. This is
   the same change ticket 19 asks for, and the two tickets should be fixed
   together.

There is also a dead parameter to remove while the code is open.
`magpie_group_models` is called as `magpie_group_models "$output" "$known"`
in both the apply and the status, and its comment says "the report is read
by looking for them" — the second argument is the known model list. The
function body uses only `$1`; the second argument is never read. Either the
filter it was meant to apply is implemented or the parameter and the
comment go.

## The consequence for the other tickets

- Ticket 19 (a group whose members the gateway does not serve) and this
  ticket are the same defect seen from two sides: the status reports the
  gateway's answer without comparing it with what the gateway can serve.
- Ticket 20 (the classifier route) depends on this one: pointing the
  classifier at `group/auto-gpt-6-1-terra` would point it at an id the
  gateway does not publish, which is the same failure as today's, with a
  different cause.
- Ticket 22 names a second candidate cause for all three: the deployment's
  group ids correspond to the gateway's own family ids. If that is the
  cause, the fix is to retire or rename the groups rather than only to
  widen the comparison, and the widening is still needed but is not
  sufficient.

## Comments

- 2026-11-20: The published model list, read from the live gateway twice —
  before the authorized apply and after it — with the same answer both times:

  ```
  auto/gpt-6-luna        auto/gpt-6.1-sol      auto/gpt-6.1-terra
  auto/gpt-6.2-astra     auto/gpt-6.2-sol
  group/auto-gpt-6-astra group/chatgpt         group/conductor
  group/openai-stack     group/workhorse
  ```

  The three groups the deployment declares as `auto-gpt-6-1-sol`,
  `auto-gpt-6-1-terra` and `auto-gpt-6-luna` are absent, and the four GPT
  families the gateway owns are present. The apply did not change that: the
  list is identical before and after it.
- 2026-11-20: The cause, from the same reads: the gateway answers the
  deployment's own ids with the *family's* id.

  | asked for | answered with |
  | --- | --- |
  | `auto-gpt-6-1-sol` | `auto/gpt-6.1-sol` |
  | `auto-gpt-6-1-terra` | `auto/gpt-6.1-terra` |
  | `auto-gpt-6-luna` | `auto/gpt-6-luna` |
  | `auto-gpt-6-astra` | `group/auto-gpt-6-astra` |

  The members, the routing (`drain`) and the stays (`auto`) are the same in
  every answer. So a group whose id names one of the gateway's own families
  is that family in the gateway's namespace — one object, published under the
  family's id — and `group/<deployment id>` is never a model id of its own.
  The astra group escapes because the gateway's astra family is
  version-stamped (`auto/gpt-6.2-astra`), so the name does not flatten onto
  it; that one stays a group and is published.
- 2026-11-20: `listed` is therefore not the cause. The gateway's answer
  carries `routing` and `stays` but no `listed` field, and the catalog's
  `listed=yes` was already in force for the three absorbed rows. The
  deployment's comparison reads only the member list
  (`magpie_group_models` parses the numbered model lines; `magpie_group_present`
  only checks that the group answers), so `routing` and `stays` are never
  compared and a stale value in the gateway survives an apply.
- 2026-11-20: The fix, in the order the evidence demands it:
  1. the deployment must offer ids the gateway serves — the three families
     under their own spelling (`auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`,
     `auto/gpt-6-luna`), which is ticket 22's ownership decision;
  2. the apply must re-assert `routing` and `stays` (and `listed`, which the
     gateway writes on `group add`/`group set`) when they differ from the
     catalog, not only the member list;
  3. the status must report a group the gateway does not publish as a
     finding, so a name the gateway does not serve can never pass silently
     again.

- 2026-11-20: Closed, all three parts. The pickers now offer ids the
  gateway serves: the three routes the deployment had declared as its own
  groups are offered under the ids the gateway publishes
  (`auto/gpt-6.1-sol`, `auto/gpt-6.1-terra`, `auto/gpt-6-luna`), and the
  device's picked list carries those ids instead of the `group/auto-gpt-6-1-*`
  ids the gateway never served. The apply compares a group's routing and
  stays as well as its member order, so a drifted group is repaired. The
  status reports a group the gateway does not publish, a group that holds an
  unserved member, and a route the deployment offers under an unpublished id
  as findings, and fails on them. On this device the status is green: five
  groups published, three routes published, no finding.
