# Git 历史、PR 与架构演变审计 — 2026-11-27

## 审计基准与方法

- 仓库：`https://github.com/JoJoTsui/dotfiles`
- 审计 revision：`598478f1bbb91de5666bc7dfb621461324675533`
- 审计时工作树：干净，`main` 与 `origin/main` 一致。
- 历史覆盖：609 个 reachable commits、69 个 merge commits、520 个 first-parent commits、16 个本地 archive tags、27 个 unreachable commit objects。
- PR 覆盖：GitHub REST `pulls?state=all` 与 `gh pr list --state all` 均返回 **0**；reachable commit subject 也没有 `(#N)`。本地 feature-branch merge 不是 GitHub PR。
- 当前架构覆盖：README、AGENTS、ADR、部署入口、catalog、legacy adapter、tests、native verifier、历史审计证据。
- 工具限制：此 checkout 没有 `.codegraph/` 或 Graphify graph；使用有界文本搜索、直接读源码、Git 历史与定向测试。
- 安全边界：未读取凭据、`.env`、auth store 或 session 内容；未安装包、未部署到真实 home、未改系统状态。

**结论先行：** 这个仓库不是“个人 dotfiles 上不断叠补丁”，而是经历了三次主导重构浪潮（Chezmoi/copy mode、portable profile deployment、provider/Magpie/Codex ownership），以及其间多次技能、Herdr、shell/proxy 所有权的局部替换，之后进入安全、状态证据和旧主机迁移的加固期。表面上重复的 Bash/PowerShell、三个 skill root、两次 settings merge、四个 Codex/Herdr 脚本，大多有真实职责边界。可清理项主要集中在**死元数据、孤立快照、过期文档和迁移完成后的单次兼容分支**；当前 T9K legacy 核心不能删。

**后续清理执行：** 根据所有者确认，已删除 Caveman CLI/gateway 历史实现与配置、旧 OpenCode V1 快照，并清理本报告列出的过期文档段落。Caveman standalone skills、skill selection 和 device-side `~/.caveman` 状态均保留。详细变更见文末“清理执行记录”。

---

## 1. 历史规模与“关键 PR”事实

| 项目 | 结果 |
| --- | ---: |
| Reachable commits | 609 |
| Merge commits | 69 |
| First-parent commits | 520 |
| 本地 archive tags | 16 |
| Remote tags | 0 |
| Remote branches | 仅 `main` |
| GitHub PRs | **0** |
| Unreachable commit objects | 27 |
| 含 PR 编号语法的 commit subject | 0 |

27 个 unreachable objects 主要是 amend、autostash 或同一 tree 的替代 commit，没有揭示第二套被放弃的架构。

月度分布：

| 月份 | Commits |
| --- | ---: |
| 2025-11 | 7 |
| 2025-12 | 28 |
| 2026-02 | 2 |
| 2026-09 | 30 |
| 2026-10 | 148 |
| 2026-11 | 394 |

2026-02-10 到 2026-09-23 的长空档是真实历史：早期是小型个人配置，之后集中完成 Chezmoi/Pixi 转换和 portable deployment。

由于没有 PR，本报告用**关键 commit、merge、ADR 和回归测试**作为设计意图证据。本地 `archive/integration/portable-deployment` 与 15 个 `archive/fix-*` tag 是集成里程碑，不在 GitHub 上。

---

## 2. 架构演变时间线

