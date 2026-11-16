# Agent stack unification

## Problem Statement

A macOS workstation runs seven coding agents from three different installation
mechanisms. Six are frozen Bun projects, Qoder is a pinned native release, and
Codex is the only agent allowed to reuse a Homebrew package. The result is that
Homebrew and Bun disagree about which version a command should be: `kimi`
resolves to Bun 2.4.1 while Homebrew carries 2.6.2, and `opencode` resolves to
2.2.5 while Homebrew carries 2.3.0. The Bun launchers win because the shared
PATH model puts `$BUN_INSTALL/bin` first on every platform. A headless Linux
server or a Windows host has no equally clear story for installing and updating
the same set.

Herdr's per-agent integrations have the same split ownership. Herdr writes the
hooks and plugins that let it identify, report, and resume an agent, and the
deployment neither installs nor verifies them. On the current device five
managed agents are current, Qoder CLI was never integrated, and every Herdr
release can leave installed integrations outdated with nothing that repairs
them. Codex is worse: a Herdr reinstall can drop the managed resume hook that
keeps `codex-herdr`, the proxy gate, and `--no-daemon` on restore.

The shared skill library has two writers. The repository catalog pins 94 skills;
the `bunx skills` CLI keeps a separate lockfile with 130 entries and writes into
the same root. On the current device 93 names overlap, 37 CLI entries are the
DeepMind skills the deployment deliberately disables, six skills exist only in
the CLI's record, and one skill exists in neither. Every client sees a different
subset: Claude 100 entries including 33 device symlinks, MiniMax 66 stale copies,
Qoder a stale 61-entry copy beside its real shared-tree discovery, Pi an empty
own root. The library is large enough that skill descriptions compete for
context: 100 skills, 30 descriptions over 240 characters, and root documents up
to 795 lines with no reference files.

Global instructions are already deployed as one owned block to all seven
clients, but they are not reviewed alongside the skills they point at, and the
preferred workflows are not stated where every client sees them.

## Solution

Agents come from a per-agent provider chain declared in one catalog. macOS tries
Homebrew first and falls back to the frozen Bun project; Linux, WSL, and native
Windows use Bun; a verified native release remains only where Bun cannot ship the
client. Installer-owned providers carry a version floor and record the observed
version; deployment-owned providers keep exact pins and locks. Both managed
launchers point at the selected executable and are revalidated on every
deployment. The macOS PATH resolves `~/.local/bin` before `$BUN_INSTALL/bin`, so
the selected provider wins; other platforms keep their Bun-first order.

Herdr integrations are triggered, not owned. The deployment runs Herdr's own
installer for the selected managed agents, reinstalls when Herdr reports an
outdated integration, re-registers the Codex resume hook after every codex
reinstall, and leaves agents the selection does not own alone. Status reports
each agent's Herdr state; health reports the same drift informationally. Herdr's
own skill is generated from the installed binary and included in every profile.

The repository catalog is the sole owner of the shared skill library. `bunx
skills` is not run against a managed root, and its lockfile is reported as
device state with exact removal commands. Six skills are adopted from that
record. Selection becomes explicit: `auto` holds the reviewed core, tags hold
`lark`, `design`, and the non-default caveman skills, and a host opts in.
Per-client profiles apply where discovery is controlled — filtered copies for
Claude and MiniMax, profile roots for Pi and OpenCode — while Codex, Kimi, and
Qoder keep the reviewed global set. Managed skills are recorded in device state
and pruned when they leave a profile; device skills are never removed. New or
changed catalog rows must meet a description and root-document budget, with
today's over-budget rows listed as reviewed exceptions.

The shared instructions name mattpocock, Herdr, Worktrunk, and RTK as preferred
workflows, keep RTK instruction-only, and retain one instruction block for all
seven clients with per-client caveats documented in one delta table.

## User Stories

