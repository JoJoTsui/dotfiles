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

The deployment foundation implements verified managers, working-source file
application, pinned common tools, and frozen Bun agent installation. Use
`--apply-only` for configuration validation, or `--agents-only` to install
clients with an already available pinned Bun/Node toolchain. Shell/history and
foreign native validation are covered by their separate implementation slices.

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
.chezmoidata.toml           # canonical shared shell defaults and PATH priority
dot_env_core.tmpl           # generated POSIX env for bash+zsh: PATH, EDITOR,
                            # rustup TUNA mirrors, noproxy/unproxy (rendered URL)
dot_profile                 # login shells: exec-nu guard (TTY + no Claude session)
dot_bashrc                  # bash init: pixi, mamba, starship, zoxide,
                            # direnv, fzf
dot_zshenv                  # every zsh: env_core + umask (bash parity)
dot_zshrc                   # interactive zsh: same inits as .bashrc (+ compinit)
dot_local/bin/executable_nu-login   # guarded interactive Nu; Bash for scripts
dot_local/bin/executable_dotfiles-shell-prepare # validated Nu startup artifacts
dot_local/bin/executable_bat-modules    # bat syntax/module installer (bash)
dot_local/bin/executable_fetchChromSizes  # UCSC chrom.sizes fetcher (POSIX sh)
dot_gitconfig               # identity, delta pager (side-by-side), zdiff3,
                            # rerere, lfs filters, gh credential helper
dot_condarc                 # TUNA mirrors, nvidia/pytorch/conda-forge/bioconda channels
deployment/common-tools.tsv  # exact common requirements and command exposures
deployment/agents/           # exact per-client package manifests + bun.lock
deployment/inventory/        # preserved optional/specialist inventory
dot_config/
  starship.toml             # Catppuccin powerline prompt
  direnv/direnvrc           # layout_micromamba
  git/ignore                # global gitignore incl. secret-pattern guardrails
  herdr/config.toml         # agent muxer: catppuccin theme, default shell nu
  pip/pip.conf              # PyPI via TUNA mirror
  uv/uv.toml                # python-preference=managed + TUNA default index
  dotfiles/pixi-global.toml.tmpl # desired tools merged into the local registry
  zellij/config.kdl.tmpl    # multiplexer: custom keybinds, default_shell nu-login
  nushell/                  # env.nu.tmpl, config.nu, adjacent managed resources
  opencode/opencode.jsonc.tmpl # OpenCode2 config (headroom + MCPs)
dot_pixi/
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

Shared settings are generated from one model:

- `.chezmoidata.toml` owns shared values and managed PATH priority. Its POSIX
  adapter `~/.env_core` is sourced by `.bashrc` and `~/.zshenv`; its guarded
  Nu adapter gives standalone Nu the same defaults. Device overrides survive.
- Interactive inits (pixi completion, micromamba, starship, zoxide,
  direnv, fzf) are kept structurally identical across `.bashrc` and
  `.zshrc`; zsh adds `compinit`, which its completion system requires.
- Multiplexers start nu the same way: zellij panes launch the managed
  `~/.local/bin/nu-login` (TTY/client guard → Nu), herdr sets
  `default_shell = "nu"`.

zoxide and `logs` are available in all supported shells. `logs` runs Tailspin
with the managed less pager; `logs --print file.log` prints without paging.
Startup needs no external completion checkout. Bootstrap generates and validates
Nu prompt/completion artifacts after installation. See
[shared shell settings](docs/SHARED_SHELL_SETTINGS.md) for guards and test evidence.

## Toolchain: pixi global

The pinned Pixi bootstrap installs under `~/.pixi/bin`. Common tools are
declared once in `deployment/common-tools.tsv` and rendered as per-tool
conda-forge environments in `~/.config/dotfiles/pixi-global.toml`. Bootstrap
merges owned entries into the device's Pixi registry, preserving unrelated
environments, extra dependencies/exposures, and channels, then runs sync.
RTK uses package `rtk-cli` and exposes `rtk`; Tailspin exposes `tspin` and
includes `less`. Bun and Node are common defaults. Python/pip and uv discover
the rendered TUNA configuration.

Pixi global has no lockfile. Exact direct pins are enforced, while solver-selected
builds and transitive dependencies can drift. Update source pins deliberately
and rerun validation; an unqualified global update is not the maintained update
path. Chezmoi and the lightweight Rustup manager use checksum-verified pinned
upstream assets. Rustup installs no compiler toolchain by default.

