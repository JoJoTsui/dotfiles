# Herdr

Herdr is a terminal workspace manager for coding agents: persistent sessions,
workspaces, panes, and recognized agent state over a socket API. It is one
transport among several; the one-shot CLI is the default, and tmux or zellij
cover most interactive needs without a socket API. Herdr is optional and
self-managed.

## Install and update

```bash
curl -fsSL https://herdr.dev/install.sh | sh
herdr --version
herdr update            # self-updating, stable channel by default
herdr channel set preview
```

The installer writes `~/.local/bin/herdr`. There is no version pin here because
`herdr update` owns upgrades; record the installed version in the session report
when behavior matters.

Client integrations are installed by Herdr:

```bash
herdr integration status
herdr integration install codex
```

## The deployment installs the integrations

Herdr owns the integration bytes; the deployment owns the trigger, the
ordering, and the check. After the agent step and before the final
client-settings merge, the deployment maps every selected managed agent to its
Herdr kind, reads `herdr integration status`, and runs
`herdr integration install <kind>` for the kinds that are missing or outdated.
A current integration is left alone, an agent outside the selection is never
passed to Herdr, and the deployment never writes an integration file itself.
The step runs in a full deployment and in `--agents-only`, never in
`--apply-only`. A host without Herdr completes the deployment with nothing to
do.

The kind of each agent is a column of the provider catalog
(`deployment/agents/providers.tsv`), and `deployment/agents/herdr-kinds.tsv`
lists the kinds a record may name. `qoder` uses the kind `qodercli`; MiniMax
Code and CodeGraph have no kind and are never passed to Herdr.

`~/.local/bin/dotfiles-herdr-status` owns Herdr's status vocabulary. It reads
`herdr integration status` once and prints one `<kind>|<state>` line per
requested kind, where the state is `current`, `outdated`, `missing`,
`unsupported` (Herdr does not know the kind), or `unavailable` (Herdr is not
installed). The deployment, `dotfiles-agents status`, and
`dotfiles-agent-health --clients` all read that vocabulary, so the three
reports agree.

`dotfiles-agents status` reports the state of every selected agent in a
`HERDR` column, and `dotfiles-agent-health --clients` reports the same drift
as a warning without failing the check: integration drift affects restore and
resume, not launch.

The deployment records the observed state in
`~/.local/state/dotfiles/herdr.tsv` as `agent|kind|state` rows.

## The generated Herdr skill

Herdr ships its own skill for the agents it drives. When Herdr is present, the
deployment generates it from `herdr --skill` into the shared tree at
`~/.agents/skills/herdr/SKILL.md` and refreshes it when the installed binary
changed; unchanged bytes are never rewritten. The skill is generated, not a
catalog pin, so it is recorded in
`~/.local/state/dotfiles/generated-skills.tsv` as `name|root|generator`. The
skill pruning step reads that record and leaves the generated skill alone.

## Collaboration use

Only use Herdr from inside a Herdr pane. The check is:

```bash
test "${HERDR_ENV:-}" = 1
```

Outside that, do not inspect or control a session; use the one-shot client
commands from the shared instructions.

Typical flow, with one agent per worktree:

```bash
herdr worktree create --cwd . --branch task/review-a
herdr pane split --current --direction right
herdr agent start reviewer --kind pi --pane <pane-id>
herdr agent prompt reviewer "Review the diff; report findings only."
herdr agent wait reviewer --until idle --timeout 600000
herdr agent read reviewer
```

Rules that follow from the CLI:

- `agent start` requires an existing idle shell pane; it never creates layout.
- Supported kinds include `pi`, `claude`, `codex`, `kimi`, `opencode`, `qodercli`,
  and others. MiniMax Code is not a kind: run `mcode` as a pane command.
- Wait on `idle`, `done`, `blocked`, or `unknown` with `agent wait`; do not poll
  with sleeps. `unknown` is not proof of completion.
- Use `agent read` for output. Titles and badges are hints.
- Give each concurrent agent its own worktree; two agents in one checkout
  collide.
- Keep delegation at depth one: a Herdr-started agent must not start further
  agents unless the task asks for it.

## Codex under Herdr

Codex 0.166 (the repo pin) keeps hooks in its shared app-server daemon, which
retains the environment of the pane that first started it. Under Herdr that
pane identity is wrong, so every Codex session is reported to another pane and
cannot be resumed with the right command. Inside interactive Herdr shells,
`codex` resolves to `codex-herdr`: it checks `dotfiles-agent-health --codex`,
then runs `with-proxy --if-available codex --no-daemon`, so hooks stay in the
pane process. `--if-available` is what makes this safe on a host with no proxy:
the launcher then drops inherited variables instead of pointing Codex at a port
nothing serves.
Non-interactive `with-proxy codex exec` bypasses the shell wrapper and keeps
the shared daemon; it has no pane identity to preserve. Outside Herdr, `codex`
keeps the shared daemon.

`~/.codex/herdr-codex-resume.sh` is a custom SessionStart hook beside the
Herdr-installed `herdr-agent-state.sh`. It reports `codex-herdr resume <id>` as
the resume argv, so a workspace restore keeps the health gate, proxy, and
`--no-daemon`. The script is managed, but `~/.codex/hooks.json` is device-owned;
register it once after `herdr integration install codex`:

```bash
dotfiles-codex-herdr install
```

The deployment runs that registration after every codex integration install or
reinstall, because Herdr rewrites the hook file when it reinstalls. The final
client-settings merge runs after the Herdr step, so the merge preserves both
the Herdr entry and the managed resume hook.

The installer preserves every existing hook, removes an older copy of this
entry, and places it last so its resume argv wins. For reference, the entry is:

```json
{"hooks":[{"type":"command","command":"bash \"$HOME/.codex/herdr-codex-resume.sh\"","timeout":5}]}
```

Codex asks for hook trust once; approve it or the override is skipped.


## Worktree persistence

Herdr creates task worktrees under `worktrees.directory` (the repo config,
shipped with the developer bundle, pins the default `~/.herdr/worktrees`). Keep
that root on persistent storage: managed hosts use `~/.herdr` in their home; the
legacy T9K host links `~/.herdr` into `/t9k/mnt/joey/SHELL` through
`deployment/legacy/home-links.tsv`. Never create a task checkout under `/tmp`;
commit, merge, or archive the branch before closing a workspace. See the
worktree persistence rule in the shared agent instructions.

## Preflight

Before a restore, or when a pane cannot reach its provider, run
`~/.local/bin/dotfiles-agent-health`. The full check covers Mihomo, U.S.
egress, Caveman, the Codex app-server daemon, Herdr, and CodeGraph.
`--codex` narrows it to the Codex launch path (no CodeGraph), `--clients`
reports client binaries, config paths, and the Herdr integration drift,
and `--probe` adds one paid Codex model round trip. After a reboot,
`dotfiles-host-up up` chains the same dependency order and `up --restore`
starts the saved Herdr session. See
[agent health](AGENT_HEALTH.md) and [host bring-up](HOST_UP.md).

## Verified here

On the workstation (herdr 0.9.4, server running):

```bash
herdr status
herdr agent list
herdr pane list
herdr api snapshot
```

All returned JSON state for live panes and agents. `herdr agent start`,
`prompt`, `wait`, and `read` are the supported control path; their help text was
checked against 0.9.4.
