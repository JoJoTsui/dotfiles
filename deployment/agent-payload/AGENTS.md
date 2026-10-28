<!-- CODEGRAPH_START -->
## CodeGraph

When a repository has `.codegraph/` or `graphify-out/graph.json`, query that
graph before text search. Prefer CodeGraph when both exist: its MCP tool
`codegraph_explore`, or `codegraph explore "<question>"`, answers symbol, file,
and call-path questions. Use Graphify (`graphify query`, `graphify path`,
`graphify explain`) when only its graph exists, and refresh it with
`graphify update .` after edits. Graphify's MCP server takes an absolute graph
path, so register it per project.

Never create an index unless the user asks. Without an index, use bounded text
search. Do not query both graphs for the same question.
<!-- CODEGRAPH_END -->

## Completion

Continue an implementation through the requested behavior, verification, and
fixes for failures it caused. Resolve routine choices in scope. Ask when a
missing decision changes the outcome or needs new authority, and report what
remains blocked.

Choose verification proportional to the change. Report the checks you ran and
the ones you skipped; never present an unrun check as passed.

## Scope discipline

Do not add complexity for a speculative race, hypothetical security edge case,
or future requirement. State the concrete failure, its likelihood, and the
complexity cost, then get agreement before implementing.

Validate untrusted input once at the boundary that owns it, then pass typed
values inward; do not revalidate invariants a schema or constructor guarantees.
Inline single-use values and logic; extract a helper only for reuse, a genuinely
complex boundary, or a name that clarifies the caller.

## Reading and language

Follow the user's language; keep identifiers, commands, and existing terms
verbatim. Read the section that matches the task instead of the whole docs tree:
pick one to three relevant documents, then the target directory's README, local
AGENTS.md, and adjacent tests. This is a user-level defaults file: the client's
system instructions and a project's AGENTS.md take precedence, and the user's
explicit instruction overrides it. Apply these rules only where they do not
conflict.

Keep this file short. Put detail in the owning document and link it here rather
than duplicating the text.

## Scientific and personal work

- Treat inputs as read-only. Keep generated artifacts, indexes, caches, and large
  data outside the tracked tree unless the project says otherwise.
- When a data format, schema, or public behavior changes, update the
  implementation, its spec or docs, and its tests in the same task.
- Synchronize lockfiles with dependency changes.
- Prefer real fixtures over mocks for pipelines, and test behavior rather than a
  copy of the implementation.
- Comment non-obvious constraints: units, assumptions, coordinate systems, and
  why a bound exists, not what the next line does.
- For any reported result, keep the command, input paths, parameters, and tool
  versions needed to reproduce it.

## CLI tools

Prefer these managed tools over `grep`, `find`, `sed`, `cat`, and `ls`:

| Task | Command |
| --- | --- |
| Search text | `timeout 15s rg -n 'pattern' path`, `rg -F` for literals |
| List files | `rg --files` or `fd . path` |
| Filter by type | `fd -e py . src`, `fd -t f -H` |
| Literal replace | `sd -s 'old' 'new' file` |
| Read a file | `bat --paging=never -l yaml file` |
| List a directory | `eza --git --icons=never -la` |
| JSON / YAML | `jq -r`, `jq -e`; `yq -r '.a.b'`, `yq -i` |
| Python | `uv run`, `uvx`, `uv add` |
| GitHub | `gh pr view`, `gh run list`, `gh ... --json` |
| Fuzzy pick | `fzf --filter`; interactive `fzf` only for a human |

Rules:

1. Use the patch tool for code and instruction edits; `sd` is for mechanical
   replacements, not structured changes.
2. Filtered output is a summary. Use the native command when exact source,
   complete diagnostics, or machine-readable output matters.
3. Managed CLIs live in `~/.pixi/bin`. If a client's bundled copy misbehaves (a
   crashing `rg`, for example), call the managed binary explicitly or prepend
   that directory to `PATH`.
4. Bound text search with `timeout`, scope the path, and use `-g` globs. On
   shared mounts avoid `/t9k`, `$HOME`, and `--no-ignore`. A timeout means
   narrow the query or use an index, not retry wider.
5. Recheck availability per device and use a portable fallback when a tool is
   missing.

## Resource limits

Measure before builds, test matrices, parallel jobs, or large downloads. `nproc`
reports host CPUs inside Docker while the cgroup quota may be lower.

- Container: `/.dockerenv`, `/run/.containerenv`, or `docker|kubepods|containerd`
  in `/proc/1/cgroup`.
- CPU: `cpu.max` on cgroup v2, or `cpu.cfs_quota_us`/`cpu.cfs_period_us` on v1;
  effective CPUs are `min(nproc, quota/period)` when quota is not `max`.
- Memory: `memory.max` (v2) or `memory.limit_in_bytes` (v1); prefer it over host
  `MemAvailable`. Physical hosts use `MemAvailable` or `vm_stat`.
- Throttling: `cpu.stat` and `/proc/pressure/*`; back off when throttled.

Cap parallel tools (`MAKEFLAGS=-jN`, `cargo -j N`, `pytest -n N`, `PIXI_JOBS=N`,
`OMP_NUM_THREADS=N`) at effective CPUs minus one, size Node work with
`NODE_OPTIONS=--max-old-space-size`, and check `df -h .` before large writes.
Unknown limit: start at half. Throttling or an OOM kill means reduce, not retry.

## Shared hosts and remote jobs

On t9k-style shared hosts, Docker or Kubernetes pods, and SSH runners, `$HOME`
can be fresh and the shell is non-login: dotfiles, `PATH`, and wrappers are not
there. Link the managed tree instead of copying files.

