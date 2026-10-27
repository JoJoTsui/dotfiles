# Client skill adapters

The portable skill tree lives at `~/.agents/skills`. Claude Code's real-file
adapter lives at `~/.claude/skills`; its resources and relative references have
the same layout. Built-in client skills and plugin payloads stay client-owned.
Pi resolves the shared tree relative to its managed agent directory, and
OpenCode V2 receives the target home's absolute skill path in its managed
config so isolated deployments do not fall back to the host account's home.

Claude Code and Kimi expose a `Skill` tool; OpenCode exposes its own skill
mechanism. Qoder lists the shared library with `qoder skills list`; MiniMax Code
reads only its own `skills` directory, which receives a real-file copy. Codex
and Pi can read a skill's instructions with their file or shell tools. Tool names, slash command syntax, delegation, and approval tools depend on
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
