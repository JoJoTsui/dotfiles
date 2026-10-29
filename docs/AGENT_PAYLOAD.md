# Portable agent instructions and skills

Ordinary bootstrap and `--apply-only` deploy this payload regardless of agent
installation selection. Use the public bootstrap for instructions, fetched
skill resources, and [merged client settings](AGENT_SETTINGS.md).

Instructions and the copy adapters live under `deployment/agent-payload`; their
`targets.tsv` declares each relative source and destination, with four
operations:

- `tree`: copy regular resources and their permissions, preserving unrelated files.
- `file`: replace the owned regular file.
- `block`: replace the `DOTFILES_AGENT_START` / `DOTFILES_AGENT_END` instruction
  block, preserving surrounding device text. A first deployment appends the block.
- `retire`: remove a previously owned instruction block from a target that is no
  longer managed, preserving device text and deleting the file when nothing else
  remains. It is idempotent and runs on every deployment.

Bootstrap validates source and destination paths, including nested symlinks,
before writing. Raw payloads live under ignored `deployment/`, so a helper named
`run_*` or a resource ending `.tmpl` retains its name and contents. Copying does
not execute helpers. The native Windows boundary must consume the same catalog;
its implementation and native checks are tracked separately.

Skill bytes are not vendored. `deployment/skills.tsv` is the owned catalog and
names each upstream source, its kind, and its path:

```text
name|kind|source|ref|path
tdd|git|https://github.com/mattpocock/skills|main|skills/engineering/tdd
lark-im|tarball|https://open.feishu.cn/.../lark-im.tar.gz||
```

`deployment/skills.lock.tsv` pins Git commits and archive SHA-256 values.
The initial lock records the existing isolated upstream cache, including every
declared skill path; it does not claim to select the latest upstream release.
Bootstrap fetches these reviewed bytes into a staging tree, then the `skills`
payload rows copy that tree to `~/.agents/skills` and the adapters. Moving branch
names in the catalog are discovery inputs for explicit updates, not deployment
versions. Cached archives and newly downloaded archives must match the lock.

Update explicitly, inspect the lock diff and changed upstream skills, then run
the deployment checks before committing:

```bash
python3 deployment/update_skills.py refresh
git diff -- deployment/skills.lock.tsv
python3 deployment/update_skills.py check
```

Refresh validates upstream skill paths and archive structure before atomically
replacing the lock. It does not deploy or execute skill helpers. A failed
proposal leaves the old lock intact. Skill contents still require review;
hashes establish which bytes deploy, not whether instructions are appropriate.

A successful cache refresh is reused for
`DOTFILES_SKILLS_MAX_AGE` seconds (default six hours), `DOTFILES_SKILLS_REFRESH=1`
forces it, and `0` reuses the cache. Git sources are shallow clones under the
XDG cache; tarballs are conditional downloads. The resolved commits and cached
archive hashes are recorded in `~/.local/state/dotfiles/skills.lock.tsv`.
Reusing the cache or falling back after a failed fetch does not reset its age.
An upstream archive that changes at the same URL fails checksum verification;
review an explicit update rather than silently accepting it.
`DOTFILES_SKILLS_DIR` bypasses fetching for hermetic tests and air-gapped hosts.

Archives are rejected when they contain absolute paths, parent traversal, or
symlinks. Copying still executes nothing. A catalog row that the upstream
project no longer ships fails the apply by name instead of silently dropping a
skill. Client built-ins, plugins, credentials, trust records, sessions, and
caches remain outside the owned source.

The common instructions use portable command discovery, a pointer to owned
`~/.agents/RTK.md`, conditional CodeGraph and Graphify guidance, a cross-agent
delegation contract with verified one-shot commands for Codex, Kimi, Pi,
OpenCode, Qoder, and MiniMax Code, the collaboration rules recorded in
[cross-agent collaboration](AGENT_COLLABORATION.md), the optional
[Herdr](HERDR.md) multi-pane workflow, the [resource-budget](AGENT_RESOURCES.md)
rules, the [shared-host and remote-job](AGENT_REMOTE_JOBS.md) pattern with
bounded search, and the cache-discipline rules recorded in
[caching and context budget](AGENT_CACHING.md).

CodeGraph is the primary code-query path: its MCP entry is registered for every
client. Graphify is optional and per repository. Provision it with
`uv tool install "graphifyy[mcp]"`, install its skill with
`graphify install --platform agents` (it writes `~/.agents/skills/graphify`),
and register `graphify-mcp <absolute graph path>` per project when its MCP tools
are wanted. Do not run both indexes for the same question. Their client capability
reference is `~/.agents/CLIENTS.md`. Account integrations and scientific
dependencies use the skill's own setup instructions on first use.

| Client | Global instructions | Portable skills | Offline discovery check |
| --- | --- | --- | --- |
| Codex | `~/.codex/AGENTS.md` | `~/.agents/skills` | `codex debug prompt-input` |
| Claude Code | `~/.claude/CLAUDE.md` | real-file `~/.claude/skills` adapter | SDK initialize command catalog |
| Kimi Code | `~/.agents/AGENTS.md` (single copy; the retired `~/.kimi-code/AGENTS.md` block is removed on upgrade) | `~/.agents/skills` | ACP initialize/new session command catalog |
| Pi | `~/.pi/agent/AGENTS.md` | `~/.agents/skills` via `settings.skills` | public SDK resource loader |
| OpenCode V2 | `~/.config/opencode/AGENTS.md` | `~/.agents/skills` via `skills` | loopback `GET /api/skill` |
| MiniMax Code | `~/.minimax/AGENTS.md` | real-file `~/.minimax/skills` adapter | client-native discovery not yet recorded |
| Qoder | `~/.qoder/AGENTS.md` | `~/.agents/skills` | `qoder skills list` |

MiniMax Code reads global memory from `<data-dir>/AGENTS.md` (default
`~/.minimax`) and skills only from `<data-dir>/skills`, so it needs a real-file
copy of the shared library. Qoder reads `~/.qoder/AGENTS.md` and discovers
`~/.agents/skills` directly; `qoder skills list` reports the shared paths for a
deployed home, so it needs no skill adapter. Both clients keep their own skill
directories and plugin payloads client-owned, and both receive the shared
instruction block and the managed CodeGraph entry documented in
[client settings](AGENT_SETTINGS.md).

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
