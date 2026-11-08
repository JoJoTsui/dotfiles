# T9K host deployment-match audit — 2026-11-08

This is the **before-alignment snapshot**. See the [completed alignment](AFTER.md) for the current remediation results.

The host is **not a full match** for this repository's T9K deployment. Its legacy persistence and current agent/proxy integrations are substantially prepared, but common tooling, shell resources, some owned settings and installer ownership still differ. No deployment alignment was performed.

Reference: `b7634032e81b56b318aee0af3fbc10b1bdbaf004` (already pushed to `origin/main`). Profile: `linux-remote-compute`, x86_64; all Linux-applicable optional bundles and all catalog skills included for comparison. The new glossary and standing newer-version rule are documentation-only working-tree changes. Source fingerprints and observation times are recorded in the linked evidence.

## Decisions

- Accepted scope: common defaults, every applicable optional bundle, all supported agents and global skills/settings/helpers. Missing optional items are conditional gaps, not required-default failures. The host has no managed profile file, so historical optional selection cannot be proven.
- **Always accept host tool versions newer than the repository pin.** No downgrade or deployment is needed solely because a version is newer. Older versions, missing tools, incorrect settings and demonstrated incompatibility remain distinct findings. The standing rule is in [AGENTS.md](../../../AGENTS.md#existing-host-audits).
- Exact bytes/versions, accepted newer versions, structurally compatible entries, intentional legacy differences, drift, missing items and unverified evidence are separate. A present executable is not proof of successful GUI/GPU/model behavior.
- This was an audit only. No package installation, sync, host configuration writes, services/agents/notebook restarts or project initialization took place. Chezmoi rendered only inside a scrubbed disposable home. The live integration adapter's `--check` was deliberately avoided because it writes scratch beneath live HOME.
- Client-settings parsing initially failed automatic approval review because of credential-bearing files. The rejected action did not run. User Q5 then explicitly authorized limited in-memory comparison of nonsecret settings; credential values were excluded from output, logs, reports and persisted copies. Standalone auth files and live .env values stayed excluded.

## Coverage and per-item results

Every row includes desired state, host observation, matching status, alignment recommendation and restart impact. These are **796 item/field checks**, not 796 independent defects: environments, aliases and their settings deliberately appear at their respective ownership layers.

| Report | Coverage | Checks |
| --- | --- | ---: |
| [Tools and versions](tools.md) | 30 common +77 optional environments; 140 declared aliases; eight agent packages; three managers; proxy, setup-on-use and 108 legacy exposures | 375 |
| [Files and persistence](files.md) | 63 visible source targets (60 intentional, three ignored bytecode artifacts), six generated shell resources, six completion modules, six process variables, 50 links, seven legacy apply targets | 138 |
| [Skills and instructions](skills.md) | 91 skills, 37 disabled names and 13 payload operations; 690 installed shared resource files fingerprinted | 141 |
| [Client settings](settings.md) | All 14 target files plus 119 nonsecret managed default fields | 133 |
| [Restart evidence](runtime.md) | Live agent state, saved restore metadata, proxy/gateway listeners, offline cache/codec, source persistence and serving proxy version | 9 |

## What needs alignment

| Area | Host finding | Deployment-match recommendation | Restart impact |
| --- | --- | --- | --- |
| Common tools | 19 exact, six accepted-newer, two missing, three older/different | Tailspin and Worktrunk were not found at inspected install locations. Less 643 vs704, system Python3.10 vs managed3.15.2, and uv-installed ty0.0.72 vs0.0.93 need separate decisions for full common-baseline alignment. Missing pip/Python aliases are included in tool rows. | These are not established blockers for the currently verified legacy restart flow. |
| Optional tools | 24 exact,12 newer accepted,21 legacy placements,13 missing,seven older | Align only capabilities actually selected/needed. Older: aardvark,mosdepth,picard,salmon,seqkit,awscli,gsutil. Every pin/observed version is in tools.md. | No automatic requirement to install all optional bundles before restart. |
| Agent packages/managers | Five agents newer accepted; Pi and CodeGraph exact; Qoder1.1.80 older than1.1.82. Pixi and Chezmoi versions exact; Rustup1.29.0 older than1.29.2. | Qoder/Rustup alignment recommended for full match. Existing Bun-global/native launcher topology differs from fresh managed projects. Pixi's version is exact but resolves through legacy Gizmo/Micromamba rather than its desired managed launcher. | Preserve working launchers during any future migration. No upgrade/downgrade performed. |
| System command ownership | 108 legacy uutils exposures remain, including system utility names and `libstdbuf.so` | Rehearse the existing catalog-driven namespacing migration; preserve unrelated aliases and keep its rollback backup. Do not delete wrappers individually. | Existing behavior persists; this is a deployment ownership mismatch, not a request to change utilities during restart. |
| Owned updater settings | Claude `env/DISABLE_AUTOUPDATER` missing; Codex `check_for_update_on_startup` missing; Kimi `upgrade/auto_install` differs | Three focused settings alignments recommended. Other device defaults/overrides remain preserved. | Policy drift, not a demonstrated restoration failure. |
| Shared skills | worktrunk and wt-switch-create absent from declared shared/client roots; Pi has28 distinct duplicate Lark directories | Prepare missing skills if full default coverage is wanted; separately reconcile duplicate Pi discovery entries after reviewing ownership. Qoder's duplicates alias the same shared resources, so native dedup remains unverified. | Graphify and graph guidance are ready; Worktrunk workflow/discovery completeness is not. |
| Skill provenance | Graphify's nine resources exactly match the reviewed Git commit;88 other installed skill names lack offline proof of the pinned source revision | No blind overwrite. Preserve installed bytes; validate provenance or fetch/reconcile through the approved deployment boundary later if exact source identity is required. | Evidence limitation, not proof the88 skills are broken. |
| Shell and desired-state files | Managed profile/Pixi desired manifests, multiple Nu modules, generated autoload files, history/shell preparation helpers and Zsh startup files are absent; other startup/mirror/Git/editor settings differ | Rehearse a separate legacy shell/settings migration. A whole-file hash difference alone does not justify overwriting personal settings. The documented legacy nu-login is intentionally retained. | The current legacy environment differs from a fresh T9K deployment. Do not run public bootstrap directly on this symlink home. |
| Proxy layout | Managed proxy script locations absent, but persistent `clash/scripts` alternatives exist; systemd user unit absent | Keep the documented notebook supervisor flow. Managed-path/systemd migration is optional. Local serving Mihomo version matches1.19.29; private profile semantics were not inspected. | Both Mihomo and Caveman listeners respond; previous preflight also verified proxied egress. No new external routing probe in this audit. |
| Persistence | All50 legacy links match. `.bash_logout` is an identical regular file on overlayfs, outside the link manifest | Persist/recreate this preference only if wanted immediately after restart. Its repo source survives; no unique configuration was identified. | That overlay copy may disappear; it is not an agent restoration dependency. |
| Source hygiene | Three ignored/untracked `__pycache__/*.pyc` files appear in Chezmoi's source inventory | Clean/exclude generated source artifacts in a separate source-only change before claiming a pristine full source application. None were removed by this audit. | No current runtime loss implied; fresh applies would include them. |

## What already matches

- All50 legacy home links, five of seven byte/mode legacy-apply targets, offline Graphify source and Chezmoi codec are present. The two remaining legacy targets are the documented retained nu-login and a byte-different codex-herdr wrapper; do not replace either blindly.
- All seven CodeGraph registrations, seven shared instruction blocks, two whole payload files, and the retired Kimi-block state match repository policy.
- All37 disabled DeepMind skills are excluded from inspected discovery roots, and Serena is inactive in all14 compared client configurations. No disabled resources were invoked.
- Graphify's official nine-resource payload is exact. The installed Graphify/CodeGraph command metadata is inventoried separately from skill bytes.
- Caveman's owned mount agrees with Pi's four live catalog model base URLs and the gateway's published runtime mount; selected Pi model and Codex/Caveman executable references are present.

## Restart decision

**Full deployment match: no. Restart preparation: no newly demonstrated deployment blocker, with the limits below.** This audit is broader than the earlier successful live `link-home`/health check; it distinguishes noncritical baseline drift from the small legacy startup path.

The final runtime snapshot has13 idle agents and one working agent. Finish any unrelated work before restart; the working pane may be this audit, but the report does not assume that identity. The persistent saved snapshot is valid and has one duplicate native reference that the existing host-up logic normalizes only while Herdr is stopped. No live snapshot was rewritten.

After notebook restart, run:

```bash
bash /t9k/mnt/joey/SHELL/dotfiles/deployment/legacy/link-home.sh
```

Only after `host stack ready`, attach from the laptop:

```bash
herdr --remote ssh://t9kuser@127.0.0.1:23331
```

This audit does not prove a fresh GPU allocation, post-restart network/provider availability, every client-native skill load, GUI/GPU capabilities, or the remote laptop's forwarding. No paid model probe, indexing, external egress request or restart was performed. Readiness observations are time-specific; the individual JSON files retain timestamps and input checksums.

## Evidence integrity

The [manifest](manifest.json) gives exact record counts and SHA-256 hashes of every published report/evidence file and reference input. Live private configuration values are absent. Source pin/default comparisons use the repository's declaration, not historical `deployment/inventory/legacy-*` desired state. The optional inventory selection and private previous-default baselines remain unknown.
