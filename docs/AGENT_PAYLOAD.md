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

`humanizer` (English prose) and `humanizer-zh` (Chinese prose) use the same
default deployment on all four platforms and all seven coding agents. Both
publish their skill at the repository root. Their layout rows copy only
`SKILL.md`, the upstream license, and Humanizer's `agents/openai.yaml`, keeping
the upstream bytes unchanged. Repository instructions, plugin manifests,
maintenance scripts, and test materials are excluded from discovery.
Windows extracts root skill archives without stripping a directory level.

Ask to use `humanizer` or `humanizer-zh` on the text or file to edit. Unlike
`show-me`, neither upstream disables implicit invocation: agents may select
them for relevant prose-editing requests. The `humanizer-zh` `allowed-tools`
names are interpreted by each client's native skill loader or the shared
client-adapter guidance; no Claude-only tool is required to edit text. They
provide editorial guidance, with no additional runtime dependency or account
setup. Their editing rules require preserving facts and protected file
content; neither skill establishes authorship or guarantees an AI-detector
outcome.

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
every host, and a tagged skill is not deployed automatically. `auto` is the
reviewed core: the mattpocock engineering and productivity skills, graphify,
worktrunk, the humanizers, `show-me`, `pr` and `research`, and the other
general entries. The caveman mode and its compress skill stay in that core,
and so do the six generic engineering skills of the caveman repository
(`investigate-first`, `lean-build`, `migration`, `safe-refactor`,
`surgical-patch`, `verify-and-stop`); they are general workflows, not caveman
voice. The other fourteen caveman-branded skills carry the `caveman` tag, the
four diagram, slide-deck, PPT, and front-end design skills carry `design`, and
the Feishu skills carry `lark`. A host asks for a group with
`DOTFILES_SKILLS=<tag>`, or for one skill with `DOTFILES_SKILLS=<name>`. Their
pins stay reviewed, so asking for them deploys the bytes that were pinned.
The selection applies both to the fetch and to the copy into a managed root,
so a library supplied through `DOTFILES_SKILLS_DIR` deploys the selected
skills and nothing else. A name the catalog does not declare is device
content: it never enters a managed root.
The initial lock records the existing isolated upstream cache, including every
declared skill path; it does not claim to select the latest upstream release.
Bootstrap fetches these reviewed bytes into a staging tree, then the `skills`
payload rows copy that tree to `~/.agents/skills` and the adapters. Moving branch
names in the catalog are discovery inputs for explicit updates, not deployment
versions. Cached archives and newly downloaded archives must match the lock.

The deployment records the skill directories it wrote into each managed root
in `~/.local/state/dotfiles/managed-skills.tsv`, one `name|root` row per
directory. A root the deployment does not own is never recorded. The prune
step runs after the payload copy: a recorded directory that leaves the
selection is removed from its root, so a tag that a host drops actually
shrinks the library. The exemptions keep the prune inside the deployment's
ownership:

- a device-created skill — a directory the deployment did not write — is never
  removed; it is reported with the root that holds it
- a generated skill named in `~/.local/state/dotfiles/generated-skills.tsv` is
  never removed
- a symlinked entry is refused and preserved: the prune never follows a link
  and never deletes through it
- a root the deployment does not own is never pruned

Reapplying with an unchanged selection changes nothing: the inventory, the
roots, and the report stay the same.

A copy root is inspected before a selected skill is written there, so a
device entry never loses to the deployment:

- a symlink at the skill path is preserved and reported; the copy never
  follows it and never writes through it
- a regular file at the skill path is preserved and reported
- a directory the inventory does not record is adopted when it already holds
  the selected bytes, without a rewrite, and preserved and reported when its
  bytes differ
- a directory the inventory records belongs to the deployment, so the staged
  copy replaces it and the bytes it no longer carries are gone
- a missing path is copied

An entry the deployment does not own is never recorded, so it stays device
content. The stale copy a device carried before the inventory existed is
reported rather than deleted.

The repository catalog is the only writer of a managed skill root. `bunx skills
add` and `bunx skills update` must not target `~/.agents/skills` or a client
root the deployment owns: a second writer replaces reviewed bytes with
unpinned ones, and the next apply overwrites the change. A skill added that
way is reported as drift and named for removal.

The `bunx skills` CLI keeps its own lockfile at `~/.agents/.skill-lock.json`.
It is device state, not a second catalog. The deployment reads that file and
never writes it or the directory that holds it. Every entry the catalog does
not own is reported: an uncatalogued skill the device added, and a disabled
skill the CLI still records. Each one is named with the exact command that
tidies the device.

```bash
python3 deployment/skill_drift.py            # the dedicated report; exits non-zero on drift
python3 deployment/skill_drift.py --report   # the same report without failing
python3 deployment/update_skills.py check    # the pin check; reports the drift without failing
```

