# Worktrunk

[Worktrunk](https://worktrunk.dev) is a Git worktree manager built for parallel
AI agent workflows: one worktree per task or agent, `wt list` to see which
worktree is busy, and a `wt switch` that moves the shell into the worktree it
selects. The deployment installs it and teaches the managed agents to use it.

## What the deployment owns

| Part | Owner | Notes |
| --- | --- | --- |
| `wt` command | `deployment/common-tools.tsv` | conda-forge package `worktrunk`, exposed as `wt` |
| Agent guidance | `deployment/skills.tsv` | upstream `worktrunk` and `wt-switch-create` skills |
| Bash/Zsh integration | `dot_bashrc`, `dot_zshrc` | the managed binary's `wt config shell init bash|zsh` |
| Nushell integration | `dot_local/bin/executable_dotfiles-shell-prepare` | generated `wt.nu` in the vendor autoload directory |
| Client plugins | `deployment/agents.sh` | `wt config plugins <client> install` for the installed clients |

The CLI's exact Pixi pin lives with the other common tools. macOS can adopt a
compatible command or Homebrew formula and exposes it through the common
launcher directory. The skill bytes are fetched from the upstream repository at the
revision recorded in `deployment/skills.lock.tsv`; they are never vendored into
this source. The plugin files are client state: the CLI writes them, and the
deployment never reproduces their content.

Agent installation finishes through the existing client-settings merger.
This preserves plugin-added settings and gives the first deployment the same
serialization as later applies. Claude and Codex plugin installers write their
own settings format before that final merge.

## Native Windows

`wt` is not deployed on native Windows, where the name belongs to Windows
Terminal. WSL keeps the Unix deployment and the `wt` command. The upstream
skill stays in the shared catalog on every platform; on a Windows host it is
guidance for a command that is not installed.

## Device-local state

The worktrunk user configuration (`~/.config/worktrunk/config.toml`), the
per-client plugin files, the Claude Code statusline, and the worktrees
themselves belong to the device. The deployment does not manage them and does
not remove them.

```bash
wt config show      # configuration, shell integration, and plugin state
wt list             # worktrees with the agent activity markers
```

The Claude Code statusline is installed separately, because it changes what the
user sees:

```bash
wt config plugins claude install-statusline
```

## Agent handoff

The upstream skill documents the handoff pattern this deployment already
supports: a new pane in the managed Zellij session runs the agent in its own
worktree.

```bash
zellij run -- wt switch --create fix-auth-bug -x claude -- 'Extend the session timeout.'
```

## Before changing this

Read [agent payloads](AGENT_PAYLOAD.md) before changing the skill rows or the
plugin step, and [the deployment boundary](DEPLOYMENT_BOUNDARY.md) before
changing what a step installs. The client plugin step runs inside the agent
step, so it inherits that step's proxy rule and its network expectations.
