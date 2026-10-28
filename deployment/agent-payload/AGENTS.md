<!-- CODEGRAPH_START -->
## CodeGraph

When a repository has a `.codegraph/` directory, use CodeGraph before searching
or reading code. Ask the available `codegraph_explore` MCP tool about a symbol,
file, or call path, or run `codegraph explore "<question>"`. If the MCP tool is
deferred, discover it through the client's tool search. The CLI is also usable
from clients with a shell tool.

When there is no index, use ordinary code search. Create an index only when the
user requests it.

## Graphify

Graphify is an optional code knowledge graph built per repository
(`graphify-out/graph.json`). Use it when the repository has a graph and the
question is about concepts, cross-file paths, or architecture that a symbol
index answers poorly. Query with `graphify query "<question>"`,
`graphify path "<a>" "<b>"`, or `graphify explain "<symbol>"`; refresh it with
`graphify update .` after edits. Graphify's mirrored MCP server takes an
absolute graph path, so register it per project, not in the shared user
configuration.

Pick one primary query path per repository. Prefer CodeGraph when `.codegraph/`
exists, because its MCP tools are already registered for every client. Prefer
Graphify when only `graphify-out/graph.json` exists. Do not index and query both
for the same question, and do not create either index unless the user asks.
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
| Codex | `with-proxy codex exec -C . "<task>"` |
| Kimi | `kimi -p "<task>"` |
| Pi | `pi -p --model minimax-cn/MiniMax-M3.1-Flash "<task>"` |
| OpenCode | `opencode run --standalone --model opencode/deepseek-v4.1-flash-free "<task>"` |
| Qoder | `qoder -p -m DeepSeek-Flash "<task>"` |
| MiniMax Code | `mcode exec --model minimax/MiniMax-M3.1-Flash "<task>"` |

Codex needs the host proxy route on networks where its provider is unreachable
directly; `with-proxy` sets the proxy variables for one command. It is a managed
launcher on this tree. Other clients work without it here.

Free defaults are `opencode/deepseek-v4.1-flash-free`,
`minimax-cn/MiniMax-M3.1-Flash` for Pi, `minimax/MiniMax-M3.1-Flash` for
MiniMax Code, and `DeepSeek-Flash` for Qoder. Model IDs move: confirm with
`opencode models`, `pi --list-models`, or `qoder --list-models` before relying
on one. Codex and Kimi resolve models from their own configuration or aliases,
so pass a model only when you know the configured name.

Rules:

1. Delegate only when context is genuinely separable: independent research
   paths, components with a clean interface, or blackbox verification. Keep
   implementation and its tests with the agent that holds the context. Do not
   split sequential phases of one feature by role.
2. Skip delegation for a small single-step task. Every call pays a round trip
   and a re-briefing.
3. Delegate one bounded task per call: exact paths, expected output, and how to
   recognize success.
4. Start read-only for analysis and review. Allow writes only when you will read
   the resulting diff yourself.
5. Keep depth at one. A delegated agent must not start another agent unless the
   task explicitly asks for a second opinion.
6. Never pass credentials, tokens, `.env` values, or private keys to a child
   agent. It shares the filesystem, so scope it to repository paths.
7. Treat child output as evidence, not truth. Check files, diffs, and gate
   results before reporting completion.
8. Set a timeout and capture the exit status. A nonzero exit is a failure. If a
   client cannot reach its provider, that is an environment failure: fall back
   to an agent whose provider is healthy instead of retrying blindly.
9. Use Codex or Kimi as the orchestrator and Pi, OpenCode, Qoder, or MiniMax
   Code as workers when a free model is sufficient. Prefer skills and tool
   search for progressive disclosure before adding a permanent specialist.
10. Do not run two agents on the same working tree at once unless each has its
    own isolated worktree.
11. Pass a compact brief with paths and the expected result. Do not paste the
    parent transcript; a child builds its own prompt cache from the shared
    instructions and its first turn.

### Transports

The one-shot table above is the default: synchronous, headless, and usable over
SSH. Choose another transport only when the task needs something it cannot do.

- Parallel from one shell: background each worker, keep its log, and collect the
  exit status.

  ```bash
  pi -p --model minimax-cn/MiniMax-M3.1-Flash "task" >task.log 2>&1 &
  pid=$!
  wait "$pid"; status=$?
  ```

- Persistent or interactive panes: use tmux or zellij, one session per task.

  ```bash
  tmux new-session -d -s review -c "$PWD"
  tmux send-keys -t review '<client command>' Enter
  tmux capture-pane -p -t review
  tmux kill-session -t review
  ```

- Remote host: `ssh host '<client command>'`; credentials stay host-local. Use
  the same one-shot form on the other side.
- Already inside Herdr (`HERDR_ENV=1`): use its worktree and agent commands.
  Run `herdr --skill` in the pane for the current syntax; do not start or attach
  to a session from outside.
- Two agents still collide in one checkout. Give each a worktree or clone,
  whichever the transport offers.

## Context and cache discipline

Provider prompt caches reward stable prefixes and append-only history. Keep
these rules while working:

1. Keep the system prompt, shared instructions, and tool definitions
   byte-identical for a session. Change model, tools, or effort between
   sessions. A timestamp or reordered tool list in the prefix defeats caching.
2. Order by stability: tools and instructions first, project rules next, then
   session context, then messages. Put paths, timestamps, and command output
   late.
3. Append rather than rewrite. Do not re-summarize, reorder, or delete earlier
   turns; summarization resets the prefix. Mid-session changes belong in a new
   message, not an edited system prompt.
4. Restrict tools with the client's allowlist or `tool_choice` instead of
   changing the tool catalog. Adding or removing a definition invalidates the
   whole cached prefix.
5. Keep tool output small: filter with the wrappers from `~/.agents/RTK.md`, read
   ranges or symbols instead of whole files, and never paste a full log when the
   decisive line is enough.
6. Batch related reads and edits. Interleaving edits with full-file reads forces
   repeated tokens and breaks locality.
7. Reuse a warm session for related follow-ups; start a new session for an
   unrelated task or a different working tree. Provider caches expire after
   minutes to about an hour of inactivity.
8. Delegation is a fresh prefix per child. Send a short brief with paths and the
   expected result, never the parent transcript. Warm the shared prefix once
   before starting parallel helpers.
9. Cacheable prompts have a minimum size (roughly 1k tokens on several
   providers). Do not contort a short task to reach it, and do not pay cache
   writes for one-off work.
10. Measure before optimizing: cache writes cost more than normal input, so track
    usage instead of assuming a hit.