Bioinformatics, GPU, desktop, and additional developer tools remain discoverable
under `deployment/inventory`; they are opt-in rather than common defaults.
Native Windows bootstrap exceptions and execution are supplied by ticket 11;
Unix-only conda entries are excluded from its desired manifest.

Select whole optional bundles explicitly:

```bash
bash bootstrap.sh --profile linux-remote-compute --bundles bio,gpu --plan
bash bootstrap.sh --profile linux-workstation --bundles developer
```

`--bundles none` is the default. Invalid names and unsupported whole-bundle
targets fail before creating state. Every selected tool has its own pinned Pixi
environment and exposed command. Herdr/Zellij settings accompany `developer`,
and `fetchChromSizes` accompanies `bio`. Reapplying with fewer bundles preserves
previous installations. Read [bundle inventory](deployment/inventory/README.md)
for target support, host prerequisites, and retained setup-on-use capabilities.

Env vars and configs only ever reference binaries that this manifest (or a
bootstrap step) installs — see the matching invariant in `AGENTS.md`.

## Coding agents

| Agent | Managed file(s) | Local-only / secrets | Notes |
| --- | --- | --- | --- |
| **Claude Code** | `~/.claude/settings.json` (GLM-5.3) | plugins, hooks, statusline, `settings.local.json`, `~/.claude.json` | token/base URL from env; MCP servers: `claude mcp add --scope user <name>` (or project `.mcp.json` with `${VAR}` expansion); T9K container workarounds → `docs/CLAUDE_SETUP_T9K.md` |
| **Codex** | `~/.codex/config.toml` | `auth.json`, per-project trust, hook hashes | providers use `env_key` (`DEEPSEEK_API_KEY`, `OMNIROUTE_API_KEY`) — no tokens in the file; codegraph MCP included |
| **kimi-code** | `~/.kimi-code/config.toml.tmpl`, `tui.toml` | `credentials/`, `oauth/`, sessions | key injected from `KIMI_API_KEY` at init; `kimi login` per host |
| **pi** | `~/.pi/agent/settings.json`, `models-store.json` (MiniMax M2.7/M3 catalog) | `auth.json` (MiniMax key), `sessions/`, `trust.json` | minimal terminal harness; `pi auth login` per host |
| **opencode** | `~/.config/opencode/opencode.jsonc` | plugins, local auth/state | pinned OpenCode2 schema; built-in Headroom provider, optional Headroom MCP disabled; remote profile ignores update events |
| **herdr** | `~/.config/herdr/config.toml` (catppuccin theme, `default_shell = "nu"`) | logs, sockets, `session.json`, `.plugins.lock`, release notes | agent terminal multiplexer/server (Rust, v0.9); binary from the pixi manifest (+ its self-updater in `~/.local/bin`); `herdr plugin install` state stays local |

All five clients install through Bun by default. `--agents none` or
`--agents codex,kimi` controls installation without removing omitted clients;
CodeGraph remains a default independent of selection. Each exact manifest and
frozen Bun lock installs into `~/.bun/managed/<name>` and exposes real launchers
under `~/.bun/bin` and `~/.local/bin` using managed Node. The existing global
Bun registry remains intact. Legacy clients and optional integrations remain
documented under `deployment/inventory`. See [agent installation](docs/AGENT_INSTALLATION.md)
for versions, lifecycle trust, update policy, and isolated diagnostic checks.

Common pattern: **config in git, credentials on the host** — auth flows run
per host (`claude` login / env token, `codex login`, `kimi login`,
`pi auth login`).

Shared instructions and the portable 105-skill library deploy by default,
including with `--agents none` and `--apply-only`. One owned source produces
regular shared files and Claude's discovery adapter. Managed instruction blocks
preserve device-specific text; unrelated skills and built-ins remain intact.
See [agent payloads](docs/AGENT_PAYLOAD.md) for discovery, ownership, prerequisite
setup on use, and offline checks.

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

# Separate real Linux network installation and harmless CLI diagnostics.
DOTFILES_TEST_INSTALL=1 python3 -m unittest discover -s tests -p test_common_install.py -v
```

## Maintenance

Fold any host-side config change back into the source file, validate on the
simulated host, then commit with the `[tag]: message` convention (tags:
`chore shell bash nu zsh claude agents codex devops direnv conda clash`) —
full workflow, invariants and secret rules in [AGENTS.md](AGENTS.md).