An apply reports the drift and continues: the lockfile belongs to the device,
and its contents are the device owner's to review. A gate runs the dedicated
report, which exits non-zero while drift remains.

The six skills the CLI knew and the catalog did not are catalogued rows now.
`baoyu-diagram`, `baoyu-slide-deck`, `guizang-ppt-skill`, and `impeccable`
carry the `design` tag; `find-skills` and `resolving-merge-conflicts` stay
`auto`. Their rows are seeded from the CLI's recorded source and path, and the
lock pins an upstream commit that ships the declared path. `impeccable` was in
neither record, so its upstream path is the one its repository publishes.

One name belongs to one discovery root per client. Pi reads the shared tree
natively and also scans its own user root (`~/.pi/agent/skills`), so a name in
both roots is a collision: Pi keeps the first copy it finds and warns about
the second. The shared tree is the portable home, and a client root holds only
names the shared tree does not provide. The deployment reports the duplicates
it finds — `deployment/agent-payload/skill-roots.tsv` lists the client roots
that overlap the shared tree — instead of removing a file the client owns.

Pi and OpenCode receive the shared tree as their profile root. Their merged
settings register the designated home's `~/.agents/skills`, and that tree holds
the selected profile plus the generated Herdr skill; no second copy is
deployed for them. OpenCode scans its default root (`~/.config/opencode/skills`)
and the project's `.opencode/skills` beside the configured root, so a device
entry there repeats a profile name; the registered root wins the name, and the
deployment reports the duplicate without writing to that root. The
client-settings merge keeps a device's own skill paths, so an extra configured
root can repeat a profile name too; that root belongs to the device.

A generated skill is not a catalog row. Herdr ships its own instructions, so
the deployment writes them into the shared tree at
`~/.agents/skills/herdr/SKILL.md` from `herdr --skill` and refreshes them
when the installed binary changed. The same generated bytes reach every other
managed copy root — Claude's and MiniMax's roots today — and the copy never
writes through a device entry there. The deployment records every generated
skill in `~/.local/state/dotfiles/generated-skills.tsv` as
`name|root|generator`, one row per name and root, so the pruning step can
tell a generated skill from a catalog row and leave it alone in every root.

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
`~/.agents/RTK.md`, conditional CodeGraph and Graphify guidance, a
preferred-workflows section that names the mattpocock skills, Herdr, Worktrunk,
and RTK as the first choice in their area and points at the detailed section or
skill instead of repeating it, a cross-agent delegation contract with verified
one-shot commands for Codex, Kimi, Pi, OpenCode, Qoder, and MiniMax Code, the
collaboration rules recorded in [cross-agent collaboration](AGENT_COLLABORATION.md),
the optional [Herdr](HERDR.md) multi-pane workflow, the
[resource-budget](AGENT_RESOURCES.md) rules, the
[shared-host and remote-job](AGENT_REMOTE_JOBS.md) pattern with bounded search,
and the cache-discipline rules recorded in
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
| Codex | `~/.codex/AGENTS.md` | `~/.agents/skills` (global set) | `codex debug prompt-input` |
| Claude Code | `~/.claude/CLAUDE.md` | real-file `~/.claude/skills` adapter (filtered copy) | SDK initialize command catalog |
| Kimi Code | `~/.agents/AGENTS.md` (single copy; the retired `~/.kimi-code/AGENTS.md` block is removed on upgrade) | `~/.agents/skills` (global set) | ACP initialize/new session command catalog |
| Pi | `~/.pi/agent/AGENTS.md` | `~/.agents/skills` (profile root) via `settings.skills` | public SDK resource loader |
| OpenCode V2 | `~/.config/opencode/AGENTS.md` | `~/.agents/skills` (profile root) via `skills` | loopback `GET /api/skill` |
| MiniMax Code | `~/.minimax/AGENTS.md` | real-file `~/.minimax/skills` adapter (filtered copy) | client-native discovery not yet recorded |
| Qoder | `~/.qoder/AGENTS.md` | `~/.agents/skills` (global set) | `qoder skills list` |

The three shapes are the recorded limit of each client's discovery. A filtered
copy and a profile root hold the selected profile; the global set is the whole
shared tree, because Codex, Kimi, and Qoder have no supported persistent
filter. The shapes follow
[ADR 0013](adr/0013-single-owner-skill-library.md).

The instruction block stays one shared source. A simulated apply proves that
all seven client instruction files carry the current block, that every copy
holds the same content, and that the retired `~/.kimi-code/AGENTS.md` file
stays absent. The per-client differences live in the delta table of
`deployment/agent-payload/CLIENTS.md`, not in per-client copies of the block.

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