| 时间 | 关键 commit / merge | 类型 | 解决的问题与设计变化 | 当前状态 |
| --- | --- | --- | --- | --- |
| 2025-11-24 | [`6f154d9`](https://github.com/JoJoTsui/dotfiles/commit/6f154d9a73bc61f8d864ad193ee172ebb276bc69) | 起点 | 个人 dotfiles 仓库 | 历史基线 |
| 2025-12-11 | [`1e79945`](https://github.com/JoJoTsui/dotfiles/commit/1e79945e33580838c96bdbdbb89ef010fc18e08c)、[`4508008`](https://github.com/JoJoTsui/dotfiles/commit/4508008859fa865c789022b28b9e202778089bec) | 增量 | 共享 `.env_core`；手跑 home-link script | env 模型仍活跃；link 机制被取代 |
| 2026-09-23 | [`dd20bf1`](https://github.com/JoJoTsui/dotfiles/commit/dd20bf1c9d7c34415f34092d9e550cbd36676b78) | **架构替换 1** | Chezmoi source state、copy mode、模板、公共 bootstrap、Pixi | 当前基础 |
| 2026-10-13 | [`6826e3c`](https://github.com/JoJoTsui/dotfiles/commit/6826e3cb4f1df7c062af06d0d59e0abd24b16db9)、merge [`00963bac`](https://github.com/JoJoTsui/dotfiles/commit/00963bac7fde3b6f8bd4c22f1c4026ca81ae0beb) | **架构替换 2** | platform × role × architecture、隔离 plan/state root、working-tree apply、取消隐式系统修改 | 当前基础，ADR 0001/0004 |
| 2026-10-13 | [`255c401`](https://github.com/JoJoTsui/dotfiles/commit/255c401c1d17b856764a3eef57e77aaaba348198) | **架构替换** | canonical shell values 生成 POSIX/Nu；Nu 优先但保留脚本 shell | 当前，ADR 0002/0005 |
| 2026-10-13 | [`b7f506c`](https://github.com/JoJoTsui/dotfiles/commit/b7f506cca2b995e05879684fbdc6b6e03bf80302)、[`5f2b917`](https://github.com/JoJoTsui/dotfiles/commit/5f2b917e43258f762d3e14433c5505691dc512a3) | 初始实现 | selectable frozen Bun agents；105-skill vendored snapshot | agent 模型后来泛化；vendored skill 已删除 |
| 2026-10-13 | [`20132d5`](https://github.com/JoJoTsui/dotfiles/commit/20132d5d772c843c457ba849b82e27b8d1019bb0)、[`86d8057`](https://github.com/JoJoTsui/dotfiles/commit/86d80571db7b95b44c7a6a4fbb52b3da37240da4) | 功能/边界 | Atuin local-first history；preserving client-settings merge；CodeGraph 不自动 index | 当前 |
| 2026-10-13 | [`e4ff86d`](https://github.com/JoJoTsui/dotfiles/commit/e4ff86d089b45569e1b629eb94858d2bcebd6658)、[`6b6555c`](https://github.com/JoJoTsui/dotfiles/commit/6b6555cbfba30918512e9aa515e07211b88852c7)、[`584b5df`](https://github.com/JoJoTsui/dotfiles/commit/584b5df2b148c57a5c94205213c8e387580d5ebb) | 平台扩展 | native Windows、WSL、macOS adapter 与验证边界 | 当前 |
| 2026-10-28 | [`073c670`](https://github.com/JoJoTsui/dotfiles/commit/073c670524ced16204bd70ff28d6120d33a7c114) | **架构替换 3** | 899 个 vendored skill files → upstream source/ref/path + resolved lock | 当前 |
| 2026-10-28—11-01 | [`b6ab8ee`](https://github.com/JoJoTsui/dotfiles/commit/b6ab8eed7689a7611b7592388ab1d1b04b081bb4)、[`374156e`](https://github.com/JoJoTsui/dotfiles/commit/374156eccd3d2b1e508482b62cc4ff5f2cbff557)、[`82a9c01`](https://github.com/JoJoTsui/dotfiles/commit/82a9c012aca99e59f8de5e0211752df8fc818631) | 运维/兼容 | headless Mihomo、Herdr pane-correct Codex、legacy file-level apply | 当前；legacy 仅旧主机 |
| 2026-11-05 | [`9e3936a`](https://github.com/JoJoTsui/dotfiles/commit/9e3936a1248cacd647ac272716130a3c00da2dcf)、[`c40f975`](https://github.com/JoJoTsui/dotfiles/commit/c40f975eee7f0ce941fa1c0ddf7daed6e01e96be) | **架构替换** | macOS 只跑 Zsh；per-platform installer order | 当前，ADR 0007/0008 |
| 2026-11-05 | [`50fcf69`](https://github.com/JoJoTsui/dotfiles/commit/50fcf696f1631a5436884e22bd981cbb261cc6e4) | 临时例外 | exact-match Homebrew Codex adoption | **已被 ADR 0011 floor 取代** |
| 2026-11-07—09 | [`06ec59e`](https://github.com/JoJoTsui/dotfiles/commit/06ec59e394191ea5c7fcd6bf2141edc0ef54c99a)、[`757e7d2`](https://github.com/JoJoTsui/dotfiles/commit/757e7d255d985486a3adf4095190464ec5b4e383)、[`751d354`](https://github.com/JoJoTsui/dotfiles/commit/751d354fe520e88ab2e7707e1af8386f36e80ac3) | 迁移/退休 | RTK hook 退休、`libstdbuf.so` exposure 退休、Caveman gateway lifecycle 退休 | 前两者迁移-only；Caveman runtime 已 retired |
| 2026-11-16 | [`8ea7c79`](https://github.com/JoJoTsui/dotfiles/commit/8ea7c790c3764483736c88a8531d9c85734291ab)、[`e878a8a`](https://github.com/JoJoTsui/dotfiles/commit/e878a8a6d9d25c2a059c68f50c792f4b204e410f) | **架构替换 4** | device-owned version override；per-agent provider catalog | 当前，ADR 0010/0011 |
| 2026-11-17 | [`27577e6`](https://github.com/JoJoTsui/dotfiles/commit/27577e64d916c3fbe51b1fe04297fd1f15894692)、[`5247d3f`](https://github.com/JoJoTsui/dotfiles/commit/5247d3f3ef40accc347a350129e85c84f0ab7bf8) | **所有权替换** | Herdr 拥有 integration bytes；Magpie 成为 model gateway | 当前，ADR 0012/0014 |
| 2026-11-19 | [`6de16eb`](https://github.com/JoJoTsui/dotfiles/commit/6de16eba18183d626c2a26e8b964512eeab17d50) | **架构替换 5** | neutral Codex resume 保留 saved provider/model/effort | 当前，ADR 0015 |
| 2026-11-21 | [`647194d`](https://github.com/JoJoTsui/dotfiles/commit/647194d8f339a5fba9f26242c7770902d1b4cf26)、[`20c7823`](https://github.com/JoJoTsui/dotfiles/commit/20c7823723fbfb725520e8ee0d1b3e133b04f4ae)、[`b3f2bdf`](https://github.com/JoJoTsui/dotfiles/commit/b3f2bdfc8fc519d59aa40d7c370445a05b324a2f) | 生命周期加固 | ordered steps、intent/recorded/live 状态、Nu completion 单 owner、proxy 单决策 | 当前 |
| 2026-11-26—27 | [`17c66b0`](https://github.com/JoJoTsui/dotfiles/commit/17c66b0cd194c59ec359ddc15b3a98680edb1e32)、[`ad881c0`](https://github.com/JoJoTsui/dotfiles/commit/ad881c062348a05a076d74400c4d202bf40cdcbd)、[`598478f`](https://github.com/JoJoTsui/dotfiles/commit/598478f1bbb91de5666bc7dfb621461324675533) | 兼容加固 | reversible legacy launcher/skill/proxy/Magpie 修复；rsync `--delete` 边界 | 当前；legacy 分支仍服务真实主机 |

### 演变模式

1. **个人配置 → 可复制 source state**：`dd20bf1`。
2. **宿主类别 → 可组合平台/角色/架构**：`6826e3c`。
3. **分散拥有者 → catalog/ownership boundary**：skills、agents、Herdr、Magpie、Codex resume、Nu completion、proxy。
4. **2026-11-21 之后主要是加固**：symlink/collision、atomic write、retry、state evidence、legacy recovery，而不是新架构。

---

## 3. 当前架构分层

| 层 | 当前实现 | 职责 |
| --- | --- | --- |
| Source state | Chezmoi naming、`.chezmoiignore`、`.chezmoi.toml.tmpl`、`.chezmoidata.toml` | 定义 `$HOME` 目标、selectors、共享 shell values、copy mode |
| Public boundary | `bootstrap.sh`、`bootstrap.ps1` | CLI/env precedence、read-only plan、隔离 roots、ordered dispatch、failure status |
| Source apply | Chezmoi init/apply、`client-settings.sh`、`merge.tmpl` | 应用 working tree；runtime settings 单独 merge |
| Instructions/skills | `skills.sh`、`payload.sh`、`update_skills.py`、`skill_review.py` | pinned fetch、stage、copy、quarantine、inventory、prune、drift report |
| Tools/agents | `common-tools.tsv`、bundle catalogs、`providers.tsv`、manager/release catalogs | 版本、installer order、provider chain、launcher、state ledger |
| Runtime integration | `magpie.sh`、Herdr/Worktrunk hooks、proxy、shell/history/completion preparation | 在依赖就绪后 wire gateway、agent、shell、history、completion |
| Native discovery | `macos.sh`、`macos-targets.tsv`、Windows native copy | canonical source → 原生发现路径 |
| Legacy host | `deployment/legacy/*`、`dotfiles-host-up` | 维护 T9K symlink topology、增量文件、reboot dependency、migration |
| Verification | portable/native runners、`native_report.py`、deterministic suites | 区分 plan/render、network、synthetic runtime、native acceptance |

关键执行顺序（Unix full deploy）：

1. Magpie client snapshot（若启用）
2. managers
3. Chezmoi source apply
4. skill fetch/stage
5. payload copy
6. managed-skill prune/cleanup
7. client-settings merge
8. macOS discovery copy
9. macOS installer tier
10. common tools/bundles
11. agents → Worktrunk plugins → Herdr integrations → 第二次 client-settings merge
12. deployment proxy
13. Magpie apply
14. shell/history preparation
15. 显式 system/login-shell 动作

证据：`bootstrap.sh:132-166`、`deployment/agents.sh:1333-1345`。

---

## 4. 哪些设计是有意为之

| 设计 | 为什么存在 | 证据 | 删除判断 |
| --- | --- | --- | --- |
| Chezmoi copy mode + working-tree apply | config watcher 需要普通文件；验证必须覆盖未提交改动 | `README.md:8-34`、`tests/test_deployment.py` | 核心，不删 |
| platform 与 role 分离 | OS 行为与主机用途不能互相推断；SSH 不自动等于 remote-compute | ADR 0001、`deployment/profile.sh` | 核心，不删 |
| Bash 与 PowerShell 两个 public adapter | 原生路径、reparse point、PortableGit、`.cmd` launcher、native discovery 不同 | ADR 0004、`tests/verify_portable.py` | 不删；共享的是 catalog/语义，不是实现 |
| canonical shell model → POSIX/Nu adapters | 避免三套 shell 值漂移 | ADR 0002、`.chezmoidata.toml` | 不删 |
| agent provider catalog | provider ownership 决定 exact pin/floor、PATH、launcher 与 fallback | ADR 0011、`providers.tsv` | 不删 |
| skill catalog + lock + managed inventory | 一个来源、reviewed bytes、只删 deployment-owned directory | ADR 0013、`skill-clients.tsv` | 不删 |
| 三个 skill roots | shared tree + Claude/MiniMax copy 是客户端能力适配 | `skill-clients.tsv:15-21` | 不删 |
| 两次 client-settings merge | 第二次在 agent/Herdr installer 后运行，保证集成条目存活 | `bootstrap.sh:147-154`、`tests/test_herdr_integrations.py` | 不删 |
| Herdr-owned integration bytes | repo 只拥有 selection/order/check，不复制 Herdr 内部格式 | ADR 0012 | 不删 |
| Magpie 三方所有权 | repo intent / Magpie credentials+generated state / device Codex base config | ADR 0014/0015 | 不删 |
| 四个 Codex/Herdr 脚本 | launch+health、neutral resume、Herdr argv reporter、hook registrar 职责不同 | `tests/test_herdr_codex_restore.py` | 不删 |
| macOS/Windows native discovery copy | canonical source 与原生发现路径之间需要 publication layer | `macos-targets.tsv`、`deployment/windows.ps1` | 不删 |
| `steps` 与 `actions` 并存 | `steps` 是实际顺序；`actions` 是旧 plan schema，消费方尚未迁移 | `docs/DEPLOYMENT_BOUNDARY.md:52-57` | 可弃用，不能直接删 |
| Native report identity/scenario outcomes | skip/unavailable 不能冒充 native pass | `tests/native_report.py` | 不删 |

---

## 5. 哪些是历史遗留，哪些问题已不存在

| 旧问题/方案 | 历史来源 | 现在是否仍存在 | 残留性质 |
| --- | --- | --- | --- |
| exact-match Homebrew Codex | `50fcf69`、ADR 0009 | **不存在**；ADR 0011 改为 floor，above-floor 必须 adopt | 代码已删；只剩 stale docs/ADR 引用 |
| 105/899 vendored skill files | `5f2b917` | **不存在**；`073c670` 改为 upstream pinned catalog | 已删除，无运行时残留 |
| Caveman gateway runtime | `a677929`/`751d354` | **不存在**；standalone skills，device state 保留 | 两个历史 reference 文件可删；retirement tests 要留 |
| `rtk hook claude` | `06ec59e` | fresh home 不再生成 | 旧设备 retirement/migration code 仍需要 |
| `libstdbuf.so` executable exposure | `757e7d2` | fresh manifest 不再暴露 | 旧 Pixi registry migration + rollback 仍需要 |
| legacy `with-proxy --if-available` | `d0b39f0` | 新 launcher 支持；旧 T9K launcher 可能不支持 | 条件兼容，不能全局删 |
| 无条件 `/etc/bash.bashrc` link | 原始 link script | public bootstrap 已取消；系统动作必须显式且拒绝 simulated home | 仅 legacy relinker 保留 opt-in |
| WSL2 ARM64 native CI job | `7cb5e73d` | job 已删，因为无 runner | **证据缺口仍存在**，不是已解决 |
| DSH TUI headless adapter 不兼容 | 初始 DSH pins | **仍存在**：当前 `0.2.2-rc.5` + `0.20.2` 实测 `validated:false` | capability gate 必须保留 |
| `ANTHROPIC_SMALL_FAST_MODEL` deprecated | Claude 新 alias | 仍被 Magpie apply/status/policy/tests enforce，以兼容旧客户端 | 不是死配置；等最低客户端版本后再删 |
| Windows ledger 被 narrow apply 覆盖 | architecture plan 的旧问题 | **已修复**；Windows 保留 unselected rows | plan/doc 过期，代码不是包袱 |
| Linux proxy 顺序错误 | architecture plan 的旧问题 | **已修复**；当前在 Magpie/shell prepare 前执行 | plan/doc 过期，代码不是包袱 |

---

## 6. 可安全移除的历史包袱

### 6.1 现在可清理：无设备迁移、无运行时消费者

| 候选 | 证据 | 建议动作 | 必须保留 |
| --- | --- | --- | --- |
| `deployment/client-settings/policies.json:8-18` 的 `legacy-vscode` | 全仓唯一引用是定义自身；`targets.tsv` 和 legacy adapter 不选它；tests 无引用。实际 VS Code owner 是 `dot_vscode-server/data/Machine/settings.json.tmpl` | 删除 policy key；可加“每个 policy 必须被 target/adapter 选中”的测试 | 当前 VS Code template |
| `deployment/caveman.sh`、`deployment/client-settings/caveman.yaml` | 文件头明确 historical；bootstrap module 列表、targets、policies 均不引用；`tests/test_caveman.py` 验证的是“不得复活 gateway” | **已删除**；`docs/CAVEMAN.md` 已改为 skills-only | retirement tests、所有 device-side `~/.caveman` 状态 |
| `deployment/inventory/legacy-opencode.jsonc` | `git grep` 0 引用；inventory README 未列为历史输入；旧 V1/Headroom/Serena 形状已被 `opencode.jsonc.tmpl` 取代 | **已删除**，依赖 Git history | 当前 OpenCode V2 template |

Caveman 两项在“历史证据策略”上可以保留，但**技术上已无设备迁移阻塞**。这与仍活跃的 T9K adapter 不同。

### 6.2 现在可安全修正的文档包袱

这些不改运行时，但会误导维护者；本轮已清理：

1. `docs/MACOS_DEPLOYMENT.md`：exact-match Codex 已改为 ADR 0011 floor。
2. `README.md`：Magpie 平台范围已改为 macOS/Linux/WSL，native Windows 仅安装 CLI。
3. `README.md`、`docs/AGENT_INSTALLATION.md`：DSH 版本改引用 provider catalog，不再维护第二份 pin。
4. `docs/DEPLOYMENT_ARCHITECTURE_PLAN.md`：Windows ledger 与 proxy ordering 已标记 resolved，并链接当前测试。
5. `docs/adr/0013-single-owner-skill-library.md`：design selection 已注明后续转入 `auto`。
6. `docs/adr/0008-installer-order.md`：exact-match Codex 已标注由 ADR 0011 supersede。
7. 同时清理了 Caveman CLI/gateway 文档、AGENT_HEALTH/HERDR 的旧 Caveman preflight、macOS/WSL 的旧 agent 数、NEW_HOST_SETUP 的 deferred-DSH 措辞、AGENT_SETTINGS 的重复版本号和 DEPLOYMENT_DESIGN 的历史文档标识。

### 6.3 需要显式弃用/归档决策

| 候选 | 为什么不能立刻删 | 删除前置条件 |
| --- | --- | --- |
| `system/bash.bashrc` | README 仍称 manual payload；可能仍有 operator 手工复制 | 退役 README 条目，确认外部 runbook 不再复制；保留 `deployment/system/bashrc` |
| `dot_local/bin/executable_bat-modules` | 441-line 用户命令，无 runtime caller/test，但 README 和 `migrate-shell.py:FILES` 仍依赖 | 决定是否支持该命令；同步移除 migration set/docs/外部说明 |
| `docs/vscode-win-settings.jsonc` | stale manual Windows/GLM recipe，无 runtime reader，但 README/AGENTS 要求校验 | 明确弃用或归档，移除 README/AGENTS 引用 |
| `legacy-pixi-global.toml`、`legacy-bun-package.json` | 无 runtime consumer，但作为 migration/audit provenance | 明确 archive policy，更新 inventory README；Git history 可承载 provenance |
| `docs/drafts/portable-deployment/` | 16 个完成 tracker 文件、约 63KB、无外部入链 | 若接受 Git history 作为 archive，可删；否则移入明确 archive |
| `docs/DEPLOYMENT_DESIGN.md` | implementation 前设计快照，含七 agent、Codex from Pixi 等过时描述 | 标 historical/archive；当前 contract 指向 `DEPLOYMENT_BOUNDARY.md` 和 ADR |
| computed `DEPLOY_CLASS`、plan `class`、template `data.class` | 内部无 consumer，但 `DEPLOYMENT_BOUNDARY.md` 把 `DEPLOY_CLASS` 定义为 extension compatibility contract | 审计外部 installer/plan/template 消费者后独立弃用 |
| plan `actions` | tests、native verifiers、外部自动化仍消费；与 `steps` 在 restricted mode 不完全相同 | 消费方迁移到 `steps` 后删除；不能直接 `actions = steps` |
| `--class` / `DOTFILES_CLASS` | docs/tests/native verifier/direct-Chezmoi fallback 仍依赖 | 发布弃用窗口，迁移命令与测试；保留 `--profile t9k` |
| Magpie `windows-arm64` release row | Windows ARM 当前不支持，但 tests 明确要求该 seed row | 产品决策：保留未来 seed 还是删除；同步改 validator/tests/docs |
| `ANTHROPIC_SMALL_FAST_MODEL` | 当前 Magpie behavior 仍 enforce | 建立并验证最低 Claude Code 版本，再同步删 policy/wiring/status/tests |

### 6.4 需要设备/主机迁移证明

| 候选 | 当前仍服务的问题 | 删除证据 |
| --- | --- | --- |
| uutils alias retirement/backup | 旧 Pixi registry 可能仍有 command-by-command exposure | 每个 managed registry 已迁移、backup/rollback 验证、无旧 alias |
| legacy Nu vendor-loader takeover | 旧 macOS managed loader 可能仍引用旧 generation | 盘点 native/vendor loader，迁移到 canonical user loader，证明无旧引用 |
| `recover-history.py` WAL fallback | 未迁移 legacy home 缺 `history-local/enabled.json` | 所有 legacy home 有 marker、完整 snapshot、host-up 成功 |
| `migrate-shell.py` | legacy shell/resources 尚未全部对齐 | live shell 与 fresh render 一致，rollback window 关闭 |
| `deployment/legacy/*`、`dotfiles-host-up` | T9K live tree 仍 symlink-managed，reboot/runbook 依赖 | 主机退役或完成 copy-mode migration，替代 runbook 验收 |
| `legacy/agent-home.sh`、launcher/skill-root recovery | 11-26 新增，当前 targeted legacy update 仍依赖 | 无 symlink-managed agent home，recovery batch 已验证 |
| `home-links.tsv` 中旧产品 state roots | 记录真实持久用户状态，不是当前 agent catalog | 逐项 owner 确认产品退休/数据导出，不能因目录旧就删 |
| macOS discovery/loader 两个 writer | apply-only 与 standalone prepare 职责不同 | 先定义单 owner，保持 native Nu discovery 和 symlink safety |

---

## 7. 明确不应删除的设计

- **PowerShell adapter**：原生 Windows 语义无法由 Bash adapter 代替。
- **三个 skill roots**：客户端发现能力不同，不是三份 catalog。
- **两次 client-settings merge**：后一次是 Herdr/client installer 之后的修复点。
- **四个 Codex/Herdr 脚本**：launch、resume、report、hook registration 各自拥有不同契约。
- **superseded ADR**：决策历史；应标注 superseded，不应删除。
- **active legacy adapters**：当前唯一支持的 T9K symlink-home 变更路径。
- **DSH adapter capability gate**：当前版本仍返回 `validated:false`。
- **retirement/preservation tests**：它们证明旧集成不会复活，不是旧功能测试。
- **Mirror adapters、login/profile files**：POSIX/Nu/macOS 语义要求，不是重复。

---

## 8. 当前技术债，不是历史包袱

1. **Codex resume 的版本证据已更新。** 当前 Bun pin 与宿主 `codex --version` 都是 `0.172.0`。本次审计用当前版本重跑 `tests/codex_resume_runtime.py`，9/9 复核通过，并已把 `docs/MAGPIE.md` 的验证边界从 0.169.0 更新到 0.172.0；0.169.0 仍是最低支持版本，后续行为变化仍需重新验证。
2. **Windows Herdr trigger 缺失。** Unix `install_agents` 会调用 Worktrunk/Herdr integration；Windows `Install-Agents` 没有同等步骤。默认 Windows bundle 不安装 Herdr，但边界应明确。
3. **Windows device-owned version override 未实现**，这是已记录限制，不是可删分支。
4. **`dotfiles-host-up` 在 WSL 上硬编码 `DOTFILES_PLATFORM=linux`**，但 helper 也安装到 WSL；这是正确性问题。
5. **文档与 catalog 漂移**：Magpie 平台、DSH pins、exact-match Codex、design tag、已完成 architecture ticket。

---

## 9. 建议清理顺序

1. **已完成两项低风险源清理**：Caveman 两个历史 reference、`legacy-opencode.jsonc`；保留 Caveman retirement tests。`legacy-vscode` 仍是独立可选清理项，本轮未动。
2. **修正当前文档**：Magpie 平台、Codex floor、DSH pin 引用、已完成 architecture ticket。
3. **给 policy catalog 加引用覆盖测试**，防止新的死 policy 再次出现。
4. **显式弃用 manual payload/user command**：`system/bash.bashrc`、`bat-modules`、`docs/vscode-win-settings.jsonc`。
5. **盘点外部 plan/template 消费者**后，弃用 `DEPLOY_CLASS`/plan `class`/`actions`/`--class`。
6. **建立主机迁移清单**：Pixi registry、Nu loader、history marker、shell、agent launcher/skill root、T9K topology。
7. **最后才删除 legacy 核心**；fresh-home 测试通过不等于旧设备已迁移。

---

## 10. 验证记录

### 已执行

- 全历史、merge、tag、reflog、unreachable object 统计。
- GitHub PR API 与 `gh pr list --state all`：0 PR。
- 当前源码、docs、tests、legacy adapter 的交叉引用检查。
- 两组定向测试，共 **153 项完成且 OK，其中 6 项按环境跳过**：
  - `test_agent_payload.py`：19 OK（4 skip）
  - `test_macos_brew_first.py`：25 OK（2 skip）
  - `test_native_linux_verifier.py`：42 passed
  - `test_deployment.py`：25 passed
  - `test_cli_catalog.py`：5 passed
  - `test_caveman.py`：2 passed
  - `test_legacy_link.py`：24 passed
  - `test_legacy_history.py`：5 passed
  - `test_nu_completions.py -k legacy`：1 passed
  - `test_agents.py -k legacy_agent`：5 passed
- 当前宿主只读诊断：`dsh 0.2.2-rc.5`、`dst 0.20.2`、`dst cli capabilities --json` 返回 `validated:false`；`codex --version` 返回 `0.172.0`。
- `tests/codex_resume_runtime.py` 对当前 Codex `0.172.0` 通过，审计脚本复核 **9/9**：两个 saved-provider thread 的 provider/model/effort 保留；两个禁止场景按预期拒绝；PTY picker 恢复目标 thread；`base_config_unchanged=true`、`other_provider_preserved=true`。报告保存在 `/tmp/opencode/codex-resume-0.172.json`，未接触真实 Codex home 或 live gateway。

### 未完成/未执行

- 完整 `python3 -m unittest discover -s tests` 两次分别因 120 秒和 600 秒上限被终止，**未获得完整套件结论**。
- 未运行 native macOS/Windows/WSL runner、network installation、真实 home apply、系统修改。
- 未读取凭据或 device-private auth/session 数据。

完整套件超时不是通过；本报告的删除判断依赖静态可达性、历史证据和上述定向回归，而不是宣称全套验证通过。

### 本轮清理执行记录

所有者确认后，本轮完成了三项清理：

1. **Caveman CLI/gateway**：删除 `deployment/caveman.sh` 与
   `deployment/client-settings/caveman.yaml`；`docs/CAVEMAN.md` 改为 skills-only；
   同步移除 README、AGENTS、AGENT_HEALTH、HERDR、MACOS_DEPLOYMENT、
   LEGACY_HOME_LINKS 中的旧 CLI/gateway 操作说明。Caveman skills、catalog/lock、
   selection tests 和 device-side `~/.caveman` 状态保留。
2. **OpenCode V1**：删除零引用的
   `deployment/inventory/legacy-opencode.jsonc`；当前 V2 template、settings merge
   和 Headroom/Serena 清理行为不变。
3. **过期文档**：修正 Codex exact-match→floor、Magpie 平台范围、DSH 重复 pin、
   Windows ledger/proxy 已修状态、design skill selection、macOS/WSL agent 数、
   deferred-DSH 措辞、AGENT_SETTINGS 重复版本和 DEPLOYMENT_DESIGN 历史标识；
   将 Codex resume 正式文档更新到本轮验证的 0.172.0。

清理后重跑：

- `test_caveman.py`：2 passed。
- `test_skill_selection.py`：20 passed。
- `test_agents.py`：25 OK（3 skip）。
- 当前 OpenCode 2.4.2 实际 loader：`test_selected_opencode_accepts_rendered_config_with_managed_updates` 通过，确认 V2 配置可加载、Headroom provider/MCP 不再渲染、shared skill root 正确注册。
- 修改文档相对链接：119 个，0 missing。
- `git diff --check`：通过。

---

## 11. 关键来源索引

### ADR

- [0001 platform 与 role 分离](../../adr/0001-separate-platform-and-host-role.md)
- [0002 canonical shell settings](../../adr/0002-canonical-shell-settings.md)
- [0003 encrypted history](../../adr/0003-encrypted-shell-history-sync.md)
- [0004 platform runtime boundaries](../../adr/0004-platform-runtime-boundaries.md)
- [0006 pinned version one owner](../../adr/0006-pinned-versions-have-one-owner.md)
- [0007 macOS runs Zsh](../../adr/0007-macos-runs-zsh.md)
- [0008 installer order](../../adr/0008-installer-order.md)
- [0010 device version overrides](../../adr/0010-device-version-overrides.md)
- [0011 agent provider chain](../../adr/0011-agent-provider-chain.md)
- [0012 Herdr-owned integrations](../../adr/0012-herdr-owned-integrations.md)
- [0013 single-owner skill library](../../adr/0013-single-owner-skill-library.md)
- [0014 Magpie ownership](../../adr/0014-magpie-owns-the-model-gateway.md)
- [0015 neutral Codex resume](../../adr/0015-neutral-codex-resume-layer.md)
- [0016 shared proxy launcher](../../adr/0016-shared-proxy-launcher-interface.md)

### 当前合同

- [Deployment boundary](../../DEPLOYMENT_BOUNDARY.md)
- [Agent installation](../../AGENT_INSTALLATION.md)
- [Agent payload](../../AGENT_PAYLOAD.md)
- [Legacy apply](../../LEGACY_APPLY.md)
- [Magpie](../../MAGPIE.md)
- [Shared shell settings](../../SHARED_SHELL_SETTINGS.md)
- [Shared history](../../SHARED_HISTORY.md)
- [Complete verification matrix](../../verification/complete-matrix.md)
