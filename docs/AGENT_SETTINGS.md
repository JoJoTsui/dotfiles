# Client settings and CodeGraph

Use the public bootstrap for client configuration in every deployment mode,
including `--apply-only` and `--agents none`. It merges the defaults in ignored
`deployment/client-settings/` into the actual client files. Direct Chezmoi
application leaves those runtime paths alone, so it cannot discard device
settings before the merge. The renderer uses the already-required Chezmoi;
apply-only does not require Python, Node, Bun, or an installed agent.

`targets.tsv` declares format, source, target relative to the designated home,
and ownership policy. `policies.json` names the enforced fields: the four owned
CodeGraph server entries and the clients' disabled self-updaters. Other defaults
fill missing fields. Existing device values, including false values, custom
providers, hooks, MCP servers, project trust, and authentication survive.

An existing value matching the last managed default follows later source
changes. A device override survives instead. This updates OpenCode's watcher
settings when changing host role without freezing the old managed profile.
Private baselines under `~/.local/state/dotfiles/client-settings/` omit token,
API-key, password, authorization, and secret fields; authentication is never
used as a replacement baseline.

The adapter parses JSON/JSONC/TOML and writes normalized files with mode 0600;
values are preserved, while comments and formatting are not. It validates
destination parents, rejects symlinks/type conflicts, and stages the whole
batch before replacing client settings. Invalid input fails at
`apply-source.client-settings` and names the path/format. Parser diagnostics
stay private and are removed, so malformed secret values are not printed.
Separate credential, trust, session, plugin, and cache files stay client-owned.

| Client | Managed CodeGraph location | Integration |
| --- | --- | --- |
| Claude 2.1.311 | `~/.claude.json`, `mcpServers.codegraph` | stdio, `alwaysLoad: true` |
| Codex 0.164.0 | `~/.codex/config.toml`, `mcp_servers.codegraph` | stdio |
| Kimi 2.3.3 | `~/.kimi-code/mcp.json`, `mcpServers.codegraph` | inferred stdio |
| OpenCode 2.2.0 | `~/.config/opencode/opencode.jsonc`, `mcp.servers.codegraph` | local, enabled, `codemode: false` |
| Pi 1.4.0 | global `AGENTS.md` from the shared payload | `codegraph explore "<question>"` |

Every MCP entry launches managed `codegraph serve --mcp`, with no credentials,
downloads through `npx`/`bunx`, or project-specific path. OpenCode's shape is
verified against its [pinned MCP schema](https://github.com/anomalyco/opencode/blob/v2.2.0/packages/schema/src/mcp.ts)
and [MCP container](https://github.com/anomalyco/opencode/blob/v2.2.0/packages/schema/src/config/mcp.ts),
then its actual loader and connected status. Kimi's location and transport
follow its [MCP configuration](https://moonshotai.github.io/kimi-code/en/customization/mcp.html)
and the installed 2.3.3 loader.

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
