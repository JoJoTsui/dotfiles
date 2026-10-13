# dotfiles

Chezmoi-managed dotfiles for Linux dev environments: shell, prompt, git, Python
toolchain, global CLI tools (via pixi), and the coding-agent configs
(Claude Code, Codex, kimi-code, pi, opencode, herdr).

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

Inspect the selected deployment before running it:

```bash
bash bootstrap.sh --profile linux-remote-compute --plan
bash bootstrap.sh --profile linux-workstation --home /tmp/example-home --apply-only
```

The public boundary applies this **working tree**, including uncommitted
changes, with an explicit source and destination. Every XDG and package-manager
state root follows the selected home. Planning prints JSON without creating
files, installing, authenticating, importing history, or indexing projects.
Ordinary deployment changes user files only; it has no system or account
login-shell action. See [the deployment boundary](docs/DEPLOYMENT_BOUNDARY.md)
for the adapter contract and isolated verification.

The initial deployment foundation implements chezmoi provisioning and file
application. Common-tool and agent installer adapters currently fail with
explicit pending-ticket messages; tickets 02 and 04 implement them before the
complete bootstrap is released. Use `--apply-only` for configuration validation.

## Deployment profiles

Platform (`linux`, `macos`, `wsl`, `windows`) and host role (`workstation`,
`remote-compute`) are independent. Platform detection distinguishes WSL;
role defaults to workstation even over SSH. Select both through a preset such
as `--profile linux-remote-compute`, or use `--platform` and `--role`.
Command-line selections override environment inputs; conflicting explicit
presets and component selections fail before writing files.

Legacy `--class t9k` / `DOTFILES_CLASS=t9k` maps to Linux remote compute;
`linux` and `win` map to their workstation profiles. Remote compute targets
receive `~/.vscode-server` settings. The current host uses the documented
`linux-remote-compute` preset and remains outside deployment validation.

Template data (all from environment variables at init time, so credentials
never enter git):

| data | env var | default |
| --- | --- | --- |
| `platform` | `DOTFILES_PLATFORM` | detected |
| `role` | `DOTFILES_ROLE` | workstation |
| `arch` | `DOTFILES_ARCH` | detected; x86_64/aarch64 |
| `class` | `DOTFILES_CLASS` (legacy input) | compatibility metadata |
| `proxyUrl` | `HTTP_PROXY_URL` | `http://127.0.0.1:7890` |
| `glmBaseUrl` | `GLM_BASE_URL` | `https://open.bigmodel.cn/api/anthropic` |
| `glmToken` | `GLM_API_TOKEN` | `REPLACE_ME` |
| `kimiApiKey` | `KIMI_API_KEY` | `REPLACE_ME` |

## Layout (chezmoi source state)

```
.chezmoi.toml.tmpl          # profile data, copy mode, secrets from env
.chezmoiignore              # bookkeeping + non-$HOME payloads never applied
bootstrap.sh                # one-shot new-host setup (see above)
deployment/                 # pure profile resolution and installer adapters
tests/test_deployment.py    # public boundary checks in disposable homes
dot_env_core.tmpl           # shared POSIX env for bash+zsh: PATH, EDITOR,
                            # rustup TUNA mirrors, noproxy/unproxy (rendered URL)
dot_profile                 # login shells: exec-nu guard (TTY + no Claude session)
dot_bashrc                  # bash init: fnm, pixi, mamba, starship, zoxide,
                            # direnv, fzf
dot_zshenv                  # every zsh: env_core + umask + fnm (bash parity)
dot_zshrc                   # interactive zsh: same inits as .bashrc (+ compinit)
dot_local/bin/executable_nu-login   # login wrapper: bash -l -> exec nu (zellij
                                    # shell); executable_ => +x in target state
dot_local/bin/executable_bat-modules    # bat syntax/module installer (bash)
dot_local/bin/executable_fetchChromSizes  # UCSC chrom.sizes fetcher (POSIX sh)
dot_gitconfig               # identity, delta pager (side-by-side), zdiff3,
                            # rerere, lfs filters, gh credential helper
dot_condarc                 # TUNA mirrors, nvidia/pytorch/conda-forge/bioconda channels
dot_bun/install/global/package.json  # bun global packages = coding-agent CLI suite
dot_config/
  starship.toml             # Catppuccin powerline prompt
  direnv/direnvrc           # layout_micromamba
  git/ignore                # global gitignore incl. secret-pattern guardrails
  herdr/config.toml         # agent muxer: catppuccin theme, default shell nu
  pip/pip.conf              # PyPI via TUNA mirror
  uv/uv.toml                # python-preference=managed + TUNA default index
  zellij/config.kdl.tmpl    # multiplexer: custom keybinds, default_shell nu-login
  nushell/                  # env.nu, config.nu, micromamba.nu, direnv.nu, proxy.nu.tmpl
  opencode/opencode.jsonc   # canonical opencode config (headroom + MCPs)
dot_pixi/
  manifests/pixi-global.toml  # every global CLI tool (conda-forge envs)
  config.toml                 # netfs-redirect = never (network mount)
dot_claude/settings.json.tmpl    # Claude Code on GLM-5.3 / glm-5.3-flash
dot_codex/config.toml            # Codex CLI, env_key-based providers
dot_kimi-code/{config.toml.tmpl,tui.toml}
dot_pi/agent/{settings.json,models-store.json}
dot_vscode-server/…         # remote compute Machine settings
system/bash.bashrc          # manual system banner payload; never auto-applied
docs/                       # CLAUDE_SETUP_T9K.md, vscode-win-settings.jsonc
clash/                      # Clash Verge profile merge (app config, not $HOME)
```

