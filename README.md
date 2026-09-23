# dotfiles

Personal dev-environment configuration for Linux dev containers on the
TensorStack/T9K ML platform. The environment lives on a **persistent network
mount** (`/t9k/mnt`) that survives ephemeral containers, so the configs are kept
in one place and symlinked into `$HOME` on each new container.

> **Status (2026-09):** this repo is a *snapshot* of the live config tree at
> `/t9k/mnt/joey/SHELL` and has drifted behind it (pixi, rustup mirrors,
> GLM-5.2 Claude config, expanded `.condarc`, and more exist only on the live
> tree). Treat the live tree as the source of truth and this repo as the
> curated, version-controlled mirror. See `AGENTS.md` for the sync workflow.

## What it configures

| Area | Tooling |
| --- | --- |
| Shells | bash (login + system `/etc/bash.bashrc`), Nushell (interactive default) |
| Prompt | Starship (Catppuccin powerline, `starship/starship.toml`) |
| Env | `.env_core` shared by bash and nushell (paths, `EDITOR=hx`, mirrors) |
| Python/conda | micromamba + `.condarc`, direnv `layout_micromamba`, `micromamba.nu` for nushell |
| Node | fnm (`fnm env --use-on-cd`) |
| Git | `.gitconfig` with delta pager, zdiff3 conflicts, gh credential helper |
| Editors | Helix (`EDITOR=hx`), VS Code remote/local settings snippets |
| AI | Claude Code on GLM models, MCP servers, T9K container workarounds |
| Proxy | Clash Verge ruleset merge template, `nuproxy`/`unproxy` for nushell |

## Layout

```
.env_core               # shared env vars + PATH (sourced by bash; kept idempotent)
.profile                # login shell: sources .bashrc, then exec nu for humans
.gitconfig  .gitignore
bash/                   # .bashrc (user), bash.bashrc (system-wide banner/aliases)
nushell/                # env.nu, config.nu, micromamba.nu, direnv.nu, proxy.nu
starship/starship.toml
direnv/direnvrc         # layout_micromamba
conda/.condarc
claude/                 # Claude Code on GLM: settings, MCP servers, T9K setup guide
vscode/                 # settings snippets: t9k (remote container) / win (local)
clash/Merge.yaml        # Clash Verge profile-merge template (superseded on host)
link_dotfiles.new.sh    # symlink installer: live tree -> $HOME
```

Note `claude/glm-keys.json` is intentionally **untracked** (see Secrets).

## How the pieces fit

1. `$HOME` (`/t9k/mnt`) gets symlinks into the persistent tree
   `/t9k/mnt/joey/SHELL` ("JSHELL"), created by `link_dotfiles.new.sh`.
2. A login shell runs `.profile`, which sources `.bashrc` (which sources
   `.env_core`) and — only for a real interactive TTY outside a Claude Code
   session — `exec nu` into Nushell.
3. Nushell picks up `~/.config/nushell/{env,config}.nu`, which wire up Starship,
   zoxide, direnv, micromamba, and completions from
   `JSHELL/CLIs/nushell/` (vendored `nu_scripts` checkout — outside this repo).
4. The guard clause matters: Claude Code spawns background shells, and an
   unconditional `exec nu` crashes them (`STDIN is not a TTY`).

## Deployment

```bash
bash link_dotfiles.new.sh    # links JSHELL configs into $HOME, backing up to *.bak
```

The script operates on the **live tree** (`$HOME/joey/SHELL`), not on this
repo's layout, and also swaps `/etc/bash.bashrc` for the banner/aliases version
(needs sudo). Known rough edges: `--dry-run` is parsed but not honored, and the
`/etc/bash.bashrc` `&&`/`;` sequencing runs the `ln` unconditionally.

## Claude Code on T9K containers

`claude/CLAUDE_SETUP_T9K.md` documents the three container-specific
workarounds, kept because they are easy to lose on a fresh container:

1. **Watcher crash on the network FS** → symlink `~/.claude` (global) and
   `.claude` (per project) caches into `/tmp`.
2. **`exec nu` crashing background bash** → the interactive-TTY guard in
   `.profile` / `.bashrc`.
3. **`ENOSPC` file-watcher limit** → `CHOKIDAR_USEPOLLING=1` (exported in
   `.env_core`, also set in VS Code terminal env).

## Secrets

API tokens live next to configs on the live tree (Claude settings, `glm-keys.json`).
The policy:

- `*keys.json` is git-ignored; `claude/glm-keys.json` must stay untracked.
- When syncing live files back into this repo, **redact** every token
  (`ANTHROPIC_AUTH_TOKEN`, `CONTEXT7_TOKEN`, gateway `sk-…`, `glmfix_…`) to a
  placeholder.
- If a token ever lands in git history, rotate it — history rewriting is not a
  substitute for rotation.

## Syncing this repo

The live tree is the source of truth. To bring the repo up to date: diff each
mirrored file against its live counterpart, copy the live version in, redact
secrets, and commit with the repo's `[tag]: message` convention
(`[bash]`, `[nu]`, `[claude]`, `[shell]`, `[conda]`, `[devops]`, `[chore]`).
The per-file mapping (repo path ↔ live path) and full rules are in `AGENTS.md`.
