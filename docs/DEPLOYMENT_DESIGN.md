# Dotfiles deployment design

The design interview is complete: the substantive choices below are confirmed.
The specification and ticket breakdown are being prepared for review;
implementation is outside the current conversion request.
The current remote compute host's live configuration is outside deployment
and validation targets.

## Requested behavior

1. Select different deployment profiles for macOS, remote compute hosts, WSL,
   and native Windows.
2. Validate every profile within the current environment without changing the
   current host.
3. Prefer Nushell, followed by Zsh and Bash, with shared settings except for
   shell-specific behavior.
4. Install and expose RTK through Pixi.
5. Install Pixi by default.
6. Install uv by default and configure the TUNA PyPI mirror for uv and pip.
7. Install Bun by default and use it to install the Bun-managed coding agents
   by default: Kimi Code, pi, opencode, Claude Code, Codex, and MiniMax Code.
   Install Qoder from its pinned native release manifest. Allow agent selection.
8. Deploy global agent instructions and skills by default.
9. Deploy shared shell history integration by default across devices.
10. Install CodeGraph by default and configure coding-agent integration.
11. Install and configure zoxide by default.
12. Install Tailspin by default and use it as the interactive log viewer.

## Confirmed choices

- Platform and host role are independent, with profile presets for common
  combinations. Platforms are Linux, macOS, WSL, and native Windows; initial
  roles are workstation and remote compute.
- Platform is detected automatically unless explicitly overridden. Role is
  selected explicitly, falling back to workstation; explicit options win over
  detection. The legacy `t9k` class maps to Linux remote compute.
- Initial architectures are Linux/WSL x86-64 and ARM64, macOS Intel and Apple
  silicon, and native Windows x86-64. Native Windows ARM is a later target.
- Native Windows uses Nushell and Git Bash. WSL supplies the full three-shell
  environment.
- Managed interactive launchers prefer Nushell. Bootstrap remains user-scoped
  by default; account login-shell changes and system-wide settings require
  explicit options. Agent subprocesses and scripts retain their suitable shell.
- Local acceptance consists of isolated rendering, configuration validation,
  package-resolution checks for every platform, and actual applicable Linux
  shell execution. Native macOS/Windows execution is covered by CI runners.
- One canonical set of shared values generates Nushell and POSIX shell
  configurations, with shell-specific initialization adapters.
- Hosted Atuin provides encrypted shell command history sync. Hooks are enabled
  by default; accounts and keys require device setup and remain outside git.
  Coding-agent conversations and sessions are outside the history scope.
- Device setup offers a one-time import of existing local history as an explicit
  choice and retains Atuin's built-in secret filtering. Import must select each
  available shell's importer; `atuin import auto` does not import all shells.
- The common defaults include the requested tools and all seven supported
  agents.
  Bioinformatics, GPU, and desktop packages become selectable tool bundles.
- The current host's global instructions and portable skill library are the
  starting point for a repo-owned payload, with agent-specific discovery
  adapters.
- All portable skills deploy by default. Specialist dependencies and external
  account services are set up when a skill is used rather than during ordinary
  bootstrap. Skill deployment does not promise identical client tool support.
- Tailspin is exposed as `tspin` and through a consistent `logs` command in all
  available managed shells. Its pager dependency must also be installed.
- Package versions are pinned, lockfiles are used where supported, and updates
  are explicit operations followed by the profile checks. Bun manages the
  Bun-based agent packages; Qoder installs from its pinned native release
  manifest. Pixi supplies the compatible Node runtime.

## Deployment contract

The implementation will provide platform, role, agent, and bundle selectors.
Agent selection supports all, none, or a named list, with all seven supported
agents as the default. This controls installation; shared instructions and skills are deployed
by default. An installer selection does not remove an existing installation.
Specialist bundles are opt-in, declare supported targets, and produce a clear
error when requested for an unsupported target.

The skill library has one repo-owned source. Client adapters render instructions
and expose skills through documented discovery paths. Targets use real files
in accordance with this repo's copy-mode contract; the current Claude skill
symlinks are not copied verbatim. Skill resources keep their directory
relationships, invocation metadata, and intended permissions.

Required installation failures return a failure status and identify the failed
step. Bootstrap can succeed with account activation pending, but reports that
history sync is pending until the device has its account and encryption key.
Authentication and real history import are separate setup actions.

## Agent adapters

