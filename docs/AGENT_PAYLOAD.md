# Portable agent instructions and skills

Ordinary bootstrap and `--apply-only` deploy this payload regardless of agent
installation selection. Use the public bootstrap for raw skill resources,
merged instructions, and [merged client settings](AGENT_SETTINGS.md).

`deployment/agent-payload` is the sole owned source. Its `targets.tsv` declares
each relative source and destination, with three operations:

- `tree`: copy regular resources and their permissions, preserving unrelated files.
- `file`: replace the owned regular file.
- `block`: replace the `DOTFILES_AGENT_START` / `DOTFILES_AGENT_END` instruction
  block, preserving surrounding device text. A first deployment appends the block.

Bootstrap validates source and destination paths, including nested symlinks,
before writing. Raw payloads live under ignored `deployment/`, so a helper named
`run_*` or a resource ending `.tmpl` retains its name and contents. Copying does
not execute helpers. The native Windows boundary must consume the same catalog;
its implementation and native checks are tracked separately.

The approved snapshot contains 105 skill directories, 847 files, and 8,508,971
bytes: 838 regular resources and nine executable helpers. Their bytes and
permissions are preserved. The shared `scienceskillscommon` sibling package,
references, inline dependency metadata, and 24 explicit-only skills remain
intact. Client built-ins, plugins, credentials, trust records, sessions, and
caches are outside the owned source.
Git attributes retain the imported bytes and line endings, including the
snapshot's existing Markdown whitespace. Application code keeps normal
whitespace checks.

The common instructions use portable command discovery, a pointer to owned
`~/.agents/RTK.md`, and conditional CodeGraph guidance. Their client capability
reference is `~/.agents/CLIENTS.md`. Account integrations and scientific
dependencies use the skill's own setup instructions on first use.

| Client | Global instructions | Portable skills | Offline discovery check |
| --- | --- | --- | --- |
| Codex | `~/.codex/AGENTS.md` | `~/.agents/skills` | `codex debug prompt-input` |
| Claude Code | `~/.claude/CLAUDE.md` | real-file `~/.claude/skills` adapter | SDK initialize command catalog |
| Kimi Code | `~/.kimi-code/AGENTS.md` and generic `~/.agents/AGENTS.md` | `~/.agents/skills` | ACP initialize/new session command catalog |
| Pi | `~/.pi/agent/AGENTS.md` | `~/.agents/skills` | public SDK resource loader |
| OpenCode V2 | `~/.config/opencode/AGENTS.md` | `~/.agents/skills` | loopback `GET /api/skill` |
| MiniMax Code | `~/.minimax/AGENTS.md` | instruction-only adapter | client-native discovery not yet recorded |
| Qoder | `~/.qoder/AGENTS.md` | instruction-only adapter | client-native discovery not yet recorded |

MiniMax Code reads global memory from `<data-dir>/AGENTS.md` (default
`~/.minimax`); Qoder reads global memory from `~/.qoder/AGENTS.md`. These two
adapters deploy instructions only. Shared skills remain available to them
through `~/.agents/skills` when the client discovers that path, but this repo
does not claim or test a skill-discovery interface for either client yet.

These locations follow [Claude skill discovery](https://code.claude.com/docs/en/skills),
[Codex skills](https://developers.openai.com/codex/skills),
[Kimi skill discovery](https://moonshotai.github.io/kimi-code/en/customization/skills.html),
[Kimi global instructions](https://moonshotai.github.io/kimi-code/en/customization/agents.html),
[Pi's skill documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md),
and [OpenCode V2 skill discovery](https://dev.opencode.ai/v2/docs/skills).
OpenCode's server may listen before its skill catalog is populated: wait for
the owned skill rather than treating the first empty response as completion.

Claude JSON and Kimi TOML credential values use serialized string literals.
The public rendering tests round-trip synthetic quotes, backslashes, newlines,
tabs, dollar signs, and backticks; they do not inspect actual credentials.

Use the managed Python for TOML checks (Python 3.11+). `test_agent_payload.py`
runs copy/isolation checks with `DOTFILES_TEST_CHEZMOI`, and the native diagnostics
when `DOTFILES_TEST_CODEX`, `DOTFILES_TEST_CLAUDE`, `DOTFILES_TEST_KIMI`,
`DOTFILES_TEST_OPENCODE`, `DOTFILES_TEST_PI_MODULE`, and `DOTFILES_TEST_NODE`
identify the pinned installed clients. All diagnostic roots remain temporary.
These checks send no model prompts or authentication requests. Foreign native
execution remains part of the platform/matrix gates.
