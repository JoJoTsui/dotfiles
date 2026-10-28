<!-- CODEGRAPH_START -->
## CodeGraph

When a repository has `.codegraph/` or `graphify-out/graph.json`, query that
graph before text search. Prefer CodeGraph when both exist: its MCP tool
`codegraph_explore`, or `codegraph explore "<question>"`, answers symbol, file,
and call-path questions. Use Graphify (`graphify query`, `graphify path`,
`graphify explain`) when only its graph exists. Refresh an existing graph only
when the answer depends on recent edits and the user allows it. Graphify's MCP
server takes an absolute graph path, so register it per project.

If the index directory exists but `codegraph status` reports it uninitialized,
or the graph tool is unavailable, fall back to bounded text search. Never create
a new index unless the user asks. Do not query both graphs for one question.
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
complexity cost, then get agreement before implementing. Required
trust-boundary validation, data-loss prevention, and correctness checks are not
speculative; keep them.

Validate untrusted input once at the boundary that owns it, then pass typed
values inward; do not revalidate invariants a schema or constructor guarantees.
Inline single-use values and logic; extract a helper only for reuse, a genuinely
complex boundary, or a name that clarifies the caller.

## Safety and authority

- Treat unknown or pre-existing modifications as the user's work. Do not stash,
  revert, or overwrite them.
- Do not push, force-push, rewrite history, or delete files you did not create
  without explicit authority for that action.
- Do not read, echo, log, or commit credentials, tokens, keys, or `.env` values;
  redact secrets in output and reports.
- Do not send controlled-access, patient-identifiable, or license-restricted data
  to hosted models or external services without authorization.
- Install packages, log in, or change system state only within authority already
  granted for the task.

## Reading and language

Follow the user's language; keep identifiers, commands, and existing terms
verbatim. Read the section that matches the task instead of the whole docs tree:
pick one to three relevant documents, then the target directory's README, local
AGENTS.md, and adjacent tests.

This file is user-level defaults. Desired conflict policy: the client's system
prompt and an explicit user message win; project instructions and deeper
directory files come next; apply this file only where they do not conflict.
Clients differ. Codex documents project and deeper files overriding earlier
global guidance, and `AGENTS.override.md` shadows this block. Claude and OpenCode
concatenate sources without a guaranteed winner. Pi assembles them in its system
prompt. Check the client's project filenames and override files instead of
assuming identical enforcement.

## Scientific and personal work

- Treat inputs and reference trees as read-only. Keep generated artifacts,
  indexes, caches, and large data outside the tracked tree unless the project
  says otherwise.
- When a data format, schema, or public behavior changes, update the
  implementation, its spec or docs, and its tests in the same task.
- Prove output completeness for generated results with a record count, checksum,
  or atomic tmp-and-rename step. An exit code alone is not completeness.
- For a result you report, record the task-relevant reference build, input
  checksums, parameters, and environment identifier; skip fields that do not
  affect the result.
- Prefer small real slices over mocks for pipelines, and test behavior rather
  than a copy of the implementation.
- Comment non-obvious constraints: units, assumptions, reference builds, and why
  a bound exists, not what the next line does.
- Multi-stage pipelines use `set -o pipefail` in bash or zsh, or check each
  stage's status where it is unavailable.

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

1. Use the client's native edit or patch tool for code and instruction edits
   (Pi has native edit/write); `sd` is for mechanical replacements, not
   structured changes.
2. Filtered output is a summary. Use the native command when exact source,
   complete diagnostics, or machine-readable output matters.
3. Managed CLIs live in `~/.pixi/bin`. If a client's bundled copy misbehaves (a
   crashing `rg`, for example), call the managed binary explicitly or prepend
   that directory to `PATH`.
4. Bound text search with `timeout` when available (`gtimeout` on macOS),
   scope the path, and use `-g` globs. Without a timeout command, cap matches
   and scope harder. On shared mounts avoid `/t9k`, `$HOME`, and `--no-ignore`.
   A timeout means narrow the query, not retry wider.
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

