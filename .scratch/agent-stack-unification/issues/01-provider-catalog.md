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

**Status:** done

- [x] The catalog is the only source of agent installation data in both bootstrap adapters; no per-agent name branch remains in plan output.
- [x] Plan output names provider, effective version, commands, and Herdr kind for every selected agent on macOS, Linux, WSL, and native Windows.
- [x] Codex still adopts an exact-matching macOS executable and otherwise uses Bun.
- [x] Invalid catalog rows fail before any state or file is created, naming the row.
- [x] Existing agent, installer, Codex-adoption, Windows, and plan tests pass unchanged.

## Comments

`deployment/agents/providers.tsv` replaces `deployment/agents/catalog.tsv` and
`deployment/agents/native.tsv` with one record per agent and provider, and
`deployment/agents/herdr-kinds.tsv` declares the Herdr kinds a record may name.
The POSIX adapter (`deployment/agents.sh`) and the native Windows adapter
(`bootstrap.ps1` with `deployment/windows.ps1`) read the same records; the plan
reports provider, version policy, effective version, commands, and Herdr kind
per selected agent. Validation runs before any state or file is created.

The macOS Codex adoption is now a catalog record ahead of the frozen Bun
record, so the plan names `homebrew` as Codex's first provider on macOS and
`bun` everywhere else. Installation still selects the same executables at the
same versions: the adoption requires the exact `codex-cli <version>` diagnostic,
and every other agent keeps its frozen Bun project or verified native release.
The macOS Homebrew-first resolution with version floors remains ticket 02.
