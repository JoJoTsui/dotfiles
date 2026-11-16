# Imported rule buckets

Generated from the active subscription by `../generate-imported-rules.py`.
Do not edit these files; re-run the generator after a subscription update:

```bash
python3 clash/generate-imported-rules.py           # write
python3 clash/generate-imported-rules.py --check   # exit 1 when stale
```

Each file is a Clash rule-provider (`payload:` of `+.domain` entries) named by
intent, not by the subscription's own group name, so a rule can reference
`RULE-SET,ai,...` and keep working after switching subscriptions:

| bucket | source group | domains |
| --- | --- | --- |
| `ai.yaml` | 🤖AI网站 | AI products and their telemetry domains |
| `ads.yaml` | 🛑广告拦截 | ad networks and trackers |
| `media.yaml` | 🎬媒体解锁 | streaming services needing an unlock node |
| `proxy.yaml` | 🚀节点选择 | long tail the subscription routes through a node |

The subscription's DIRECT group is deliberately not imported: mainland direct
routing comes from `GEOIP,CN` and the Loyalsoldier direct lists, which cover
far more than one snapshot.

Headers record the subscription name and uid only. Subscription URLs and tokens
are never read, so they cannot leak into the repository.