1. As a macOS workstation user, I want each agent to come from Homebrew when Homebrew provides a version at or above the catalog floor, so the agent updates with the rest of my brew-managed tools.
2. As a macOS user, I want Homebrew's newer Kimi and OpenCode to win over the older Bun copies, so the command I run is the version I expect.
3. As a macOS user whose Homebrew package is below the floor, I want the frozen Bun fallback selected automatically, so a lagging cask never blocks the deployment.
4. As a headless Linux user, I want one installation method for every agent, so provisioning a server is one documented story.
5. As a WSL user, I want the same method as Linux, so the boundary between workstation and server does not change agent installation.
6. As a native Windows user, I want the same Bun method as Linux, so the catalog and plan agree across platforms.
7. As a Qoder user, I want its verified native release path unchanged, so the one client Bun cannot ship keeps working.
8. As a user of MiniMax Code or CodeGraph, I want the Bun provider used where Homebrew has no package, so those clients are not dropped.
9. As an operator, I want `--agents` and `DOTFILES_AGENTS` selection respected across providers, so omitting an agent never installs it.
10. As a device owner, I want an exact agent version override to force a deployment-owned install, so a floating installer cannot silently break an exact requirement.
11. As an operator, I want both managed launchers to point at the selected provider's executable, so the command is the same in every shell.
12. As an operator, I want launchers revalidated on every deployment, so a removed Homebrew package cannot leave a broken command behind.
13. As an operator, I want the frozen Bun project kept as a fallback, so switching providers does not require a reinstall.
14. As a macOS shell user, I want `~/.local/bin` ahead of `$BUN_INSTALL/bin`, so the selected provider wins in an interactive shell.
15. As a Linux or Windows shell user, I want the Bun-first order unchanged, so the agent provider keeps its PATH priority.
16. As an operator, I want the plan to report each agent's effective provider and version before applying, so a change is visible first.
17. As an operator, I want `dotfiles-agents status` to report provider, effective version, and drift, so I can see what the device actually runs.
18. As a Herdr user, I want every selected agent's integration installed when missing, so Herdr can report and resume it.
19. As a Herdr user, I want outdated integrations reinstalled on the next deployment, so a Herdr update does not leave stale hooks.
20. As a Qoder user, I want its `qodercli` integration installed, so it joins the other managed agents.
21. As a Codex user, I want the managed resume hook re-registered after every codex integration reinstall, so restore keeps the health gate, proxy, and `--no-daemon`.
22. As a Herdr user, I want agents outside my selection left untouched, so device-installed agents keep their own integration state.
23. As an operator without Herdr, I want the integration step to succeed with nothing to do, so the deployment is not coupled to Herdr.
24. As an operator, I want `--apply-only` to remain execution-free, so a file-only apply never runs an agent installer.
25. As a Herdr user, I want Herdr's own skill available to every client, so agents know the in-pane rules.
26. As an operator, I want Herdr state in `dotfiles-agents status` and informational drift in `dotfiles-agent-health --clients`, so restore problems are visible before a reboot.
27. As a maintainer, I want the repository catalog to be the only writer of the shared skill tree, so an upgrade has one path.
28. As a maintainer, I want the six CLI-only skills adopted with their recorded sources and hashes, so they become reviewable and prunable.
29. As a security-conscious user, I want the CLI lockfile's disabled DeepMind entries reported and never obeyed, so a `bunx skills update` mistake is visible rather than silent.
30. As a context-conscious user, I want `auto` to hold the reviewed core rather than every catalog row, so clients load only useful guidance.
31. As a caveman user, I want the mode and its compress skill by default, so the workflow works without selecting the whole group.
32. As a user who rarely needs the caveman extras, I want the other caveman-branded skills behind a tag, so they stop consuming context.
33. As a user who invokes diagram, slide, PPT, and front-end design skills manually, I want the design group opt-in, so it does not compete for selection.
34. As a Feishu user, I want the lark group to stay opt-in per host, so hosts without Feishu do not load 28 descriptions.
35. As a Claude user, I want a filtered copy of my profile, so my skill root matches what I selected.
36. As a MiniMax user, I want a filtered copy refreshed on every apply, so the stale 66-skill copy disappears.
37. As a Pi or OpenCode user, I want my configured skill root to be a profile, so my client set matches my selection.
38. As a Codex, Kimi, or Qoder user, I want the reviewed global set and a documented limitation, so I know why I cannot have a smaller set.
39. As a maintainer, I want managed skill directories recorded per root and pruned when they leave a profile, so deselection actually shrinks the library.
40. As a maintainer, I want device-created skills never pruned, so my own work is preserved.
41. As a reviewer, I want a new or changed skill above the description or root-document budget to fail the check, so the next 609-character description does not ship.
42. As a reviewer, I want today's over-budget rows listed as exceptions, so the gate is honest rather than blocking on legacy.
43. As a maintainer, I want a per-client inventory report, so I can see what each agent actually loads.
44. As a user, I want mattpocock, Herdr, Worktrunk, and RTK named as preferred workflows in the shared instructions, so priority is visible to every client.
45. As a user, I want RTK to stay instruction-only, so its always-applicable rule is not gated behind skill selection.
46. As a maintainer, I want one instruction block audited across all seven clients, so the cross-agent contract stays single-sourced.
47. As an operator, I want the work validated in simulated homes before any real-home apply, so the migration is proven first.