Files ending `.tmpl` are rendered; everything else is applied verbatim.
Auth/credential files (`auth.json`, `credentials`, `*keys.json`) are
git-ignored and always stay host-local.

## Shells

**nushell is the preferred shell** — login shells exec into it via the TTY
guard in `~/.profile` (exception for Claude Code sessions:
`docs/CLAUDE_SETUP_T9K.md`). **bash and zsh are installed by default** from
the pixi manifest, because coding agents spawn them (`SHELL=/bin/bash`,
`#!/bin/sh` scripts, `zsh -c`).

Shared settings are defined once and mirrored:

- `~/.env_core` (POSIX, idempotent) is sourced by `.bashrc` and `~/.zshenv`;
  it owns PATH, `EDITOR`, rustup TUNA mirrors, LS_COLORS and the
  `noproxy`/`unproxy` toggles.
- `dot_config/nushell/env.nu` mirrors those values with guarded
  `$env.X? | default …`, so standalone `nu` (spawned without bash) behaves
  the same.
- Interactive inits (fnm, pixi completion, micromamba, starship, zoxide,
  direnv, fzf) are kept structurally identical across `.bashrc` and
  `.zshrc`; zsh adds `compinit`, which its completion system requires.
- Multiplexers start nu the same way: zellij panes launch the managed
  `~/.local/bin/nu-login` (`bash -l` → `exec nu`), herdr sets
  `default_shell = "nu"`.

## Toolchain: pixi global

All CLI tools (nu, starship, delta, direnv, fnm, fzf, gh, git, ruff, uv,
helix/`hx`, ty, vivid, python/`pip`, zellij, herdr, codex, micromamba,
**bash, zsh, bun**, …) are declared in
`dot_pixi/manifests/pixi-global.toml` as per-tool conda-forge envs. On a
host: `pixi global sync` installs/updates them all; `pixi global update`
bumps; `pixi global add <pkg>` edits the manifest — commit the change.

Env vars and configs only ever reference binaries that this manifest (or a
bootstrap step) installs — see the matching invariant in `AGENTS.md`.

## Coding agents

| Agent | Managed file(s) | Local-only / secrets | Notes |
| --- | --- | --- | --- |
| **Claude Code** | `~/.claude/settings.json` (GLM-5.3) | plugins, hooks, statusline, `settings.local.json`, `~/.claude.json` | token/base URL from env; MCP servers: `claude mcp add --scope user <name>` (or project `.mcp.json` with `${VAR}` expansion); T9K container workarounds → `docs/CLAUDE_SETUP_T9K.md` |
| **Codex** | `~/.codex/config.toml` | `auth.json`, per-project trust, hook hashes | providers use `env_key` (`DEEPSEEK_API_KEY`, `OMNIROUTE_API_KEY`) — no tokens in the file; codegraph MCP included |
| **kimi-code** | `~/.kimi-code/config.toml.tmpl`, `tui.toml` | `credentials/`, `oauth/`, sessions | key injected from `KIMI_API_KEY` at init; `kimi login` per host |
| **pi** | `~/.pi/agent/settings.json`, `models-store.json` (MiniMax M2.7/M3 catalog) | `auth.json` (MiniMax key), `sessions/`, `trust.json` | minimal terminal harness; `pi auth login` per host |
| **opencode** | `~/.config/opencode/opencode.jsonc` | `~/.opencode` install, plugins | headroom provider + codegraph/headroom MCPs, serena disabled; watcher off for network FS |
| **herdr** | `~/.config/herdr/config.toml` (catppuccin theme, `default_shell = "nu"`) | logs, sockets, `session.json`, `.plugins.lock`, release notes | agent terminal multiplexer/server (Rust, v0.9); binary from the pixi manifest (+ its self-updater in `~/.local/bin`); `herdr plugin install` state stays local |

The agent CLIs themselves are recorded in
`~/.bun/install/global/package.json` (claude-code, kimi-code, opencode,
pi-coding-agent, codegraph, larksuite …) and installed by `bootstrap.sh` via
`bun add -g --trust`.

Common pattern: **config in git, credentials on the host** — auth flows run
per host (`claude` login / env token, `codex login`, `kimi login`,
`pi auth login`).

## Validating on a simulated host

```bash
# Existing chezmoi can be supplied without installing into the current host.
simulated_home=$(mktemp -d /tmp/dotfiles-sim.XXXXXX)
DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh \
  --source "$PWD" --home "$simulated_home" --class t9k --apply-only
eza --all "$simulated_home"
rm -rf "$simulated_home"

# Automated acceptance checks (no network or real account operations).
DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest discover -s tests -v
```

## Maintenance

Fold any host-side config change back into the source file, validate on the
simulated host, then commit with the `[tag]: message` convention (tags:
`chore shell bash nu zsh claude agents codex devops direnv conda clash`) —
full workflow, invariants and secret rules in [AGENTS.md](AGENTS.md).
