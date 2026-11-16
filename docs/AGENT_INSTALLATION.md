# Coding agent installation

Ordinary bootstrap installs Kimi Code, pi, OpenCode, Claude Code, Codex, and
MiniMax Code through frozen Bun projects, plus Qoder from a pinned native
release manifest. `--agents all`, `--agents none`, or a comma-separated list
selects which client executables to install. Names are `kimi`, `pi`,
`opencode`, `claude`, `codex`, `minimax`, and `qoder`; `kimi-code`,
`claude-code`, and `minimax-code` are accepted aliases. Repeated names are
deduplicated in catalog order. Flags override `DOTFILES_AGENTS`.
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
bash bootstrap.sh --agents-only --agents claude,codex,qoder
```

The managed `dotfiles-agents` command wraps the same boundary:

```bash
dotfiles-agents install all          # apply source, install selected agents
dotfiles-agents update claude,codex  # resolve pins, refresh locks, reinstall
dotfiles-agents status               # compare pinned and installed versions
```

`install` runs `bootstrap.sh --agents-only` (or `bootstrap.ps1` on native
Windows). `update` asks `deployment/update_versions.py propose-agents` for the
selected upstream versions, rewrites pins and regenerates Bun locks only when a
proposal exists, and then reinstalls through the same boundary. Vendor
self-updaters are not invoked. The working checkout remains the source of
truth, so the refreshed manifests and locks can be reviewed and committed.

## Updating a client CLI

The managed launchers own `~/.bun/bin/<command>` and `~/.local/bin/<command>`.
Bun's global installer links into the same directory and refuses to replace an
existing file, so `bun add -g @anthropic-ai/claude-code` fails with `EEXIST`.
The package still lands in `~/.bun/install/global/node_modules`, where it can
never run: the managed launcher keeps the command. Remove such a leftover with
`bun remove -g <package>`. The deployment reports every leftover it finds, and
`dotfiles-agents status` lists each copy with its version, the commands it
would provide, and the command that removes it.

Update a client through the wrapper instead. It resolves the upstream version,
rewrites the pin and its Bun lock, and reinstalls the selected clients:

```bash
dotfiles-agents update claude      # one client
dotfiles-agents update all         # every selected client
dotfiles-agents status             # pinned, device-owned, and installed versions
```

`update` never invokes a vendor self-updater and never edits the device's
global Bun registry. A device-owned version in
`~/.config/dotfiles/versions.tsv` stays in effect; `status` reports it as
device-owned rather than as a mismatch.

Lock generation requires the exact Bun pin from the common catalog. When a
proposal changes Bun-managed pins, `update` reuses the selected Bun only at that
version; otherwise managed Pixi supplies a separate cached runtime through
`pixi exec --spec bun==<pin>`. The command verifies that runtime before refresh
and leaves device Bun intact. Empty and native-only proposals need no lock
runtime. Normal macOS agent installation continues to accept compatible newer
Bun versions.

`--agents-only` applies the working source and installs selected packages. It
skips common installation and shell preparation and requires compatible Bun/Node
already exposed through the common command directory. macOS uses regular
`~/.local/bin` launchers and accepts the runtime catalog floors. Older Pixi
exposures remain usable before those launchers exist. Other platforms enforce
the exact runtime pins under `~/.pixi/bin`. It conflicts with `--apply-only`. Its
completion message describes only file/agent deployment. Absolute
`DOTFILES_BUN_BIN` and `DOTFILES_NODE_BIN` paths can supply read-only runtimes
satisfying the selected platform's version policy for isolated checks. Package caches and client
state/config roots still follow the designated `--home`.

## Ownership, versions, and lifecycle scripts

The provider catalog is `deployment/agents/providers.tsv`. One record per agent
and provider names the provider (`bun`, `native`, or `homebrew`), the package or
release, the package kind (the Homebrew formula or cask), the version, the
version policy, the exposed commands, the platforms it serves, its place in the
provider chain, whether the agent joins the named selection or is always
installed, the Herdr integration kind, the runtime floor, the lifecycle trust
list, the lock or release manifest, and the expected `--version` diagnostic.
`deployment/agents/herdr-kinds.tsv` lists the Herdr kinds a record may name.
Both bootstrap adapters read these files, so the catalog is the only source of
agent installation data.

The plan reports every selected agent with its provider, version policy,
effective version, commands, and Herdr kind. The provider it names is the first
one in the agent's chain that can serve the platform, and the entry describes
that provider. A Homebrew entry names the Homebrew package and its package
kind (`formula` or `cask`) and reports `manager` `homebrew`. A Bun entry names
its package, its minimum Node, and its lock. A native entry names its release
manifest. An installer-owned entry never carries a deployment-owned lock.
The deployment-owned project of an installer-owned agent stays visible as the
entry's explicit `fallback` field, with its own provider, package, minimum
Node, and lock.

Each Bun package has its own exact `package.json` and real text `bun.lock`. A
project under
`~/.bun/managed/<name>` installs with `bun install --frozen-lockfile`; an absent
lock is an error. Separate projects allow arbitrary selections while keeping
each manifest consistent with its lock. Locks contain upstream integrity
strings and foreign optional native payloads. Bun's
[lockfile](https://bun.sh/docs/pm/lockfile) and
[frozen installation](https://bun.sh/docs/pm/cli/install) are the supported
mechanism; a filtered monolithic manifest is not used.

| Selection | Exact package | CLI |
| --- | --- | --- |
| kimi | `@moonshot-ai/kimi-code` 2.4.1 | `kimi` |
| pi | `@earendil-works/pi-coding-agent` 1.5.2 | `pi` |
| opencode | `@opencode/cli` 2.2.5 | `opencode`, `opencode2` |
| claude | `@anthropic-ai/claude-code` 2.1.325 | `claude` |
| codex | `@openai/codex` 0.166.0 | `codex` |
| minimax | `@minimax-ai/code` 0.7.0 | `mcode` |
| qoder (native) | release manifest pin 1.1.82 | `qoder`, `qodercli` |
| independent default | `@colbymchenry/codegraph` 1.6.2 | `codegraph` |

On native macOS, the provider chain resolves Homebrew first and the frozen Bun
project second. The catalog declares the Homebrew package of every agent
Homebrew ships: `kimi-code` and `pi-coding-agent` and `opencode-v2` as
formulas, `claude-code` and `codex` as casks. A Homebrew record carries a
floor, not an exact pin: Homebrew owns the installed version, and the
deployment adopts a package at or above the catalog floor. A missing,
below-floor, or removed package falls through to the frozen Bun project, and
the next apply repairs both managed launchers. The deployment never installs or
upgrades a Homebrew package. See
[ADR 0011](adr/0011-agent-provider-chain.md).

Both regular managed launchers point at the selected executable, and every
deployment rechecks it. The frozen Bun project stays on disk as the offline
fallback, so switching providers is a reapply rather than a reinstall. On
macOS the managed launcher directory precedes the Bun directory in the managed
PATH, so the adopted command wins in an interactive shell; the other platforms
keep Bun first and retain Bun ownership; Pixi does not declare Codex. OpenCode
has one selected distribution, without `opencode-ai`. Historical inventories
remain under `deployment/inventory`. Source application and project
installation preserve the device's unrelated global Bun registry and tools.
Real executable launchers under `~/.bun/bin` and `~/.local/bin` point to the
same selected executable, preserve package-relative native resources, and prepend managed
Node/Bun paths. Both managed Qoder launchers point at the verified versioned
native binary. Existing vendor dispatchers and older releases retain their
device-owned state. Omitted launchers are unchanged.

The deployment records the observed provider, version, and floor of every
selected agent in `~/.local/state/dotfiles/agents.lock.tsv`, one
`name|provider|version|floor` row per agent. `dotfiles-agents status` reports
that provider and the effective version next to the installed state; without
device state it reports the provider the deployment would install.

A device may own a different version of a client than the catalog pins. The
entry `agent|<name>|<exact version>` in `~/.config/dotfiles/versions.tsv`
replaces that client's pin on this device. An installer-owned provider cannot
promise an exact version, so the entry forces the deployment-owned install.
Its manifest and lock are generated
once into `~/.local/state/dotfiles/agents/<name>` and installed frozen, so the
client keeps the frozen-install property and the repository lock returns when
the entry is removed. The client's `--version` diagnostic must report the
declared version. Native clients use the same entry; their release manifest
still supplies and verifies the archive digest. See
[ADR 0010](adr/0010-device-version-overrides.md).

Qoder is not executed from the vendor install script. The installer reads
`<manifest-base>/<version>/manifest.json`, requires that it advertises the
pinned version, selects the declared host archive, requires an HTTPS URL and a
64-character SHA-256 digest, downloads and verifies the archive, extracts
`qodercli`, checks its exact version, and places those verified bytes under
`~/.qoder/bin/qodercli`. Dotfiles owns that versioned executable and its two
launchers. Linux x64 falls back to the manifest's
baseline archive when the CPU lacks the required Bun feature flags. macOS
reports Apple silicon under Rosetta so the native archive is selected.

The common toolchain supplies Bun 1.4.2 and Node 26.12.1. Bootstrap checks both
exact versions and catalog minimum Node versions, then executes each selected
CLI's `--version`. A failing install or diagnostic returns its nonzero status
and package step. Pin changes require compatible manifests, locks, engines,
and runtime diagnostics; a package-manager exit alone is not acceptance.

The deliberate lifecycle trust list contains Kimi Code, Claude Code, OpenCode,
and `better-sqlite3` (a direct MiniMax Code dependency). It does not enable
broad `--trust` or arbitrary dependency scripts. MiniMax Code's own postinstall
is a native-install verifier and remains untrusted; the managed project pins
`better-sqlite3` directly so Bun builds its binding against the managed Node
runtime before `mcode` starts. Kimi's optional `node-pty` is not trusted for
Linux source compilation by default. In shipped 2.1.1
`dist/main.mjs`, `BashTool` acquires only the process capability and calls
`HostProcessService`, which uses Node's `child_process.spawn`; the sole
`node-pty` import belongs to `HostTerminalService.spawn` (lines 175629,
175662, 176725–176747 of the exact
[published package](https://registry.npmjs.org/@moonshot-ai/kimi-code/-/kimi-code-2.1.1.tgz)).
Terminal CLI/shell tools therefore do not require that optional binding.
The optional browser terminal's Linux PTY needs separately provisioned native
build prerequisites; these CLI checks do not establish its availability.
Mac/Windows PTY prebuilds ship in the locked optional package and need native
validation. Lifecycle scripts explicitly run in non-global mode so Kimi's
legacy global-shim takeover does not probe or rename host tools.

## Pinned client configuration

OpenCode 2 uses `providers`, `settings`, `package`, and nested `mcp.servers`.
The template was verified by 2.2.0's actual `opencode debug config` loader.
The exact [config schema](https://raw.githubusercontent.com/anomalyco/opencode/v2.2.0/packages/schema/src/config.ts)
and [MCP schema](https://raw.githubusercontent.com/anomalyco/opencode/v2.2.0/packages/schema/src/config/mcp.ts)
are authoritative; the unversioned public schema still described V1 at
implementation time. `codemode: false` preserves direct CodeGraph tools;
the default integration is enabled through the [settings merge](AGENT_SETTINGS.md).
The historical Serena and Headroom download commands are preserved in the
ignored inventory, outside active configuration.

The exact [watcher schema](https://raw.githubusercontent.com/anomalyco/opencode/v2.2.0/packages/schema/src/config/watcher.ts)
supports ignore patterns only. The old `watcher.enabled` had no effect;
remote compute profiles ignore all project update events (`**`), while
workstations ignore noisy directories. This filters events; it does not claim
the client's underlying watcher is disabled.

OpenCode uses `update: "disable"`, Kimi uses `[upgrade].auto_install = false`,
Claude sets `DISABLE_AUTOUPDATER=1`, and Codex disables its startup update
check. MiniMax Code and Qoder are pinned by the managed installer; `update`
reinstalls the selected managed version instead of delegating to a vendor
self-updater. These are documented controls: [OpenCode config](https://dev.opencode.ai/v2/docs/config/),
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
executes all seven real CLI selections, and repeats selections without deleting
clients. `DOTFILES_TEST_KIMI` and `DOTFILES_TEST_OPENCODE` enable actual pinned
config checks in ordinary test discovery.

```bash
DOTFILES_TEST_AGENT_INSTALL=1 \
DOTFILES_TEST_CHEZMOI=/absolute/path/chezmoi \
DOTFILES_TEST_BUN=/absolute/path/bun \
DOTFILES_TEST_NODE=/absolute/path/node \
python3 -m unittest discover -s tests -p test_agents.py -v
```

Native execution is separate CI acceptance, and has since passed for macOS,
native Windows and WSL2 x86-64; only WSL2 ARM64 is unscheduled. A
cross-platform lock proves resolution/integrity metadata, not execution of
foreign binaries or postinstall scripts. No account, credential, model request,
real shell history, or user-repository index is part of these checks.