## Implementation Decisions

- **Agent provider catalog.** One record per agent and provider. A record names the agent, the provider, the package or release manifest, the exact version or floor, the exposed commands, the platforms, the order, the Herdr kind, and the Bun lock or native manifest. The catalog is the only source for installation and plan output; one agent may have several provider rows.
- **Provider order.** macOS is Homebrew then Bun. Linux, WSL, and native Windows are Bun. A native release stays only for Qoder. A provider that cannot serve the platform is skipped, and an agent with no viable provider fails before state is created.
- **Version policy.** Deployment-owned providers keep exact versions and their lock or manifest. Installer-owned providers keep a floor; the deployment records the observed version in device state. A device `agent` override forces a deployment-owned install; a `cli`-style floor raises the accepted installer minimum.
- **Launcher ownership.** Both managed launcher directories receive a regular executable pointing at the selected provider. Every apply revalidates the target and diagnostic. The frozen Bun project remains as the offline fallback.
- **PATH model.** The shared value model gains a per-platform path order. macOS resolves the managed launcher directory before the Bun directory; other platforms keep Bun first. Both shell adapters render the same model.
- **Herdr step.** The step maps each selected agent to its Herdr kind, runs Herdr's installer when the integration is missing or outdated, skips when Herdr is absent, and never touches unselected agents. It runs in full and agents-only deployments, not in apply-only. The final client-settings merge runs after it. Codex is followed by the managed resume-hook registration on every install or reinstall.
- **Generated Herdr skill.** When Herdr is present, its own skill output is written into the shared tree as a generated skill, refreshed on apply, excluded from pruning, and included in every profile.
- **Skill catalog reconciliation.** The catalog is the only owner. The CLI lockfile is read for a drift report that names uncatalogued and disabled entries and prints removal commands. The six CLI-only skills become catalog rows seeded from their recorded source, path, and hash.
- **Skill selection.** `auto` holds the reviewed core. Tags hold `lark`, `design`, and the caveman group minus the mode and compress skill. The six generic engineering skills from that repository stay `auto`.
- **Skill profiles.** Claude and MiniMax receive filtered copies; Pi and OpenCode receive a profile root through their merged `skills` setting; Codex, Kimi, and Qoder keep the global set. The per-client matrix records the limitation.
- **Managed-skill pruning.** Device state records the directories deployed per root. A directory that leaves a profile is pruned only if the deployment owns it; device skills are reported, never removed.
- **Skill review gate.** New or changed catalog rows must have a description of at most 240 characters and a root document of at most 200 lines unless the skill ships a reference file. Current violations are listed as reviewed exceptions. The check emits the per-client inventory, budget findings, and ratchet failures.
- **Preferred workflows and instructions.** The shared instructions gain a preferred-workflows block naming mattpocock, Herdr, Worktrunk, and RTK. RTK stays instruction-only. One instruction block remains, with a per-client delta table and an audit that every client file carries the current block.
- **Platform parity.** The catalog and plan cover every platform. Native Windows receives catalog data and no Herdr behaviour, because the deployment does not manage Herdr there.
- **Documentation.** Three ADRs record the provider chain, Herdr ownership, and single-owner skill library. The glossary gains the provider, floor, Herdr integration, and skill ownership terms.

