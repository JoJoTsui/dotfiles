# Client skill adapters

The portable skill tree lives at `~/.agents/skills`. Claude Code's real-file
adapter lives at `~/.claude/skills`; its resources and relative references have
the same layout. Built-in client skills and plugin payloads stay client-owned.

Claude Code and Kimi expose a `Skill` tool; OpenCode exposes its own skill
mechanism. Codex and Pi can read a skill's instructions with their file or shell
tools. Tool names, slash command syntax, delegation, and approval tools depend on
the client. Use an available equivalent only when it preserves the requested
workflow; report a required unavailable capability.

Keep the skill's invocation metadata. Claude Code, Codex, Kimi, Pi, and the
pinned OpenCode V2 client support
explicit-only skill behavior; a client that does not enforce that field still
receives the common instruction to require an explicit user request.

The library includes account integrations and scientific tools. Their own setup
instructions apply on first use. Ordinary deployment copies files; it does not
run helpers, install scientific dependencies, log in to external services, or
copy another device's authentication, trust, sessions, or caches.
