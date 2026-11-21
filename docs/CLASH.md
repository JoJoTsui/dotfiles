# Desktop proxy (Clash Verge)

The repository owns the routing policy of the desktop Clash Verge Rev app.
`clash/` holds reference copies of the app's profile enhancements; the
directory is chezmoi-ignored, so nothing in it is ever applied to `$HOME`.

## What is owned

| File | Clash Verge slot | Purpose |
| --- | --- | --- |
| `clash/Merge.yaml` | global merge config (全局扩展配置) | DNS policy and the Loyalsoldier rule providers |
| `clash/rules-enhancement.yaml` | per-profile rule editor (规则) | personal and managed rules, prepended to the subscription's own |
| `clash/groups-enhancement.yaml` | per-profile group editor (代理组) | the owned proxy groups, including `兜底` |
| `clash/script-enhancement.js` | per-profile script enhancement (脚本) | the final catch-all |
| `clash/imported/` | rule providers | domains copied from the subscription by intent |

`clash/generate-imported-rules.py` regenerates the imported buckets from a
subscription profile; it is the only writer of `clash/imported/`.

## The order the app applies them

Clash Verge applies a profile's enhancements in this order:

```
subscription rules -> rule editor -> group editor -> merge config -> script
```

Two consequences decide where the catch-all has to live:

- The rule editor **appends** after the subscription's own rules, and a
  subscription ends with its own catch-all (`MATCH,<the vendor's group>`). A
  catch-all added by the editor therefore sits behind that rule and can never
  match.
- The rule editor **deletes by exact string**, so the vendor's catch-all cannot
  be removed by name either: every subscription names its group differently.

The script enhancement runs last, so it is the only stage that can repair the
catch-all. `clash/script-enhancement.js` finds the catch-all by its rule type
and replaces it with the owned group, keeping every specific rule in order. The
rule editor therefore carries no catch-all of its own.

The rule type is the token before the first comma, trimmed, so a catch-all the
pinned Mihomo accepts in config-test mode (`MATCH ,DIRECT`) is recognized as
well. The whole token is compared, so a rule whose type merely resembles
`MATCH` stays a specific rule and keeps its place in the list.

## The invariant

The effective rules carry exactly one catch-all, it is the final rule, and it
routes to the owned group `兜底` (defined by `clash/groups-enhancement.yaml`),
where it can be flipped between a node and `DIRECT` at runtime.

If that group is missing from the profile's proxy groups, the script leaves the
rules alone: a rule naming an undefined group makes Mihomo refuse the whole
configuration, which is worse than the vendor's own catch-all.

A profile that carries no rule list is handled as an empty list, so the owned
catch-all is still the single final rule.

## Installing

The live copies live under
`~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/profiles/`.
For every profile that should follow this policy:

1. Copy `clash/Merge.yaml` into the app's global merge config (全局扩展配置).
2. Copy `clash/rules-enhancement.yaml` and `clash/groups-enhancement.yaml`
   into that profile's rule editor and group editor.
3. Copy `clash/script-enhancement.js` into that profile's script editor
   (脚本).

Every profile keeps its own copy, so repeat the three steps per subscription.

## Verifying

```bash
node --test clash/tests/
python3 -m unittest tests.test_clash_rules -v
```

The Node regression is offline: it composes the rule editor and the script over
vendor rule lists with different catch-alls, then checks the effective rules,
the retained order of the specific rules, and idempotence.

## Not this proxy

The headless Linux and WSL Mihomo instance is a separate deployment with its
own policy and its own lifecycle: see [the headless proxy](PROXY.md). The two
never share a configuration or a rule list.