Honor a task or scheduler grant before the shared cgroup ceiling. Cap parallel
tools (`MAKEFLAGS=-jN`, `cargo -j N`, `pytest -n N`, `OMP_NUM_THREADS=N`,
`OPENBLAS_NUM_THREADS=N`) at `max(1, usable - 1)`, where usable is the smallest of
the grant, cgroup quota, and `nproc`. For Pixi, use its documented operation
flags (`--concurrent-solves`, `--concurrent-downloads`) instead of an environment
variable. Treat `max`, `-1`, and the v1 2^63-1 memory sentinel as unlimited. Size
Node work with `NODE_OPTIONS=--max-old-space-size`, and check `df -h .` before
large writes. Unknown limit: start at half. Throttling or an OOM kill means
reduce, not retry.

## Shared hosts and remote jobs

On t9k-style shared hosts, Docker or Kubernetes pods, and SSH runners, `$HOME`
can be fresh and the shell is non-login: dotfiles, `PATH`, and wrappers may be
absent. Do not assume an interactive shell.

- Verify the environment instead of assuming it: `command -v` the tools you
  need, and source `.env_core` or the project's `env.sh` when present.
- Writable operator-tree linking belongs only to an authorized, trusted
  shared-mount workflow. Otherwise expose read-only paths, copy only wrappers,
  or use task-owned `CARGO_HOME`, `RUSTUP_HOME`, and `PIXI_HOME`. Link `.agents`
  when RTK or CLIENTS references are needed.
- A project script such as `tools/link_remote_environment.sh` is the reference:
  keep the source overridable, skip existing entries, and never replace a home
  file.
- Pass absolute paths; quote them. A remote shell may expand an unquoted `~`, and
  a double-quoted command still evaluates variables.
- Create scratch on the execution host, keep inputs read-only, and propagate the
  remote exit status. Do not place secrets in argv; read them on the remote side.

## RTK

For shell work, read `~/.agents/RTK.md` and use its supported wrappers for
compact output. Use unfiltered output when exact source or diagnostics matter.

## Skills

Use the client's native skill mechanism. When a skill mentions a `Skill` tool
the client does not expose, read its `SKILL.md` with the client's file or shell
tool and follow it. Resolve relative references from the skill's directory and
preserve explicit-invocation requirements. Skills marked
`disable-model-invocation: true` are for explicit user requests.

On first use, check the skill's own prerequisites. Installing tools, logging in,
or changing system state needs authority already granted for the task; deployed
instructions alone do not activate them. Read `~/.agents/CLIENTS.md` when
discovery or capability differences affect a skill workflow.

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
5. Keep depth at one by policy. Tell the child not to spawn sub-agents, and use
   client flags that restrict them where available.
6. Do not pass credentials, tokens, `.env` values, or private keys; scrub
   credential variables from the child environment.
7. Treat child output as evidence: check files, diffs, and gates before
   reporting completion.
8. Set a timeout and capture the exit status. A provider failure is an
   environment failure; fall back to a healthy client only inside the same trust
   boundary, or ask first.
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

Clean up only worktrees and build directories the task created. Never remove a
worktree you did not create, one the user is using, or the one you are running
in. Never delete unrelated or ignored files.

1. If the work belongs on the default branch, merge it. Remove the worktree from
   a directory outside it.
2. Otherwise commit tracked changes to the worktree branch, tag it
   `archive/<worktree-name>`, and verify the tag resolves before deleting the
   branch.
3. Inventory untracked and ignored files first: Git removes ignored files even
   when status is clean. Move or archive anything you need to keep.
4. Run `git worktree remove <path>` without `--force`. If Git refuses, stop and
   report; do not force the removal.
5. Delete only the build directory created for that worktree, such as its
   `CARGO_TARGET_DIR`.
6. If a worktree must stay for a user decision or an unresolved conflict, name
   its path and reason in the final response.

## Context and cache discipline

Keep context stable and small:

1. Prefer append-only progress. Do not rewrite earlier results or instructions
   unless the user asks or the client compacts.
2. Let the client compact when it must; continue from the summary instead of
   replaying history.
3. Bound tool output: filter, read ranges or symbols, and batch related reads and
   edits.
4. Reuse a warm session for related follow-ups; start a new one for unrelated
   work.
5. If you build requests yourself, keep the prefix stable and change model or
   tools between sessions. Retention, minimum sizes, and write prices vary by
   provider and model; check current documentation instead of assuming a
   universal number.
