# 06: Configure CodeGraph access without automatic indexing

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** Every supported agent can reach installed CodeGraph using
its supported integration. Indexed projects can be explored, unindexed projects
receive the documented fallback, and merely deploying the agent setup does not
index user repositories.

**Blocked by:** 05 — Deploy portable instructions and skills to every agent.

**Status:** Implemented and verified on isolated Linux x86-64. Native foreign
execution has since passed for macOS, native Windows and WSL2 x86-64 through
tickets 09–11; only WSL2 ARM64 is unscheduled.

- [x] Claude Code, Codex, Kimi Code, and opencode receive validated native MCP configuration appropriate to their pinned versions.
- [x] pi receives usable CodeGraph CLI instructions or a skill without assuming a core MCP client.
- [x] Configuration uses portable managed commands, and opencode's schema is verified against its pinned release rather than inferred from another version's documentation.
- [x] Registration preserves unrelated host-local client settings and authentication; credentials are absent from the managed integration payload.
- [x] The common rule reaches for CodeGraph when an index exists and uses supported fallback behavior for an unindexed project.
- [x] Deployment and registration do not create indexes; an explicitly designated temporary fixture may be indexed only for a dedicated integration check.
- [x] Fresh-home integration checks establish client configuration/command usability and controlled indexed/unindexed behavior without touching real user repositories.

Evidence: [client ownership and adapters](../../../AGENT_SETTINGS.md),
[actual MCP/CLI checks](../../../verification/codegraph.md), and
`tests/test_codegraph.py`. All six checks passed in 34.145s, including real client
discovery/connections, explicit temporary fixture indexing, and secret-safe
preservation failures. Apply-only uses Chezmoi and requires no agent runtime.
