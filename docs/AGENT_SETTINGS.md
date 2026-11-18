# Client settings and CodeGraph

Use the public bootstrap for client configuration in every deployment mode,
including `--apply-only` and `--agents none`. It merges the defaults in ignored
`deployment/client-settings/` into the actual client files. Direct Chezmoi
application leaves those runtime paths alone, so it cannot discard device
settings before the merge. The renderer uses the already-required Chezmoi;
apply-only does not require Python, Node, Bun, or an installed agent.

`targets.tsv` declares format, source, target relative to the designated home,
and ownership policy. `policies.json` names the enforced fields: the seven owned
CodeGraph server entries and the clients' disabled self-updaters. Other defaults
fill missing fields. Existing device values, including false values, custom
providers, hooks, MCP servers, project trust, and authentication survive.

Codex's `.codex/hooks.json` has one compatibility migration: retire the exact
`rtk hook claude` command from `PreToolUse` by replacing it with `exit 0`.
This inert slot preserves both group and command positions in Codex's hook
trust identities without changing device trust records. The Claude adapter emits
`updatedInput` without Codex's required `permissionDecision: "allow"`, causing a
hook failure. All other hook entries and metadata survive, and an unchanged file
retains its bytes and mtime.
Fresh homes receive an empty hook configuration; bootstrap installs no RTK hook.
Use explicit RTK commands as described in `~/.agents/RTK.md`.

An existing value matching the last managed default follows later source
changes. A device override survives instead. This updates OpenCode's watcher
settings when changing host role without freezing the old managed profile.
The explicit disabled-integration policy removes Serena registrations from
known MCP objects and retains existing Serena plugin-enable entries as false.
Other server entries and device values are preserved. The approved legacy
integration adapter uses the same settings codec without replacing defaults.

Private baselines under `~/.local/state/dotfiles/client-settings/` omit token,
API-key, password, authorization, and secret fields; authentication is never
used as a replacement baseline.

The adapter parses JSON/JSONC/TOML/YAML and writes normalized files with mode
0600; values are preserved, while comments and formatting are not. It validates
destination parents, rejects symlinks/type conflicts, and stages the whole
batch before replacing client settings. Invalid input fails at
`apply-source.client-settings` and names the path/format. Parser diagnostics
stay private and are removed, so malformed secret values are not printed.
Separate credential, trust, session, plugin, and cache files stay client-owned.
A target whose merged content is unchanged keeps its file and its modification
time, so services that read those files are not restarted for nothing.

