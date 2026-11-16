---
status: superseded
superseded_by: 0011-agent-provider-chain.md
---

# Adopt an exact matching Codex on macOS

An existing Mac may already provide the repository's exact Codex version through
Homebrew. macOS adopts that executable through managed regular launchers when
its successful diagnostic exactly matches the catalog pin; otherwise it installs
the frozen Bun project. The catalog remains the version owner, and every
deployment revalidates the external executable because its installer can update
it independently.

This exception avoids a duplicate Codex installation on an existing Mac while
preserving the pinned baseline. Other agents retain their declared installation
ownership. Fresh-install verification still exercises frozen Codex installation;
an existing-device rehearsal separately verifies adoption and preservation.

Superseded by [ADR 0011](0011-agent-provider-chain.md): the exact-match
exception became the first version floor, and the provider chain now covers
every agent instead of one client.
