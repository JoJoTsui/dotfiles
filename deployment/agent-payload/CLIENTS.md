# Client adapters

## Instruction files

Each client reads a user-scope file plus project files. The user file is the same
managed block everywhere, but discovery and conflict behavior differ.

The deployment replaces the block between the `DOTFILES_AGENT_START` and
`DOTFILES_AGENT_END` markers, so host text outside them survives a reapply.
Every copy carries the same content: the shared block plus the overlay for the
platform. The block names the preferred workflows, so the mattpocock skills,
Herdr, Worktrunk, and RTK read the same in every client.

The deployment points each client's user root at the home-relative path below
and clears the overrides that would relocate a client, so the managed file is
the one the client reads.

| Client | User-scope file | Project files | Caveats |
| --- | --- | --- | --- |
| Codex | `~/.codex/AGENTS.md` | `AGENTS.md` from root to cwd | The user root is `CODEX_HOME`; `AGENTS.override.md` shadows the user block; deeper project files load later |
| Claude Code | `~/.claude/CLAUDE.md` | `CLAUDE.md`, `CLAUDE.local.md` | `CLAUDE_CONFIG_DIR` is cleared, so the user file stays in `~/.claude`; a project `CLAUDE.md` suppresses project `AGENTS.md` by default; sources are concatenated |
| Kimi Code | `~/.agents/AGENTS.md` | `.kimi-code/AGENTS.md`, `AGENTS.md` | One copy is deployed here, outside `KIMI_CODE_HOME`; the retired user-scope `~/.kimi-code/AGENTS.md` block is removed on upgrade, and the project-scope `.kimi-code/AGENTS.md` is left alone |
| Pi | `~/.pi/agent/AGENTS.md` | `AGENTS.md` chain | The user root is `PI_CODING_AGENT_DIR`; `AGENTS.override.md` shadows the user block; instructions are system-prompt level |
| OpenCode V2 | `~/.config/opencode/AGENTS.md` | `AGENTS.md` chain | The user root is `OPENCODE_CONFIG_DIR`; sources are concatenated; a project file loads later but does not formally override |
| MiniMax Code | `~/.minimax/AGENTS.md` | project instructions | The global memory is the data dir's `AGENTS.md`; the deployment points `MINIMAX_DATA_DIR` at `~/.minimax` |
| Qoder | `~/.qoder/AGENTS.md` | `AGENTS.md`, `AGENTS.local.md`, `.qoder/rules` | The user root is `QODER_CONFIG_DIR`; project documents have a byte budget and can truncate |

No client guarantees identical conflict resolution. The shared policy states the
desired order: system prompt and explicit user message first, project
instructions next, this user-level block last. Check a client's override files
before assuming the block is active.

Each client has exactly one managed global instruction location. The shared
`~/.agents/AGENTS.md` file is Kimi's only global copy; it is not an additional
global input for the other clients.

## Editing tools

Claude Code, Codex, Kimi, Pi, OpenCode, and Qoder expose native file edit or
apply-patch tools. Use the native tool for structured edits; use a generic patch
tool only where the client provides one, and `sd` only for mechanical
replacements.

## Skills

The portable skill tree lives at `~/.agents/skills`. Claude Code's real-file
adapter lives at `~/.claude/skills`; its resources and relative references have
the same layout. Built-in client skills and plugin payloads stay client-owned.
Pi and OpenCode V2 receive the target home's absolute skill path in their
managed config, so an isolated deployment does not fall back to the host
account's home.

Pi and OpenCode have the shared tree as their profile root: their merged
settings register `<home>/.agents/skills`, and that tree holds the selected
profile plus the generated Herdr skill. No second copy is deployed for them.
Pi also resolves the shared tree natively as the Agent Skills location, so its
configured path and the native one name the same directory and no skill is
discovered twice.

Both clients also scan roots the deployment does not own, so a name can be
discovered twice. Pi scans its own user root, `~/.pi/agent/skills`, and warns
about the second copy of a name the shared tree provides; OpenCode scans its
default root, `~/.config/opencode/skills`, and the project's `.opencode/skills`
beside the configured profile root. The registered profile root wins the name
in both clients, because the merged settings name it: Pi prefers the
configured path over its own root, and OpenCode prefers the configured global
root over its default and project roots. The deployment writes neither root,
reports every duplicate it finds, and never removes a file the client owns.
The client-settings merge keeps a device's own skill paths, so an extra
configured root can also repeat a profile name; that root is the device's to
review.

Claude Code and Kimi expose a `Skill` tool; OpenCode exposes its own skill
mechanism. Qoder lists the shared library with `qoder skills list`; MiniMax Code
reads only its own `skills` directory, which receives a real-file copy. Codex
and Pi can read a skill's instructions with their file or shell tools. Tool
names, slash command syntax, delegation, and approval tools depend on the client.
Use an available equivalent only when it preserves the requested workflow;
report a required unavailable capability.

Keep the skill's invocation metadata. Claude Code, Codex, Kimi, Pi, and the
pinned OpenCode V2 client support explicit-only skill behavior; a client that
does not enforce that field still receives the common instruction to require an
explicit user request.

The library includes account integrations and scientific tools. Their own setup
instructions apply on first use. Ordinary deployment copies files; it does not
run helpers, install scientific dependencies, log in to external services, or
copy another device's authentication, trust, sessions, or caches.
