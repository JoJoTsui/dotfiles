---
status: accepted
---

# Trigger Herdr integrations instead of owning their files

Herdr recognizes a coding agent and resumes its session through a per-agent
integration: a hook, plugin, or extension that Herdr writes into the client's
config directory. The integration schema changes with Herdr releases, and
`herdr integration status` reports the installed revision. The device already
shows the drift this causes: five managed agents were current, `qodercli` was
never installed, and four unrelated agents were outdated.

The deployment now runs `herdr integration install <kind>` for the selected
managed agents and verifies the result with `herdr integration status`. It never
writes the integration bytes itself, and it never repairs an agent the selection
does not own. Herdr owns its integration content; the repository owns the
trigger, the ordering, and the check. This is the same ownership split already
used for Worktrunk plugins.

The step runs during a full bootstrap and during `--agents-only` /
`dotfiles-agents install|update`, because both already install clients. It does
not run in `--apply-only`, which promises a pure file-and-merge step with no
agent or tool execution. When `herdr` is absent, the step succeeds with nothing
to do; when `herdr integration status` reports the selected agent as outdated,
the step reinstalls it.

Ordering matters because Herdr writes into files the deployment also merges:
Codex `hooks.json` and `config.toml`, Claude and Qoder `settings.json`, and Kimi
`config.toml`. The final client-settings merge runs after the Herdr step so the
merge preserves the added entries. Codex has one extra rule: every codex
integration install or reinstall is followed by `dotfiles-codex-herdr install`,
which re-adds the managed resume hook last. Otherwise a Herdr update silently
drops the `codex-herdr` resume argv and the proxy gate with it.

The registration reconciles at command granularity. The managed command is the
one that runs the managed hook script, and only that command is replaced: a
group that carries a device command beside it keeps its own commands, its own
metadata, and its place in the list, and only a group that held nothing but the
managed command disappears. Herdr's own entries and the other hook events are
never written by the deployment. The managed entry stays last, because its
resume argv has to win.

The managed command is the exact invocation of the managed script, not a
command that mentions it. The directory and the file name decide what a stored
command runs, so a device command that only names the script, or that runs a
file beside it, keeps its place in the group. A device may store the same
script with the path spelled another way, and that is the managed command.

MiniMax Code has no Herdr kind and stays a pane command. `dotfiles-agents
status` reports each selected agent's Herdr state
(`current`/`outdated`/`missing`/`unsupported`), and `dotfiles-agent-health
--clients` reports the same drift informationally. Integration drift affects
restore and resume, not launch, so it does not gate startup.

Consequence: installation now depends on the Herdr binary when it is present.
The deployment cannot repair integrations on a host without Herdr, and a future
Herdr schema change is repaired by reapplying rather than by editing repo files.
