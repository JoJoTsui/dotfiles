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
