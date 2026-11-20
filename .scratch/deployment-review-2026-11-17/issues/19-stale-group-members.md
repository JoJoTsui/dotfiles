# 19: The gateway keeps a group whose members it no longer serves

Status: needs-diagnosis
Blocked by: 15 — the catalog decision comes first

**What to build:** a group the gateway holds must not name models the
gateway does not serve, and the status must say so when it does.

- [ ] `deployment/magpie.sh`: a group the gateway holds is reconciled with
      the models the gateway serves, so a stale membership is not left
      routing requests to models that cannot answer.
- [ ] The status reports a group that holds an unserved member as a finding,
      not as a normal group line.

## What the live verification found

The last apply recorded the group as empty:

```
group|auto-gpt-6-luna|
```

because the apply refuses to write a group whose member cannot be resolved.
The gateway still holds the membership an earlier apply wrote, and the live
status reports it as a healthy group:

```
group|auto-gpt-6-luna|codex/gpt-6-luna,openai/gpt-6-luna,zed/gpt-6-luna,opencode-go/gpt-6-luna
```

Three of those four ids are not in the gateway's model list. Only
`zed/gpt-6-luna` is served.

## Why the current behaviour is a trap

`magpie_group_models_for` returns nothing for a group with an unresolved
member, and the apply then leaves the group alone. The rule is right for a
group the deployment is about to write: a group must not promise a model
that cannot answer. The rule has a second effect it does not intend: it
leaves the *previous* membership in place, and the previous membership
promises exactly the models that were retired.

So the failure is silent in both directions:

- the apply reports the group as empty, which reads like "the group holds
  nothing" rather than "the group holds something stale";
- the status reports the group with four members, which reads like a healthy
  group, because the status reads the gateway's membership and does not
  compare it with the model list.

An agent that picks `auto-gpt-6-luna` from the picker routes to a group
whose first member is `codex/gpt-6-luna`, a model the gateway does not
serve. The request waits for a route that cannot answer.

## The two decisions

**What the deployment does with a stale group.** Three shapes:

- *Reconcile it*: compute the membership the catalog resolves to and write
  that, so the gateway's group matches the catalog even when a member is
  unavailable. The group then routes to what the gateway can serve. This
  keeps the deployment in charge of the routing, which is what the ownership
  table in `docs/MAGPIE.md` says.
- *Retire it*: remove a group the catalog cannot resolve, so the picker does
  not offer it. This hands the routing back to the gateway's own `auto/`
  ids.
- *Report it and leave it*: keep today's behaviour but make the status say
  "this group holds a member the gateway does not serve" so the operator can
  see it.

**What the status compares.** The status already fetches the model list for
the group lines. The comparison it needs is the group's members against that
list, and a group whose member is absent is a finding like any other
missing piece, so the status exits non-zero.

The reconcile-and-report shape does both and is the one the ownership table
points at: the repository owns which models a group holds, and the status
reports the device against the repository's intent. The operator decides.

## Where the code is

- `magpie_group_models_for` (`deployment/magpie.sh`): the resolution that
  returns nothing for an unresolved member.
- the group loop in `magpie_apply`: it writes a group only when the desired
  membership differs, and skips a group the resolution could not resolve.
- `magpie_status`: it prints `group|<id>|<members>` from the gateway's own
  answer, with no comparison against the served model list.

## What the source proves about the status half

The status cannot report an unserved member, and the reason is structural
rather than incidental.

`magpie_status` builds its `known` list from the **catalog**:

```bash
known=$(magpie_catalog_model_ids)
```

`magpie_catalog_model_ids` returns every model id the *repository's*
`models.tsv` names — the deployment's intent — not the ids the gateway
serves. The status never calls `magpie_models_fetch`, so it never learns
what the gateway actually serves. It then compares the gateway's group
membership against that catalog list, and a member the gateway does not
serve is a catalog member too, so the comparison finds nothing wrong.

The apply gets this right already. It fetches the live list first:

```bash
output=$(magpie_models_fetch "$MAGPIE_GATEWAY" || true)
...
live=''
for id in $(magpie_model_ids "$output"); do
    live="$live|$id|"
done
```

and resolves every model role against `live`, so a role with no live model
is `unresolved` and its group is reported incomplete. The status uses the
wrong input for the same question.

There is a second, smaller defect in the same area.
`magpie_group_models` is called with two arguments in both the apply and
the status:

```bash
current=$(magpie_group_models "$output" "$known")
```

but the function body uses only `$1`:

```bash
magpie_group_models() {
    printf '%s\n' "$1" | awk '...'
}
```

The second argument — the known model list — is never read, and the
function's own comment says the report "is read by looking for them". The
filter it was meant to apply is missing. Either the filter is implemented
or the parameter and the comment go.

## The measurement this ticket needs

The gateway's model list is the input, and it is already read by the apply
and by `magpie_test`. The comparison needs no new interface.