- Local execution already sources `.env_core`, so `~/.local/bin` and
  `~/.pixi/bin` are on `PATH`.
- Remote execution: pass the environment explicitly over `ssh`, link `.local`,
  `.pixi`, `.cargo`, `.rustup`, and `.env_core` from the operator tree, then
  source `.env_core` or the project's `env.sh`. A project script such as
  `tools/link_remote_environment.sh` is the reference: keep the source
  overridable, skip existing entries, and never replace a home file.
- No aliases, no login shell, no inherited `PATH`; `~` does not expand inside a
  double-quoted `ssh` command. Pass absolute, quoted paths.
- Create scratch on the execution host, keep inputs read-only, and propagate the
  remote exit status.

## RTK

For shell work, read `~/.agents/RTK.md` and use its supported wrappers for
compact output. Use unfiltered output when exact source or diagnostics matter.

## Skills

Use the client's native skill mechanism. When a skill mentions a `Skill` tool
the client does not expose, read its `SKILL.md` with the client's file or shell
tool and follow it. Resolve relative references from the skill's directory and
preserve explicit-invocation requirements. Skills marked
`disable-model-invocation: true` are for explicit user requests.

On first use, check the skill's own prerequisites. Set up specialist tools and
account-backed services for that invocation; deployed instructions alone do not
activate them. Read `~/.agents/CLIENTS.md` when discovery or capability
differences affect a skill workflow.

## Cross-agent delegation

Several clients can share one machine. Prefer the one whose model or tooling
fits, and treat this file as their contract. Any client may start another for a
bounded task.

| Agent | Command |
| --- | --- |
| Codex | `with-proxy codex exec -C . "<task>"` |
| Kimi | `kimi -p "<task>"` |
| Pi | `pi -p --model minimax-cn/MiniMax-M3.1-Flash "<task>"` |
| OpenCode | `opencode run --standalone --model opencode/deepseek-v4.1-flash-free "<task>"` |
| Qoder | `qoder -p -m DeepSeek-Flash "<task>"` |
| MiniMax Code | `mcode exec --model minimax/MiniMax-M3.1-Flash "<task>"` |

Codex needs the host proxy route where its provider is unreachable directly;
`with-proxy` is a managed launcher. Free defaults are
`opencode/deepseek-v4.1-flash-free`, `minimax-cn/MiniMax-M3.1-Flash` for Pi,
`minimax/MiniMax-M3.1-Flash` for MiniMax Code, and `DeepSeek-Flash` for Qoder.
Model IDs move: confirm with `opencode models`, `pi --list-models`, or
`qoder --list-models`. Codex and Kimi resolve models from their own
configuration, so pass one only when you know its name.

Rules:

1. Delegate only when context is separable: parallel research, clean-interface
   components, or blackbox verification. Keep implementation and its tests with
   the agent holding the context; never split sequential phases by role.
2. Skip delegation for a small single-step task; every call pays a round trip.
3. Give one bounded task per call with exact paths, expected output, and success
   criteria. Prefer a compact brief over the parent transcript.
4. Start read-only. Allow writes only when you will read the resulting diff.
5. Keep depth at one; a child must not start another agent unless asked.
6. Never pass credentials, tokens, `.env` values, or private keys.
7. Treat child output as evidence: check files, diffs, and gates before
   reporting completion.
8. Set a timeout and capture the exit status. A provider failure is an
   environment failure; fall back to a healthy client instead of retrying.
9. Prefer skills and tool search for progressive disclosure before adding a
   permanent specialist.

Transports beyond the one-shot table:

- Background from one shell: `cmd >task.log 2>&1 & pid=$!; wait "$pid"`.
- Persistent panes: `tmux new-session -d -s review -c "$PWD"`, then `send-keys`
  and `capture-pane`.
- Remote host: `ssh host '<client command>'`; credentials stay host-local.
- Inside Herdr (`HERDR_ENV=1`): use its worktree and agent commands; run
  `herdr --skill` for syntax and do not attach from outside.

## Worktree hygiene

A worktree is temporary. Finish every task by removing the worktree, its branch,
and any dedicated build directory.

1. Merge into `main` when that is the task's outcome.
2. Otherwise commit every change to the worktree branch, tag it
   `archive/<worktree-name>`, then remove the worktree and delete the branch.

   ```bash
   git worktree remove <path>
   git branch -D <branch>
   git worktree prune
   ```

3. Delete the per-worktree build directory, such as `CARGO_TARGET_DIR`.
4. The session that spawned a subagent cleans up its worktree, including
   `.claude/worktrees/agent-*` and `.codex/worktrees/*`.
5. Keep one only for a pending user decision or unresolved conflict; name its
   path and reason in the final response. Never leave one silently.

## Context and cache discipline

Provider prompt caches match an exact prefix, so keep it stable:

1. Keep system prompt, instructions, and tool definitions byte-identical for a
   session; change model, tools, or effort between sessions.
2. Order by stability: tools and instructions, project rules, session context,
   then messages. Put paths, timestamps, and command output late.
3. Append rather than rewrite; do not re-summarize, reorder, or delete earlier
   turns. Mid-session changes belong in a new message.
4. Restrict tools with allowlists or `tool_choice` instead of editing the tool
   catalog; a changed definition invalidates the prefix.
5. Keep output small: filter, read ranges or symbols, and never paste a full log
   when the decisive line is enough.
6. Batch related reads and edits.
7. Reuse a warm session for follow-ups; start a new one for unrelated work.
8. Cacheable prompts have a minimum size, around 1k tokens on several providers.
9. Measure before optimizing; cache writes cost more than normal input.
