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
then runs `with-proxy codex --no-daemon`, so hooks stay in the pane process.
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
reports client binaries and config paths, and `--probe` adds one paid Codex
model round trip. See [agent health](AGENT_HEALTH.md).

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