The gateway migration points Claude Code and pi at Magpie after readiness
checks. Claude's endpoint is `http://127.0.0.1:3425`. The managed Haiku alias
`ANTHROPIC_DEFAULT_HAIKU_MODEL` and its deprecated predecessor
`ANTHROPIC_SMALL_FAST_MODEL` both select `codex/gpt-6.1-terra`, the
classifier-level route. Claude Code's documented environment variables
(<https://code.claude.com/docs/en/env-vars>) name the Haiku variable as the
Haiku alias and the background-functionality model, and the small-fast variable
as its predecessor. The Fable, Opus and Sonnet aliases keep `group/conductor`,
and `CLAUDE_CODE_AUTO_MODE_MODEL` keeps `codex/gpt-6.1-terra` for the permission
classifier. Pi selects the provider `magpie` and model `group/workhorse`.
Pi's `~/.pi/agent/models.json` is
Magpie-owned: the repository never templates it, and the gateway generates the
provider block and the group model entry. The official OpenCode, Kimi Code,
MiniMax Code, and Codex provider configurations remain device-owned. See
[Magpie](MAGPIE.md) for the ownership split and
[ADR 0014](adr/0014-magpie-owns-the-model-gateway.md).

Scope: this changes the two alias values the gateway merge writes into Claude
Code's settings. It does not claim that all compaction or summary traffic uses
this alias, and it does not enforce child-agent model strength. Runtime
verification that background functionality actually takes this route is
**pending**. `tests/test_magpie_auxiliary_models.py` checks the rendered gateway
settings and that the other managed aliases are unchanged; it makes no model
requests.

Claude keeps a declared plain `opus` default through client installation. The
pinned client can change plain `opus` to `opus[1m]` while initializing plugins;
the final merge restores plain `opus` only when it was selected immediately
before that installation. Explicit `opus[1m]` and custom models survive. The
Magpie wiring declares `group/conductor` instead, so that restoration does not
apply to it. Claude's own runtime metadata migrations remain client-owned.

Claude Code's `env.CLAUDE_CODE_SUBAGENT_MODEL` is no longer a managed default or
an enforced field. Claude Code normally inherits the parent model when no
higher-priority subagent selection applies, so the deployment does not pin a
separate model for them. Built-in agents and explicit selections can use other
models. On an existing device the
exact previously managed `group/conductor` value is retired once, but only when
the pre-merge baseline records that same value; a different device value, or a
value whose prior ownership the baseline cannot prove, is left untouched. The
ordinary client-settings merge performs this check while the prior baseline is
still present, before the gateway merge replaces it. This is a one-time cleanup
of a deployment-owned value, not a universal ceiling on model strength: a
device may still select any model for its subagents explicitly.

Caveman gateway configuration and lifecycle are device-owned. Bootstrap leaves
existing configuration, run state, and old merge baselines untouched and creates
none on fresh homes. Standalone skills continue to deploy through the skill
catalog. See [Caveman retirement](CAVEMAN.md#skills-only-operation).

| Client | Managed CodeGraph location | Integration |
| --- | --- | --- |
| Claude 2.1.325 | `~/.claude.json`, `mcpServers.codegraph` | stdio, `alwaysLoad: true` |
| Codex 0.166.0 | `~/.codex/config.toml`, `mcp_servers.codegraph` | stdio |
| Kimi 2.4.1 | `~/.kimi-code/mcp.json`, `mcpServers.codegraph` | inferred stdio |
| OpenCode 2.2.5 | `~/.config/opencode/opencode.jsonc`, `mcp.servers.codegraph` | local, enabled, `codemode: false` |
| Pi 1.5.2 | `~/.pi/agent/mcp.json`, `mcpServers.codegraph` | stdio, user scope |
| MiniMax Code 0.7.0 | `~/.minimax/mcp.json`, `mcpServers.codegraph` | inferred stdio |
| Qoder 1.1.82 | `~/.qoder/settings.json`, `mcpServers.codegraph` | user scope stdio |

Every MCP entry launches managed `codegraph serve --mcp`, with no credentials,
downloads through `npx`/`bunx`, or project-specific path. OpenCode's shape is
verified against its [pinned MCP schema](https://github.com/anomalyco/opencode/blob/v2.2.0/packages/schema/src/mcp.ts)
and [MCP container](https://github.com/anomalyco/opencode/blob/v2.2.0/packages/schema/src/config/mcp.ts),
then its actual loader and connected status. Kimi's location and transport
follow its [MCP configuration](https://moonshotai.github.io/kimi-code/en/customization/mcp.html)
and the installed 2.3.3 loader. Pi reads user servers from
`~/.pi/agent/mcp.json`. Qoder writes user scope into `~/.qoder/settings.json`
and MiniMax Code reads its user file at `<data-dir>/mcp.json`; both use the same
`mcpServers` object shape, taken from each client's own user-scope reader.

Claude's normal discovery puts settings in `~/.claude/settings.json` and user
MCP/auth fields in `~/.claude.json`. In the pinned release,
`CLAUDE_CONFIG_DIR=~/.claude` instead relocates that user file to
`~/.claude/.claude.json`. Bootstrap clears an inherited override and uses normal
discovery under its designated home. Inactive alternate config files remain
untouched. Native Windows must designate the OS home too; a Linux check does
not prove Windows home discovery.

The shared instructions use CodeGraph when the project has an index and ordinary
search when it does not. Registering a server does not run `init`, `index`, or
`install --init`. Index creation is an explicit project action. The server can
query an indexed project through `projectPath` even when launched in an
unindexed directory; its unindexed response explains the fallback.

Read [verification evidence](verification/codegraph.md) for the checks actually
run and the native coverage that has since passed.
