# Portable dotfiles deployment

**Status:** Implemented through the repository-local ticket set. Native macOS,
Windows, and WSL runner results remain external verification evidence; the
accepted behavior and local/network/native boundaries are summarized in
[Ticket 13's matrix evidence](../../verification/complete-matrix.md).

## Problem Statement

The dotfiles user needs one source state to deploy a familiar development
environment across workstations and remote compute hosts running Linux, macOS,
WSL, or native Windows. The current host classes conflate platform and purpose,
and every class receives a large manifest containing specialist packages.
Some intended defaults are already declared, but standalone shell settings,
agent installation, global instructions, history sync, and platform coverage
are incomplete.

Testing must leave the current remote compute host intact. Changing a home
directory alone cannot guarantee this because the existing installer can modify
system configuration. Rendering a foreign platform's settings on Linux also
does not demonstrate that its native programs work.

## Solution

Provide user-scoped deployment profiles that select platform independently from
host role. Install portable common defaults, make specialist tool bundles
selectable, and prefer Nushell for managed interactive sessions while keeping
Zsh and Bash available where supported. Shared shell settings come from one
canonical model with shell-specific adapters.

Install all five coding agents through Bun by default, with installation
selection available. Deploy the portable skill library, shared instructions,
and suitable CodeGraph integrations by default. Configure hosted Atuin for one
encrypted shared shell history, with deliberate device activation and optional
existing-history import. Install RTK, uv, zoxide, and Tailspin with the required
shell integrations and TUNA Python mirror settings.

Make the deployment independently verifiable: run a full isolated local matrix,
execute applicable Linux shells and tools, and use native runners for native
platform behavior. Pin tested package versions and make updates explicit.

## User Stories

1. As a dotfiles user, I want platform and host role selected independently, so that a remote machine can retain its platform's correct behavior.
2. As a workstation user, I want Linux, macOS, WSL, and native Windows profiles, so that I can use the same source state on my devices.
3. As a remote compute user, I want a remote compute role on supported platforms, so that deployment reflects my machine's purpose.
4. As a dotfiles user, I want automatic platform detection, so that a usual new-host setup needs fewer choices.
5. As a dotfiles user, I want explicit selections to override detection, so that I can choose the intended target reliably.
6. As a dotfiles user, I want host role to default to workstation unless selected, so that an SSH session does not silently select compute-host behavior.
7. As an existing T9K user, I want the legacy class to map to Linux remote compute, so that existing documented selection remains meaningful.
8. As a device owner, I want deployment scoped to my account by default, so that configuring my environment does not change other users' settings.
9. As a device owner, I want account login-shell and system configuration changes to require explicit options, so that ordinary bootstrap does not make them implicitly.
10. As a Nushell user, I want managed interactive launchers to prefer Nushell, so that my preferred shell is ready after deployment.
11. As a shell user, I want Zsh and Bash available on Linux, macOS, and WSL, so that I can use the secondary shells when appropriate.
12. As an agent or script author, I want subprocesses to retain their suitable shell, so that the interactive preference does not break automation.
13. As a shell user, I want shared values to come from one canonical source, so that shell configurations do not drift apart.
14. As a standalone Nushell user, I want managed tools and shared defaults without an inherited Bash environment, so that directly starting Nushell works.
15. As a shell user, I want existing environment overrides and repeated initialization to behave consistently, so that deployment respects deliberate host settings.
16. As a dotfiles user, I want Pixi installed by default and managed tools exposed, so that declared commands are available after bootstrap.
17. As a coding-agent user, I want RTK installed and exposed through Pixi with portable agent guidance, so that agents can use compact shell output.
18. As a Python user, I want uv installed and TUNA configured for both uv and pip, so that Python package installation uses my preferred mirror.
19. As a shell user, I want zoxide installed and initialized in supported shells, so that directory navigation works consistently.
20. As a shell user, I want Tailspin installed as the interactive log viewer with a consistent logs command, so that log inspection works immediately.
21. As a coding-agent user, I want Bun installed by default, so that it can manage the coding-agent packages.
22. As a coding-agent user, I want Kimi Code, pi, opencode, Claude Code, and Codex installed through Bun by default, so that my full agent suite is available.
23. As a device owner, I want to select all, none, or a named list of agents, so that I can control new agent installation.
24. As an existing agent user, I want an installation selection to leave existing installations intact, so that opting out does not become an uninstall operation.
25. As a coding-agent user, I want a compatible managed execution runtime, so that Bun-installed packages can actually run.
26. As a coding-agent user, I want shared instructions and portable skills deployed by default, so that each supported client discovers my operating rules and capabilities.
27. As a skill user, I want skill resources and invocation metadata preserved, so that deployment retains the library's intended behavior.
28. As a skill user, I want specialist prerequisites and account-backed services configured on use, so that ordinary deployment does not provision every external capability.
29. As a coding-agent user, I want CodeGraph installed and configured through each client's supported mechanism, so that indexed projects can be explored.
30. As a project owner, I want index creation to remain explicit, so that installing CodeGraph does not index my repositories automatically.
31. As a multi-device shell user, I want hosted encrypted Atuin sync across supported shells, so that devices share one logical command history.
32. As a multi-device shell user, I want local history while offline, so that I can work before synchronization is available.
33. As a device owner, I want clear account and encryption-key setup with a pending-sync status, so that I can activate a newly deployed device deliberately.
34. As a device owner, I want optional one-time import from each available shell and built-in secret filtering, so that migration into shared history is explicit.
35. As a specialist tool user, I want selectable bioinformatics, GPU, and desktop bundles with declared targets, so that those tools do not prevent a common deployment on another platform.
36. As a native Windows user, I want Nushell, Git Bash, and managed Windows installation exceptions, so that the common tools and agents work without promising native Zsh.
37. As a maintainer, I want Linux and WSL x86-64/ARM64, macOS Intel/Apple silicon, and Windows x86-64 coverage, so that the initial supported targets are explicit.
38. As a maintainer, I want pinned versions and locks where supported with deliberate updates, so that a tested installation remains reproducible.
39. As a maintainer, I want every profile rendered and checked in isolated homes, so that validation leaves the current host intact.
40. As a maintainer, I want foreign-target package resolution separated from actual native execution, so that test results state what has been established.
41. As a maintainer, I want required failures and unavailable verification to be visible, so that a skipped or mocked step does not appear as a successful installation.
42. As a new-host user, I want documented bootstrap, activation, verification, and update paths, so that I can reproduce the maintained environment.

## Implementation Decisions

- Deployment profile combines platform and host role. Initial platforms are
  Linux, macOS, WSL, and native Windows; roles are workstation and remote
  compute. Provide presets for common combinations.
- Platform detection is automatic, role is explicit with workstation as the
  fallback, and explicit selectors take precedence. Preserve the legacy T9K
  selection as a Linux remote compute compatibility alias.
- Initial architectures are Linux/WSL x86-64 and ARM64, macOS Intel and Apple
  silicon, and native Windows x86-64. Both roles are covered for each target.
- Keep bootstrap user-scoped. Account login-shell and system-wide changes are
  explicit opt-ins, excluded from ordinary deployment and simulated tests.
- Prefer Nushell through managed interactive launchers; retain explicit
  secondary shells and suitable agent/script subprocess behavior. Preserve the
  interactive-TTY and coding-agent-session constraints on shell handoff.
- Use one canonical shared-settings model to render POSIX and Nushell adapters.
  Guard host overrides and idempotence. Platform paths use the selected target;
  legacy tool directories remain off executable search paths.
- Common defaults include the requested tools and all five agents. Specialist
  bundles are opt-in with declared platform/architecture support. Unsupported
  requested bundles fail clearly rather than partially installing.
- Install Pixi first, expose RTK as a Pixi-managed command, and manage portable
  tool packages through Pixi. Use managed bootstrap exceptions where a required
  target lacks a package, including native Windows Bun and Atuin.
- Install uv and configure the TUNA PyPI mirror through the configurations
  actually discovered by uv and pip on each platform.
- Install Bun and a compatible managed Node runtime. Bun owns installation of
  all five coding-agent packages and CodeGraph; ensure Codex has one managed
  installation source. Agent selectors control installation without deleting
  existing tools; shared instructions and skills remain default payloads.
- Pin package versions and use lockfiles where supported. Update through an
  explicit workflow that checks runtime compatibility and reruns validation.
- Import the portable current skill library into one repo-owned source. Render
  real-file client adapters under the copy-mode contract, preserving resources,
  intended permissions, metadata, and client-built-in separation.
- Common agent instructions include portable RTK and conditional CodeGraph
  guidance. Use supported skill/instruction discovery for each client; client
  tool differences do not require identical MCP or skill-tool implementations.
- Configure CodeGraph with native MCP for clients that support it, and CLI
  guidance for pi. Verify opencode's integration schema against the selected
  version. Preserve unrelated host-local client state and leave indexing to
  explicit project choice.
- Deploy Atuin hooks and hosted encrypted sync settings by default. Device
  activation uses the same account and encryption key across devices; account
  material stays outside source control. Account activation pending is reported
  separately from installation failure.
- Offer explicit one-time history import through each available shell's
  importer and keep built-in secret filtering. Ordinary bootstrap neither
  activates real accounts nor imports existing history implicitly.
- Initialize zoxide in available managed shells. Install Tailspin and its pager,
  expose its standard command, and provide the same interactive logs behavior
  across shell adapters.
- Required installer or verification failures return a failure status and name
  the step. Treat unperformed native/network checks as pending or unavailable,
  never as a pass. Keep network-dependent results separate from deterministic
  mocked plan tests.

## Testing Decisions

- Prefer the existing top-level deployment boundary: selected profile, source
  state, installation selections, and a target home produce a rendered target,
  an installation plan, and an observable result. Add a non-executing planning
  mode at that same boundary if necessary; avoid tests of internal helpers.
- Exercise that boundary with disposable homes, isolated package-manager and
  XDG roots, controlled environment inputs, and synthetic credentials/history.
  Test fixtures, installers, and child processes must stay inside the designated
  test environment. No real-home apply, system configuration changes, real
  account login, real history reads/imports, or user-project indexing are test
  actions. Dedicated temporary repositories may be indexed explicitly for
  synthetic CodeGraph integration checks.
- For every supported platform, architecture, and role, validate selection,
  precedence, target paths, output format, required/default installation plans,
  optional-bundle behavior, and real-file output. Prove repeat application is
  idempotent and respects explicit host overrides.
- Use post-apply shell and command behavior at the same boundary: start
  applicable shells with legacy variables and inherited tool paths removed;
  verify shared values, managed command availability, interactive launchers,
  supported agent discovery, and requested tool integrations.
- Test all/none/named agent installation using controlled installer results;
  separately install pinned packages and execute harmless CLI diagnostics in
  isolated environments. Diagnostics must not require model credentials or
  send model requests.
- Validate history recording, recognized-secret exclusion, optional import,
  activation-pending behavior, and offline use with synthetic commands and
  disposable state. Use isolated test credentials/endpoints for sync tests.
  No test sends existing device history to the hosted service.
- Separate deterministic render/plan checks from network-enabled package
  resolution and isolated install/execution. Resolve the declared required
  packages for all targets and supported requested bundles; execute foreign
  binaries only on their native runtime.
- Run applicable Linux execution locally. Native macOS and Windows runners
  execute their deployment slices; WSL integration is verified in an actual WSL
  environment. Report coverage that cannot run explicitly rather than claiming
  equivalence from Linux template rendering.
- Prior art is the repository's manual simulated-home chezmoi application for
  host classes and standalone Nushell smoke check. Extend that external contract
  into an automated matrix; there is no established automated suite to mimic.
- Good tests demonstrate resulting deployment behavior, detect a meaningful
  failure or side effect, and identify the validation layer. A mocked installer,
  parser-only check, or copied implementation cannot establish native execution.

## Out of Scope

- Applying the new source state to this session's real remote compute host.
- Native Windows ARM support in the initial matrix.
- Making native Windows supply Zsh; the full three-shell environment is WSL.
- Synchronizing coding-agent conversations, sessions, credentials, trust state,
  or runtime caches.
- Automatically creating real service accounts, provisioning every skill's
  external capability, importing real history, or indexing user repositories.
- Automatic package upgrades or installing specialist bundles by default.
- Promising identical client-specific skill tools or MCP features across agents.

## Further Notes

This draft synthesizes the completed interview and its five accepted ADRs.
The current conversion prepares specifications and tickets; it does not run
implementation or change the current host. Existing simulated applications passed for legacy T9K,
Linux, and Windows classes; that evidence does not establish the new profiles.

The current portable skill snapshot contains 105 skills and 847 files. Node 24
is the discussed compatibility baseline; exact pins and their engine ranges
must be verified during implementation. Kimi Code's current package identity
is the new Kimi Code npm package, rather than its archived Python predecessor.

Design sources: [completed deployment interview](../../DEPLOYMENT_DESIGN.md),
[domain vocabulary](../../../GLOSSARY.md), and the accepted ADRs on
[profile selection](../../adr/0001-separate-platform-and-host-role.md),
[shared settings](../../adr/0002-canonical-shell-settings.md),
[history sync](../../adr/0003-encrypted-shell-history-sync.md),
[runtime boundaries](../../adr/0004-platform-runtime-boundaries.md), and
[user-scoped startup](../../adr/0005-user-scoped-nushell-startup.md).
