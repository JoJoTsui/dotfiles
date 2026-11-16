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

| bucket | source group | domains | wired |
| --- | --- | --- | --- |
| `ai.yaml` | 🤖AI网站 | 34 | yes → group `ai` |
| `ads.yaml` | 🛑广告拦截 | 564 | yes → `REJECT` |
| `media.yaml` | 🎬媒体解锁 | 241 | **no**, see below |
| `proxy.yaml` | 🚀节点选择 | 6,769 | yes → `PROXY` |

`media.yaml` is stored but not referenced: streaming unlock depends on which
node the subscription marks as unlocking, so the subscription's own
🎬媒体解锁 group must keep owning those domains. Routing them through an
auto-selected group broke Netflix while it was wired.

The subscription's DIRECT group is deliberately not imported: mainland direct
routing comes from `GEOIP,CN` and the Loyalsoldier direct lists, which cover
far more than one snapshot.

Headers record the subscription name and uid only. Subscription URLs and tokens
are never read, so they cannot leak into the repository.
