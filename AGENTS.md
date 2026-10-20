# AGENTS.md

Read `README.md` for orientation (layout, deployment profiles, coding-agent table).
This file is the operational contract for working in this repo.

## Model

This repo is a **chezmoi source state** applied to new/test hosts in copy mode.
Rules that follow from it:

- The repo is the source of truth. Fold host changes *into it*; never edit a
  target host and consider the job done.
- **Never run `chezmoi init/apply` against this session's real `$HOME`.** The
  legacy T9K live tree (pre-chezmoi) would be overwritten. Validation happens on
  a simulated home only (recipe below).

## Naming

- `dot_x` → `~/x`; `dot_config/...` → `~/.config/...`; nested names map 1:1
  (`dot_pi/agent/settings.json` → `~/.pi/agent/settings.json`).
- Files needing template data end in `.tmpl` (suffix stripped on apply);
  without it, contents apply verbatim.
- `.chezmoiignore` patterns match **target** names (verified via
  `chezmoi ignored`), and cover everything not meant for `$HOME`:
  `README.md`, `AGENTS.md`, `bootstrap.sh`, `deployment`, `tests`, `docs`,
  `system`, `clash`, `.vscode-server` (workstation roles).

## Template data

Defined in `.chezmoi.toml.tmpl`, sourced from environment variables at init:
`platform` (`DOTFILES_PLATFORM`), `role` (`DOTFILES_ROLE`, default workstation),
`arch` (`DOTFILES_ARCH`), legacy `class` metadata, `proxyUrl`
(`HTTP_PROXY_URL`), `glmBaseUrl` (`GLM_BASE_URL`), `glmToken`
(`GLM_API_TOKEN`), `kimiApiKey` (`KIMI_API_KEY`). Defaults keep unattended
init non-interactive. `bootstrap.sh` resolves profile presets and legacy aliases
then exports canonical selectors. Read `docs/DEPLOYMENT_BOUNDARY.md` when
changing selection, planning, state isolation, or installer adapters.
Token defaults are the literal `REPLACE_ME` — a rendered
target containing `REPLACE_ME` is healthy, a committed real token is an
incident (rotate it; history rewrite is not a substitute).

## Secrets

- Never stage `*keys.json`, `auth.json`, `credentials`, `*.pem`, `*.token`
  (git-ignored at repo root *and* via the global gitignore). `claude/glm-keys.json`
  exists untracked on the legacy host — leave it that way.
- When copying config from a live host, redact tokens/keys/bearer headers to
  placeholders first (`ANTHROPIC_AUTH_TOKEN`, `CONTEXT7_TOKEN`, `sk-…`,
  `glmfix_…`, oauth `key =` fields).
- Codex providers take `env_key` names, not values — keep it that way.

## Validating a change (simulated host)

1. Edit the source file(s); commit-worthy changes are staged but uncommitted.
2. Use a fresh `simulated_home=$(mktemp -d /tmp/dotfiles-sim.XXXXXX)` and run
   `DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh --source "$PWD" --home "$simulated_home" --class t9k --apply-only`.
   The boundary applies the **working tree** and isolates XDG/package-manager
   roots. Repeat with `--class linux` in a fresh simulated home to exercise
   the ignore branch. `init --apply "$PWD"` clones committed HEAD and misses
   working changes; the public bootstrap does not use that form.
3. Check rendered values with `rg`, confirm required files are regular files,
   then delete the simulated home after any shell checks.
4. For nushell edits, also run
   `nu --config "$simulated_home/.config/nushell/config.nu" --env-config "$simulated_home/.config/nushell/env.nu" -c 'print "ok"'`
   with `JOEY/JSHELL/...` unset (`env -u`) — config must bootstrap standalone
   without the host's external completion checkout. Read
   `docs/SHARED_SHELL_SETTINGS.md` for preparation and interactive checks.

Run `DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest discover -s tests -v`
for changes to the public deployment boundary; actual apply tests report a skip
when chezmoi is unavailable. They must run before claiming application passed.

Done when: the simulated apply succeeds for both legacy profiles, the nushell check
passes (if touched), `git status` shows no secret files, and the commit body
explains every changed pair.

## Invariants

- **`.env_core` is POSIX sh and idempotent** (`: "${VAR:=...}"` guards);
  bash sources it before the interactive check so non-interactive shells get PATH.
