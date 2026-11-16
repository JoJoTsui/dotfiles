# 01: Provider catalog, current behaviour preserved

**What to build:** One per-agent provider catalog that the plan and apply read on
both bootstrap adapters. The rows describe today's installation exactly: frozen
Bun projects for Kimi, Pi, OpenCode, Claude, Codex, MiniMax, and CodeGraph; the
verified native release for Qoder; and the macOS Homebrew exact-match adoption
for Codex. The plan reports each selected agent's provider, effective version,
commands, and Herdr kind. Validation rejects duplicate agent/provider rows,
unsupported platform or order combinations, missing locks or manifests, unknown
Herdr kinds, and an agent with no viable provider. Installation selects the same
executables at the same versions as before.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] The catalog is the only source of agent installation data in both bootstrap adapters; no per-agent name branch remains in plan output.
- [ ] Plan output names provider, effective version, commands, and Herdr kind for every selected agent on macOS, Linux, WSL, and native Windows.
- [ ] Codex still adopts an exact-matching macOS executable and otherwise uses Bun.
- [ ] Invalid catalog rows fail before any state or file is created, naming the row.
- [ ] Existing agent, installer, Codex-adoption, Windows, and plan tests pass unchanged.
