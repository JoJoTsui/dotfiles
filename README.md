# dotfiles

Chezmoi-managed dotfiles for Linux dev environments: shell, prompt, git, Python
toolchain, global CLI tools (via pixi), and the coding-agent configs
(Claude Code, Codex, kimi-code, pi, opencode).

The repo is the **source state**; `chezmoi` applies it to a host in **copy
mode** (plain files, no symlinks — config watchers in VS Code and Claude Code
reliably read them). It is meant for **new or test hosts**; the legacy T9K
container's live tree predates chezmoi and is never `chezmoi apply`-ed — see
`AGENTS.md`.

## Quick start (new host)

```bash
git clone https://github.com/JoJoTsui/dotfiles.git ~/dotfiles && cd ~/dotfiles
export GLM_API_TOKEN=...   # optional: Claude Code GLM token (default REPLACE_ME)
export KIMI_API_KEY=...    # optional: kimi-code key  (default REPLACE_ME)
bash bootstrap.sh
```

`bootstrap.sh` is idempotent: installs pixi and chezmoi into `~/.local/bin`,
runs `chezmoi init --apply <clone>`, `pixi global sync` (installs every CLI
tool from the manifest), clones nushell's `nu_scripts` completions (with a
mirror fallback), and optionally installs the system-wide bash banner.

## Host classes

`.chezmoi.toml.tmpl` picks a class at init — `t9k` (T9K/K8s container),
`linux`, or `win` — overridable with `DOTFILES_CLASS`. Only `t9k` gets
`~/.vscode-server` settings (`.chezmoiignore` gates it).

Template data (all from environment variables at init time, so credentials
never enter git):

| data | env var | default |
| --- | --- | --- |
| `class` | `DOTFILES_CLASS` | detected |
| `proxyUrl` | `HTTP_PROXY_URL` | `http://10.233.17.241:3128` |
| `glmBaseUrl` | `GLM_BASE_URL` | `https://open.bigmodel.cn/api/anthropic` |
| `glmToken` | `GLM_API_TOKEN` | `REPLACE_ME` |
| `kimiApiKey` | `KIMI_API_KEY` | `REPLACE_ME` |

## Layout (chezmoi source state)

```
.chezmoi.toml.tmpl          # host-class detection, copy mode, secrets from env
.chezmoiignore              # bookkeeping + non-$HOME payloads never applied
bootstrap.sh                # one-shot new-host setup (see above)
dot_env_core                # shared env + PATH, POSIX & idempotent (bash → nu)
dot_profile  dot_bashrc     # login: exec-nu guard; interactive init (fnm, pixi, mamba, starship, zoxide, direnv, fzf)
dot_gitconfig               # delta pager (side-by-side), zdiff3, rerere, gh helper
dot_condarc                 # TUNA mirrors, nvidia/pytorch/conda-forge/bioconda channels
dot_config/
  starship.toml             # Catppuccin powerline prompt
  direnv/direnvrc           # layout_micromamba
  git/ignore                # global gitignore incl. secret-pattern guardrails
  nushell/                  # env.nu, config.nu, micromamba.nu, direnv.nu, proxy.nu.tmpl
  opencode/opencode.jsonc   # canonical opencode config (headroom + MCPs)
dot_pixi/
  manifests/pixi-global.toml  # every global CLI tool (conda-forge envs)
  config.toml                 # netfs-redirect = never (network mount)
dot_claude/settings.json.tmpl    # Claude Code on GLM-5.3 / glm-5.3-flash
dot_codex/config.toml            # Codex CLI, env_key-based providers
dot_kimi-code/{config.toml.tmpl,tui.toml}
dot_pi/agent/{settings.json,models-store.json}
dot_vscode-server/…         # remote Machine settings (class t9k only)
system/bash.bashrc          # optional /etc banner+aliases (bootstrap installs)
docs/                       # CLAUDE_SETUP_T9K.md, vscode-win-settings.jsonc
clash/                      # Clash Verge profile merge (app config, not $HOME)
```

Files ending `.tmpl` are rendered; everything else is applied verbatim.
Auth/credential files (`auth.json`, `credentials`, `*keys.json`) are
git-ignored and always stay host-local.

## Toolchain: pixi global

All CLI tools (nu, starship, delta, direnv, fnm, fzf, gh, git, ruff, uv, helix,
zoxide, codex, micromamba, …) are declared in
`dot_pixi/manifests/pixi-global.toml` as per-tool conda-forge envs. On a host:
`pixi global sync` installs/updates them all; `pixi global update` bumps;
`pixi global add <pkg>` edits the manifest — commit the change.

## Coding agents

| Agent | Managed file(s) | Local-only / secrets | Notes |
| --- | --- | --- | --- |
| **Claude Code** | `~/.claude/settings.json` (GLM-5.3) | plugins, hooks, statusline, `settings.local.json`, `~/.claude.json` | token/base URL from env; MCP servers: `claude mcp add --scope user <name>` (or project `.mcp.json` with `${VAR}` expansion); T9K container workarounds → `docs/CLAUDE_SETUP_T9K.md` |
| **Codex** | `~/.codex/config.toml` | `auth.json`, per-project trust, hook hashes | providers use `env_key` (`DEEPSEEK_API_KEY`, `OMNIROUTE_API_KEY`) — no tokens in the file; codegraph MCP included |
| **kimi-code** | `~/.kimi-code/config.toml.tmpl`, `tui.toml` | `credentials/`, `oauth/`, sessions | key injected from `KIMI_API_KEY` at init; `kimi login` per host |
| **pi** | `~/.pi/agent/settings.json`, `models-store.json` (MiniMax M2.7/M3 catalog) | `auth.json` (MiniMax key), `sessions/`, `trust.json` | minimal terminal harness; `pi auth login` per host |
| **opencode** | `~/.config/opencode/opencode.jsonc` | `~/.opencode` install, plugins | headroom provider + codegraph/headroom MCPs, serena disabled; watcher off for network FS |

Common pattern: **config in git, credentials on the host** — auth flows run per
host (`claude` login / env token, `codex login`, `kimi login`, `pi auth login`).

## Validating on a simulated host

```bash
H=/tmp/dotfiles-sim; rm -rf "$H"; mkdir -p "$H"
HOME="$H" chezmoi init --apply "$PWD"     # class auto-detected
HOME="$H" DOTFILES_CLASS=linux chezmoi init --apply "$PWD"   # other branch
find "$H" -maxdepth 3                     # inspect the applied state
chezmoi diff                              # drift vs current source (on a real host)
```

## Maintenance

Fold any host-side config change back into the source file, validate on the
simulated host, then commit with the `[tag]: message` convention (tags:
`chore shell bash nu claude agents codex devops direnv conda clash`) — full
workflow, invariants and secret rules in [AGENTS.md](AGENTS.md).
