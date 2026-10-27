# CodeGraph integration verification

Linux x86-64 checks ran in disposable homes with pinned CodeGraph 1.6.2 and
Claude 2.1.296, Codex 0.162.1, Kimi 2.1.1, OpenCode 2.0.27. Their binaries were
borrowed read-only from the isolated ticket04 installation; every writable
client/cache root was separate. Chezmoi 2.72.2 was explicitly selected as the
test renderer. Diagnostics set `CODEGRAPH_NO_DOWNLOAD=1` and `DO_NOT_TRACK=1`.

`test_codegraph.py` passed all six checks in 34.145 seconds:

- Actual bootstrap configured four MCP clients while agent installation was
  disabled, with no index/authentication created.
- Existing client settings and synthetic authentication survived registration.
- Switching workstation/remote roles updated managed watcher defaults; device
  overrides and repeat application survived.
- Malformed TOML containing a synthetic secret failed without exposing its
  value or replacing any client config.
- The configured MCP command completed initialize/tools-list, returned the
  unindexed fallback, and created no index. Only one explicitly designated
  temporary Python fixture was then indexed. MCP exploration and the CLI
  returned its function source and calling function. The source repository and
  simulated home remained unindexed.
- Claude's native `mcp get` reported connected from its normal user config;
  Codex's native `mcp get --json` reported the enabled stdio configuration;
  Kimi's loopback MCP registry and real connection test exposed
  `codegraph_explore`; OpenCode's loopback MCP API reached connected status.

OpenCode listens before its asynchronous MCP registry is ready. The test waits
for the owned server's connected status rather than accepting the first empty
or pending response. Kimi's pinned Fastify route declaration uses `::` to
escape a literal colon; the actual connection-test URL is
`/api/v2/mcp/servers:test`. Its temporary server binds only 127.0.0.1 with a
headless test auth boundary. No model prompt, account login, or session was
needed. Codex config discovery is distinct from the direct MCP handshake.

Set `DOTFILES_TEST_CHEZMOI`, `DOTFILES_TEST_CODEGRAPH`, and the four
`DOTFILES_TEST_CODEX/CLAUDE/KIMI/OPENCODE` paths to run the actual checks. Missing
tools produce explicit skips. TOML preservation checks need Python 3.11+; the
managed Python 3.13.16 ran them. The public boundary itself has no Python
prerequisite.

macOS, WSL x86-64 and native Windows execution has since passed on the platform
tickets' native runners; portable config syntax and Linux execution are not
native proof, and only WSL2 ARM64 remains unscheduled for want of a runner. Ticket05 separately established Pi's global instruction and
shared-library discovery; the CLI exploration here establishes the command
those instructions use.

Re-verified on 2026-10-27 against the advanced pins: Claude Code 2.1.311,
Codex 0.164.0, Kimi 2.3.3, OpenCode 2.2.0, and Pi 1.4.0. Payload and setting
tests passed with disposable homes, including Codex prompt discovery, Pi's
resource loader, Kimi/Claude skill command advertisement, and OpenCode skill
discovery. The OpenCode diagnostic now runs with `--standalone` because 2.2.0
starts its managed service for `debug config`.
