<!-- CODEGRAPH_START -->
## CodeGraph

When a repository has a `.codegraph/` directory, use CodeGraph before searching
or reading code. Ask the available `codegraph_explore` MCP tool about a symbol,
file, or call path, or run `codegraph explore "<question>"`. If the MCP tool is
deferred, discover it through the client's tool search. The CLI is also usable
from clients with a shell tool.

When there is no index, use ordinary code search. Create an index only when the
user requests it.
<!-- CODEGRAPH_END -->

## Completion

For implementation requests, continue through the requested behavior, relevant
verification, and fixes for failures caused by the change. Resolve routine
implementation choices within scope. Ask when a missing decision materially
changes the outcome or further progress requires new authority; report what
remains blocked.

Choose context and verification proportional to the change, while honoring
project requirements. Read supporting documents when their subject applies.
Once relevant checks pass, finish unless new evidence warrants more work.

## CLI tools

Prefer available tools for their matching tasks: `rg` for search, `rg --files`
or `fd` for discovery, `sd` for mechanical replacements, a patch tool for code
edits, `uv` for Python environments and dependencies, `jq` for JSON,
`bat --paging=never` for readable output, and `eza` for directory listings.
Use `fzf --filter` for automated fuzzy selection; reserve interactive `fzf` for
a human-facing terminal. Recheck tool availability on each device and use a
portable alternative when required.

## RTK

For shell work, read `~/.agents/RTK.md` and use its supported wrappers for
compact output. Use unfiltered output when exact source or diagnostics matter.

## Skills

Use the client's native skill mechanism. When a skill mentions a `Skill` tool
that the client does not expose, read its `SKILL.md` using the client's file or
shell tool and follow the instructions. Resolve relative references from the
skill's directory and preserve explicit-invocation requirements. Skills marked
`disable-model-invocation: true` are for explicit user requests.

On first use, check the skill's own prerequisites. Set up specialist tools and
account-backed services for that invocation; deployed instructions alone do not
activate them. Read `~/.agents/CLIENTS.md` when a client's discovery or tool
capabilities affect a skill workflow.

## Cross-agent delegation

Several coding agents can share one machine. Prefer the agent whose model or
tooling fits the task, and treat this file as their shared contract. Any client
may start another client for a bounded task.

Verified non-interactive invocations, run from the repository root:

| Agent | Command |
| --- | --- |
| Codex | `codex exec -C . "<task>"` |
| Kimi | `kimi -p "<task>"` |
| Pi | `pi -p --model minimax-cn/MiniMax-M3.1-Flash "<task>"` |
| OpenCode | `opencode run --standalone --model opencode/deepseek-v4.1-flash-free "<task>"` |
| Qoder | `qoder -p -m DeepSeek-Flash "<task>"` |
| MiniMax Code | `mcode exec --model minimax/MiniMax-M3.1-Flash "<task>"` |

Free defaults are `opencode/deepseek-v4.1-flash-free`,
`minimax-cn/MiniMax-M3.1-Flash` for Pi, `minimax/MiniMax-M3.1-Flash` for
MiniMax Code, and `DeepSeek-Flash` for Qoder. Model IDs move: confirm with
`opencode models`, `pi --list-models`, or `qoder --list-models` before relying
on one. Codex and Kimi resolve models from their own configuration or aliases,
so pass a model only when you know the configured name.

Rules:

1. Delegate one bounded task per call: exact paths, expected output, and how to
   recognize success.
2. Start read-only for analysis and review. Allow writes only when you will read
   the resulting diff yourself.
3. Keep depth at one. A delegated agent must not start another agent unless the
   task explicitly asks for a second opinion.
4. Never pass credentials, tokens, `.env` values, or private keys to a child
   agent. It shares the filesystem, so scope it to repository paths.
5. Treat child output as evidence, not truth. Check files, diffs, and gate
   results before reporting completion.
6. Set a timeout and capture the exit status. A nonzero exit is a failure.
7. Use Codex or Kimi as the orchestrator and Pi, OpenCode, Qoder, or MiniMax
   Code as workers when a free model is sufficient.
8. Do not run two agents on the same working tree at once unless each has its
   own isolated worktree.
