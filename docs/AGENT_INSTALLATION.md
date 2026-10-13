# Bun-managed coding agents

Ordinary bootstrap installs Kimi Code, pi, OpenCode, Claude Code, and Codex.
`--agents all`, `--agents none`, or a comma-separated list selects which client
executables to install. Names are `kimi`, `pi`, `opencode`, `claude`, and
`codex`; `kimi-code` and `claude-code` are accepted aliases. Repeated names
are deduplicated in catalog order. Flags override `DOTFILES_AGENTS`.
Unknown/empty/mixed all-or-none selections fail before writing files.

CodeGraph is always selected, including with `--agents none`. Installation
never indexes a repository. Selection does not gate configuration, shared
instructions, or portable skills, and does not uninstall omitted clients.
Instruction/skill adapters deploy by default through the public bootstrap; see
[agent payloads](AGENT_PAYLOAD.md) for discovery and ownership.

```bash
bash bootstrap.sh --agents codex,kimi --plan
bash bootstrap.sh --agents none
# Install/update selected clients with an already available toolchain.
bash bootstrap.sh --agents-only --agents claude,codex
```

`--agents-only` applies the working source and installs selected packages. It
skips common installation and shell preparation and requires pinned Bun/Node
already exposed under `~/.pixi/bin`. It conflicts with `--apply-only`. Its
completion message describes only file/agent deployment. Absolute
`DOTFILES_BUN_BIN` and `DOTFILES_NODE_BIN` paths can supply read-only runtimes
at the exact catalog versions for isolated checks. Package caches and client
state/config roots still follow the designated `--home`.

## Ownership, versions, and lifecycle scripts

The portable catalog is `deployment/agents/catalog.tsv`. Each package has its
own exact `package.json` and real text `bun.lock`. A project under
`~/.bun/managed/<name>` installs with `bun install --frozen-lockfile`; an absent
lock is an error. Separate projects allow arbitrary selections while keeping
each manifest consistent with its lock. Locks contain upstream integrity
strings and foreign optional native payloads. Bun's
[lockfile](https://bun.sh/docs/pm/lockfile) and
[frozen installation](https://bun.sh/docs/pm/cli/install) are the supported
mechanism; a filtered monolithic manifest is not used.

| Selection | Exact package | CLI |
| --- | --- | --- |
| kimi | `@moonshot-ai/kimi-code` 2.1.1 | `kimi` |
| pi | `@earendil-works/pi-coding-agent` 1.2.0 | `pi` |
| opencode | `@opencode/cli` 2.0.27 | `opencode`, `opencode2` |
| claude | `@anthropic-ai/claude-code` 2.1.296 | `claude` |
| codex | `@openai/codex` 0.162.1 | `codex` |
| independent default | `@colbymchenry/codegraph` 1.6.2 | `codegraph` |

Only Bun owns desired Codex installation; Pixi does not declare Codex.
OpenCode has one selected distribution, without `opencode-ai`. Historical
inventories remain under `deployment/inventory`. Source application and project
installation preserve the device's unrelated global Bun registry and tools.
Real executable launchers under `~/.bun/bin` and `~/.local/bin` point to the
same project, preserve package-relative native resources, and prepend managed
Node/Bun paths. Omitted launchers are unchanged.

The common toolchain supplies Bun 1.3.11 and Node 24.21.0. Bootstrap checks both
exact versions and catalog minimum Node versions, then executes each selected
CLI's `--version`. A failing install or diagnostic returns its nonzero status
and package step. Pin changes require compatible manifests, locks, engines,
and runtime diagnostics; a package-manager exit alone is not acceptance.

The deliberate lifecycle trust list contains Kimi Code, Claude Code, and
OpenCode. It does not enable broad `--trust` or arbitrary dependency scripts.
Kimi's optional `node-pty` is not trusted for Linux source compilation by
default. In shipped 2.1.1 `dist/main.mjs`, `BashTool` acquires only the process
capability and calls `HostProcessService`, which uses Node's
`child_process.spawn`; the sole `node-pty` import belongs to
`HostTerminalService.spawn` (lines 175629, 175662, 176725–176747 of the exact
[published package](https://registry.npmjs.org/@moonshot-ai/kimi-code/-/kimi-code-2.1.1.tgz)).
Terminal CLI/shell tools therefore do not require that optional binding.
The optional browser terminal's Linux PTY needs separately provisioned native
build prerequisites; these CLI checks do not establish its availability.
Mac/Windows PTY prebuilds ship in the locked optional package and need native
validation. Lifecycle scripts explicitly run in non-global mode so Kimi's
legacy global-shim takeover does not probe or rename host tools.

## Pinned client configuration

OpenCode 2 uses `providers`, `settings`, `package`, and nested `mcp.servers`.
The template was verified by 2.0.27's actual `opencode debug config` loader.
The exact [config schema](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.27/packages/schema/src/config.ts)
and [MCP schema](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.27/packages/schema/src/config/mcp.ts)
are authoritative; the unversioned public schema still described V1 at
implementation time. `codemode: false` preserves direct CodeGraph tools;
the default integration is enabled through the [settings merge](AGENT_SETTINGS.md).
Headroom uses the client's built-in
`@opencode/ai/providers/openai-compatible` adapter, avoiding a dynamic SDK
download. Its MCP remains disabled until that optional service is provisioned.
The historical Serena download command is preserved in the ignored inventory,
outside active configuration.

The exact [watcher schema](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.27/packages/schema/src/config/watcher.ts)
supports ignore patterns only. The old `watcher.enabled` had no effect;
remote compute profiles ignore all project update events (`**`), while
workstations ignore noisy directories. This filters events; it does not claim
the client's underlying watcher is disabled.

OpenCode uses `update: "disable"`, Kimi uses `[upgrade].auto_install = false`,
Claude sets `DISABLE_AUTOUPDATER=1`, and Codex disables its startup update
check. These are documented controls: [OpenCode config](https://dev.opencode.ai/v2/docs/config/),
[Kimi TUI preferences](https://moonshotai.github.io/kimi-code/en/configuration/config-files.html#tui-toml),
[Claude environment variables](https://code.claude.com/docs/en/env-vars), and
[Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference).
Actual Kimi `doctor config` and `doctor tui` validate rendered files without
logging in or making model requests. Pi and CodeGraph do not automatically
replace managed package pins through this installer.

## Evidence and remaining native checks

Deterministic public tests cover all/none/named selection, package failure
propagation, working-source application, and preserved global registries.
The explicit network test installs into a disposable Linux x86-64 home,
executes all six real CLIs, and repeats selections without deleting clients.
`DOTFILES_TEST_KIMI` and `DOTFILES_TEST_OPENCODE` enable actual pinned config
checks in ordinary test discovery.

```bash
DOTFILES_TEST_AGENT_INSTALL=1 \
DOTFILES_TEST_CHEZMOI=/absolute/path/chezmoi \
DOTFILES_TEST_BUN=/absolute/path/bun \
DOTFILES_TEST_NODE=/absolute/path/node \
python3 -m unittest discover -s tests -p test_agents.py -v
```

Native macOS/Windows/ARM execution remains separate CI acceptance. A
cross-platform lock proves resolution/integrity metadata, not execution of
foreign binaries or postinstall scripts. No account, credential, model request,
real shell history, or user-repository index is part of these checks.