## Testing Decisions

Good tests assert externally visible behaviour: which provider the plan selects, which executable a launcher runs, what a shell's PATH resolves, which Herdr commands were invoked, which skill directories exist under a root, what the drift report prints, and what the deployment refuses. They do not assert internal helper names or exact shell text beyond what a user would observe.

The testing seams, highest first:

1. **Simulated-home apply.** Run the public bootstrap against a disposable home with fake `brew`, `bun`, `herdr`, and diagnostic commands on `PATH`, then inspect launchers, rendered shell files, client settings, skill roots, and state. This is the primary seam and already exists in the deployment tests.
2. **Plan output.** Assert the JSON plan for a platform and selection: provider, effective version, Herdr kind, and skill profile. This is the cheapest place to prove selection and ordering.
3. **Catalog validation.** Unit tests for duplicate agent/provider rows, unsupported platform combinations, invalid floors, missing locks, and unknown Herdr kinds.
4. **Hermetic skill library.** Use the existing `DOTFILES_SKILLS_DIR` bypass to prove adoption, tagging, profiles, pruning, budgets, and drift reporting without network access.
5. **Native macOS verifier.** Extend the existing native check to prove the real provider resolution and PATH order on macOS. The Linux suite's platform assumptions remain unchanged.

Prior art: the existing agent installation, installer-tool, Codex adoption, agent payload, skill, and common-provider tests; the simulated-home bootstrap pattern; and the native macOS verifier. Every new failure mode gets a test that fails before the change and passes after it.

Specific behaviours to pin:

- A selected agent with a Homebrew version at or above the floor installs no Bun project and both launchers point at the Homebrew executable.
- The same agent with a Homebrew version below the floor uses the frozen Bun project.
- `--agents none` leaves both launcher directories and Herdr state untouched.
- macOS renders the managed launcher directory before the Bun directory; Linux renders Bun first.
- A missing or outdated Herdr integration is installed, a current one is not, and an unselected agent is never passed to Herdr.
- A Codex reinstall is followed by resume-hook registration, and the final settings merge preserves both Herdr and resume hooks.
- `--apply-only` invokes neither Herdr nor an agent installer.
- Deselecting a tag prunes its managed directories but preserves a device-created skill with the same discovery root.
- The CLI lockfile is never written; a disabled entry produces a report and removal command.
- A new catalog row over the description or root-document budget fails the check.

## Out of Scope

- Installing, upgrading, or pinning Homebrew itself, and running `brew upgrade`.
- Replacing vendor self-updaters or changing their behaviour beyond the catalog floors.
- Herdr on native Windows, or installing Herdr itself.
- Per-client subagent definitions and their formats.
- Rewriting upstream skill prose, descriptions, or reference layouts.
- Changing the lark skill content or its Feishu source.
- The Qoder desktop cask, Codex desktop app, or any GUI client.
- Applying the result to a real account home without the explicit authorization and native gate in the repo contract.
- Removing a device's existing Bun global registry entries automatically.

## Further Notes

Rollback is a reapply with the provider chain reduced to Bun; the frozen projects and launchers remain, so no agent must be reinstalled to go back. The device state that matters is the observed installer versions, the managed-skill inventory, and the Herdr status cache, all of which are regenerated.

The migration order matters: adopt the catalog and keep current behaviour first, then switch macOS provider resolution, then PATH, then Herdr, then the skill library. That order lets each step be verified while the previous one still explains the device.

Evidence for the final report should include the simulated-home check for both a macOS-shaped and a Linux-shaped profile, the native macOS verifier, the skill review check output, and a before/after of the device's effective agent providers. Real-home application remains a separate, explicitly authorized step.