- **Shared settings are defined once**: `.chezmoidata.toml` owns shared defaults
  and PATH priority. `dot_env_core.tmpl` and
  `dot_config/nushell/env.nu.tmpl` render its POSIX/Nu syntax; change the model,
  then verify both adapters. Proxy input comes from `proxyUrl` and is quoted
  separately for each shell. The `.bashrc` and `.zshrc` interactive blocks keep
  equivalent managed-tool hooks (Zsh adds its required `compinit`).
- **Env vars and managed binaries must match**: when a config or env var
  implies a command, the pixi manifest or a bootstrap step must install it in
  the same commit (`EDITOR=hx` → helix exposed as `hx`; `RUSTUP_*` → the
  rustup bootstrap step; `pip.conf` → the `python`/`pip` env; the vscode `ty`
  setting → the `ty` env; zellij's `default_shell` → managed
  `~/.local/bin/nu-login`).
- **Legacy tool dirs stay off PATH**: `.env_core`/`env.nu` keep `$GIZMO`/
  `$BIO_GIZMO`/`$NUSHELL_PATH` as variables for legacy hosts and scripts, but
  never prepend them — every CLI (bio tools included) comes from the pixi
  manifest or a declared bootstrap exception. Add common tools to
  `deployment/common-tools.tsv`; read `deployment/inventory/README.md` when
  changing optional ownership. Desired manifests under `.config/dotfiles`
  merge into device registries; source application never replaces them.
- **Scripts need the `executable_` source prefix**: chezmoi derives a target's
  exec bit from that attribute, *not* from the source file's mode (a 0755
  source without it renders 0644 — verified on chezmoi 2.59.1 and 2.72.2), so
  every managed script is named `dot_local/bin/executable_*` and lands
  `~/.local/bin/<name>` with mode 0755.
- **The exec-nu guard** in `dot_profile`/`dot_bashrc` stays POSIX-safe and
  fires only for a real interactive TTY outside a Claude Code session
  (rationale: `docs/CLAUDE_SETUP_T9K.md`).
- **`dot_config/nushell/env.nu.tmpl` keeps guarded `$env.JOEY? | default` bootstrap
  + `path add … uniq`** — standalone `nu` (spawned without bash) must still
  resolve compatibility variables while `micromamba.nu` invokes managed
  `MAMBA_EXE`, never a legacy tool tree.
- **JSONC files**: `dot_config/opencode/opencode.jsonc`,
  `dot_vscode-server/…/settings.json.tmpl`, `docs/vscode-win-settings.jsonc`
  — validate as JSON-with-comments, not shell (historical `.sh` naming retired).
- Not applied to `$HOME` (ignored): `system/`, `clash/`, `docs/`, `deployment/`,
  `tests/`. Ordinary bootstrap has no system or account login-shell action.
- **Legacy home symlinks are explicit and opt-in**:
  `deployment/legacy/link-home.sh` and its ignored `home-links.tsv` manifest
  maintain the pre-chezmoi T9K tree. Bootstrap never runs them; managed homes
  stay in copy mode. The utility validates before writing, backs up replaced
  targets, and requires `--system` for `/etc` changes. Read
  `docs/LEGACY_HOME_LINKS.md` before adding state roots to the manifest.
- **Agent payloads use the public bootstrap copier**: raw skills under ignored
  `deployment/agent-payload/` retain filenames and permissions without executing
  helpers. Its catalog produces regular discovery files and managed instruction
  blocks while preserving unrelated device content. Read `docs/AGENT_PAYLOAD.md`
  before changing global instructions, skills, or their copy adapters.
- **Client settings merge through bootstrap**: defaults under ignored
  `deployment/client-settings/` merge into runtime paths excluded from Chezmoi.
  Read `docs/AGENT_SETTINGS.md` when changing client settings, MCP registration,
  ownership, or preservation. Index creation stays an explicit project action.

## Known rough edges

- Nu's vendor autoload runs for interactive sessions and is omitted by ordinary
  `-c` execution. `dotfiles-shell-prepare` validates generated resources
  explicitly; interactive tests establish prompt/completion discovery.
- `.chezmoi.toml.tmpl` explicitly persists `sourceDir`; bootstrap passes source,
  destination, config, cache, and state paths on both init and apply.
- Legacy live tree (JSHELL) is still symlink-managed and ahead in places this
  source intentionally diverged from (portable paths, GLM-5.3, env_key
  secrets); when folding live changes in, adapt rather than copy verbatim.

## Commits

`[tag]: message`, lowercase imperative, one logical config area per commit,
body summarizing what drifted/changed. Tags in use: `chore`, `shell`, `bash`,
`nu`, `claude`, `agents`, `devops`, `direnv`, `conda`, `clash`.
