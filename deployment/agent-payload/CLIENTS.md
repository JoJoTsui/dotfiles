# Client adapters

## Instruction files

Each client reads a user-scope file plus project files. The user file is the same
managed block everywhere, but discovery and conflict behavior differ.

| Client | User-scope file | Project files | Caveats |
| --- | --- | --- | --- |
| Codex | `~/.codex/AGENTS.md` | `AGENTS.md` from root to cwd | `AGENTS.override.md` shadows the user block; deeper project files load later |
| Claude Code | `~/.claude/CLAUDE.md` | `CLAUDE.md`, `CLAUDE.local.md` | A project `CLAUDE.md` suppresses project `AGENTS.md` by default; sources are concatenated |
| Kimi Code | `~/.agents/AGENTS.md` | `.kimi-code/AGENTS.md`, `AGENTS.md` | One copy is deployed here; the retired `~/.kimi-code/AGENTS.md` block is removed on upgrade |
| Pi | `~/.pi/agent/AGENTS.md` | `AGENTS.md` chain | `AGENTS.override.md` shadows the user block; instructions are system-prompt level |
| OpenCode V2 | `~/.config/opencode/AGENTS.md` | `AGENTS.md` chain | Sources are concatenated; a project file loads later but does not formally override |
| MiniMax Code | `~/.minimax/AGENTS.md` | project instructions | Global memory lives under the data dir |
| Qoder | `~/.qoder/AGENTS.md` | `AGENTS.md`, `AGENTS.local.md`, `.qoder/rules` | Project documents have a byte budget and can truncate |

No client guarantees identical conflict resolution. The shared policy states the
desired order: system prompt and explicit user message first, project
instructions next, this user-level block last. Check a client's override files
before assuming the block is active.

## Editing tools

Claude Code, Codex, Kimi, Pi, OpenCode, and Qoder expose native file edit or
apply-patch tools. Use the native tool for structured edits; use a generic patch
tool only where the client provides one, and `sd` only for mechanical
replacements.

## Skills

The portable skill tree lives at `~/.agents/skills`. Claude Code's real-file
adapter lives at `~/.claude/skills`; its resources and relative references have
the same layout. Built-in client skills and plugin payloads stay client-owned.
Pi resolves the shared tree relative to its managed agent directory, and
OpenCode V2 receives the target home's absolute skill path in its managed
config so isolated deployments do not fall back to the host account's home.

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