| Agent | Global instructions | Skills | CodeGraph |
| --- | --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` | `~/.claude/skills/` adapter | Native MCP; register while preserving host-local configuration |
| Codex | `~/.codex/AGENTS.md` | `~/.agents/skills/` | Native MCP in managed config |
| Kimi Code | `~/.kimi-code/AGENTS.md` | shared `~/.agents/skills/` | Native MCP in `~/.kimi-code/mcp.json` |
| pi | `~/.pi/agent/AGENTS.md` | shared `~/.agents/skills/` | CLI instructions/skill; core has no MCP client |
| opencode | `~/.config/opencode/AGENTS.md` | shared `~/.agents/skills/` | Native MCP; schema verified against its pinned version |

CodeGraph is installed and configured by default. Creating an index remains
an explicit project decision; bootstrap does not index user repositories.
Common instruction content and RTK guidance have one source with portable
client references, replacing the current host-specific paths.

The imported library contains 105 skills and 847 files (about 8.12 MiB), with no
internal symlinks. Canonical sources are the legacy parent tree's
`.agents/skills`, `.codex/AGENTS.md`, `.claude/CLAUDE.md`, and `.codex/RTK.md`.
The shorter Claude instruction file contributes its CodeGraph rule to the
common instruction model. Credentials, runtime state, and client-built-in
skills remain outside the payload.

## Platform package exceptions

RTK uses the conda-forge package `rtk-cli` and exposes `rtk`; Tailspin uses
`tailspin` and exposes `tspin`. Both have builds for all selected native targets.
Native Windows has no conda-forge builds for Bun or Atuin, so it needs pinned
upstream installers for those tools. Git Bash supplies the Windows Bash
subprocess environment; Zsh is provided in WSL. These exceptions are managed
bootstrap steps rather than untracked host dependencies.

A Node 24 runtime satisfies the inspected Kimi Code minimum (22.19.0) and
CodeGraph's declared range (at least 20 and below 25); the exact version and
agent pins must be verified together during implementation. Kimi's current
package is `@moonshot-ai/kimi-code`. Installing packages through Bun does not
imply that every agent uses Bun as its execution runtime.

## Existing behavior and gaps

Pixi, uv, Bun, RTK, Atuin, and zoxide already appear in the bootstrap or Pixi
manifest. uv and pip already have TUNA configurations, and zoxide is initialized
in all three shells. CodeGraph is already a Bun dependency with Codex and
opencode configuration. These defaults need portability and deployment
verification rather than duplicate installers.

The source currently has only `t9k`, `linux`, and `win` classes, one large tool
manifest, no agent-selection switches, and no deployed global instruction or
skill payload. Codex currently comes from Pixi. Atuin lacks shell hooks and
device sync setup, and Tailspin is absent. Standalone Nushell does not add the
same managed-tool paths or Python preference as the POSIX environment.

Bootstrap can modify `/etc/bash.bashrc`, so changing `HOME` alone does not isolate
an installer run. It can also continue after an agent installation fails.
Validation must account for these effects and distinguish simulated checks
from native execution.

## Implementation and verification work

- Map existing tools into the common defaults and specialist bundles, preserving
  the invariant that deployed configuration references managed binaries.
- Implement profile detection, presets, selection precedence, and compatibility
  aliases, then render platform-specific paths and settings.
- Pin and verify package versions, including opencode's version-dependent MCP
  schema, native Windows installer exceptions, and Bun-installed agent execution.
- Import the skill library and portable common instructions, generate client
  adapters, and preserve host-local authentication and unrelated client state.
- Implement the history activation/import helper and synthetic filter checks.
- Build deterministic local configuration/plan tests and network-enabled
  package-resolution/install checks. Network-dependent results must be reported
  separately rather than represented by a mock's success.
- Isolate homes, package-manager roots, XDG directories, credentials, and
  installer effects during tests. Existing home directories and system
  configuration are outside all test targets.
- Run applicable Linux shell/tool checks locally and native platform checks in
  CI. Those runners have since executed for macOS, Windows and WSL2 x86-64;
  local template checks still do not stand in for native execution, and WSL2
  ARM64 is unscheduled.

No design decision remains open. The next review covers the specification's
test boundaries and the ticket breakdown before tracker publication.

## Decision records

- [Separate platform and host role](adr/0001-separate-platform-and-host-role.md)
- [Canonical shell settings](adr/0002-canonical-shell-settings.md)
- [Encrypted shell history sync](adr/0003-encrypted-shell-history-sync.md)
- [Platform runtime boundaries](adr/0004-platform-runtime-boundaries.md)
- [User-scoped Nushell startup](adr/0005-user-scoped-nushell-startup.md)

Terminology lives in [GLOSSARY.md](../GLOSSARY.md).

## Primary sources consulted

- [Claude instructions](https://code.claude.com/docs/en/memory),
  [skills](https://code.claude.com/docs/en/skills), and
  [MCP](https://code.claude.com/docs/en/mcp).
- [Codex instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
  [skills](https://learn.chatgpt.com/docs/build-skills), and
  [MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
- [Kimi instructions](https://moonshotai.github.io/kimi-code/en/customization/agents.html),
  [skills](https://moonshotai.github.io/kimi-code/en/customization/skills.html),
  [MCP](https://moonshotai.github.io/kimi-code/en/customization/mcp.html), and
  [installation](https://moonshotai.github.io/kimi-code/en/guides/getting-started).
- [pi documentation](https://github.com/earendil-works/pi/tree/main/packages/coding-agent).
- [opencode rules](https://opencode.ai/docs/rules/),
  [skills](https://opencode.ai/docs/skills/), and
  [MCP](https://opencode.ai/docs/mcp-servers/).
- [CodeGraph](https://github.com/colbymchenry/codegraph).
- [Atuin sync](https://docs.atuin.sh/main/guide/sync/),
  [import](https://docs.atuin.sh/main/reference/import/), and
  [configuration](https://docs.atuin.sh/main/configuration/config/).
- [Bun platform metadata](https://api.anaconda.org/package/conda-forge/bun),
  [Atuin platform metadata](https://api.anaconda.org/package/conda-forge/atuin),
  [RTK package](https://anaconda.org/conda-forge/rtk-cli), and
  [Tailspin package](https://anaconda.org/conda-forge/tailspin).
