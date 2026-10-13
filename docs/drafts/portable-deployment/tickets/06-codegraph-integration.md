# 06: Configure CodeGraph access without automatic indexing

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** Every supported agent can reach installed CodeGraph using
its supported integration. Indexed projects can be explored, unindexed projects
receive the documented fallback, and merely deploying the agent setup does not
index user repositories.

**Blocked by:** 05 — Deploy portable instructions and skills to every agent.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] Claude Code, Codex, Kimi Code, and opencode receive validated native MCP configuration appropriate to their pinned versions.
- [ ] pi receives usable CodeGraph CLI instructions or a skill without assuming a core MCP client.
- [ ] Configuration uses portable managed commands, and opencode's schema is verified against its pinned release rather than inferred from another version's documentation.
- [ ] Registration preserves unrelated host-local client settings and authentication; credentials are absent from the managed integration payload.
- [ ] The common rule reaches for CodeGraph when an index exists and uses supported fallback behavior for an unindexed project.
- [ ] Deployment and registration do not create indexes; an explicitly designated temporary fixture may be indexed only for a dedicated integration check.
- [ ] Fresh-home integration checks establish client configuration/command usability and controlled indexed/unindexed behavior without touching real user repositories.
