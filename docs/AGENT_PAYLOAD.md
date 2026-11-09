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
Host-specific text (absolute shared-mount paths, the proxy route, Caveman/Herdr
daemon names) belongs outside that block in the client's user file; the block
replacement preserves it. Platform command differences live in
`deployment/agent-payload/overlays/<platform>.md` and are concatenated into the
block; the core stays portable.
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

Graphify uses the official portable skill from the reviewed release commit.
`deployment/skill-layouts.tsv` maps upstream `skill-agents.md` to `SKILL.md` and
its eight reference files to `references/`, preserving upstream bytes. The
shared tree and existing client adapters expose it to all seven clients. The
upstream installer is not run: its optional search-reminder plugins, project
instruction edits, hooks, and index creation are outside this global integration.
Shared guidance retains CodeGraph priority and explicit project initialization.

HumanLayer's `show-me` deploys through the same catalog and pinned lock, with
its upstream `SKILL.md` and `agents/openai.yaml` unchanged. It is installed by
default but requires explicit invocation: ask to use `show-me` to explain a
topic visually (or `/show-me` in Claude Code). Its frontmatter disables model
invocation, and its Codex policy disables implicit invocation. It provides
instructions for diagrams, code sketches, and focused HTML files; it installs
no rendering engine or executable helpers. Opening an HTML artifact uses the
host's browser (`open` on macOS); other platforms need their native opener.
For a manual global trial, `bunx skills add humanlayer/skills --skill show-me
--global --agent codex claude-code --copy --yes` uses the shared discovery root
and Claude's regular-file adapter. Bootstrap deployment uses the pinned copier,
not this CLI or the upstream Claude plugin installer.

This default applies to Linux, macOS, WSL, and native Windows, for both
workstation and remote-compute roles. All seven managed coding agents receive
`show-me`: Codex, Kimi Code, Pi, OpenCode, and Qoder use the shared tree;
Claude Code and MiniMax Code use their regular-file adapters listed below.
No per-platform skill row, Bun package installation, or Claude plugin is needed.
Herdr is the agent multiplexer; its clients discover the skill through these
same paths. Client discovery and explicit-only behavior are covered by the
shared diagnostics where available; MiniMax's native discovery remains
unverified, as recorded in the client table.

`deployment/disabled-skills.tsv` excludes the complete Google DeepMind group:
36 catalog skills and the installed `scienceskillscommon` helper. They cannot
be selected from the active catalog, even by name. Deployment moves installed
entries from known discovery roots into private recovery directories under
`~/.local/state/dotfiles/disabled-integrations/`. Override libraries are filtered
too. Packages and unrelated skills remain installed; the `uv` executable is
independent of its disabled DeepMind skill.

On the legacy T9K home, use the explicit
[agent integration adapter](LEGACY_APPLY.md#global-agent-integrations). It reuses
the public instruction copier and settings codec while validating canonical
destinations inside the persistent tree. Ordinary bootstrap keeps its stricter
symlink refusal.

`deployment/skills.lock.tsv` pins Git commits and archive SHA-256 values.
A missing or invalid lock stops fetching; `DOTFILES_SKILLS_DIR` remains the
hermetic bypass.

The catalog's last column is the selection: `auto` skills are deployed by
every host, and a tagged skill is not deployed automatically. The Lark skills
are tagged `lark` — a host that uses them asks for them with
`DOTFILES_SKILLS=lark` (or by skill name). Their pins stay reviewed, so
asking for them deploys the bytes that were pinned.
The initial lock records the existing isolated upstream cache, including every
declared skill path; it does not claim to select the latest upstream release.
Bootstrap fetches these reviewed bytes into a staging tree, then the `skills`
payload rows copy that tree to `~/.agents/skills` and the adapters. Moving branch
names in the catalog are discovery inputs for explicit updates, not deployment
versions. Cached archives and newly downloaded archives must match the lock.

One name belongs to one discovery root per client. Pi reads the shared tree
natively and also scans its own user root (`~/.pi/agent/skills`), so a name in
both roots is a collision: Pi keeps the first copy it finds and warns about
the second. The shared tree is the portable home, and a client root holds only
names the shared tree does not provide. The deployment reports the duplicates
it finds — `deployment/agent-payload/skill-roots.tsv` lists the client roots
that overlap the shared tree — instead of removing a file the client owns.

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

The native Linux gate additionally runs `tests/installed_skill_discovery.py`
after fresh installation and reapplication. It reads the deployed default lock,
checks the real fetched files and copy adapters, and parses their frontmatter
independently before comparing the selected names and invocation flags with
Pi, OpenCode, Codex, Claude, Kimi, and Qoder. Codex's prompt diagnostic covers
the automatic subset; the other diagnostics also enumerate manual skills.
OpenCode must expose `autoinvoke: false` for manual-only skills. Its optional
flag is absent for ordinary automatic skills; the report records those names
without treating registry discovery as proof of automatic invocation.
Client state and rendered configuration copies stay in private scratch, while
the discovered skill paths must point to the installed library. MiniMax's
adapter is checked for byte parity; its native discovery remains unverified.
