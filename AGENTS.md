# AGENTS.md

Read `README.md` for orientation (layout, host classes, coding-agent table).
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
  `README.md`, `AGENTS.md`, `bootstrap.sh`, `docs`, `system`, `clash`,
  `.vscode-server` (non-t9k classes).

## Template data

Defined in `.chezmoi.toml.tmpl`, sourced from environment variables at init:
`class` (`DOTFILES_CLASS`, else detected: t9k/linux/win), `proxyUrl`
(`HTTP_PROXY_URL`), `glmBaseUrl` (`GLM_BASE_URL`), `glmToken`
(`GLM_API_TOKEN`), `kimiApiKey` (`KIMI_API_KEY`). Defaults keep unattended
init non-interactive; token defaults are the literal `REPLACE_ME` — a rendered
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
2. `H=/tmp/dotfiles-sim; rm -rf "$H"; mkdir -p "$H"; HOME="$H" chezmoi init --apply "$PWD"`
   (use `DOTFILES_CLASS=linux` too, to exercise the ignore branch).
3. Check the rendered target (`grep` the templated value, confirm file is a
   regular file not a symlink), then delete `$H`.
4. For nushell edits, also run
   `nu --config $H/.config/nushell/config.nu --env-config $H/.config/nushell/env.nu -c 'print "ok"'`
   with `JOEY/JSHELL/...` unset (`env -u`) — config must bootstrap standalone.

Done when: the simulated apply succeeds for both classes, the nushell check
passes (if touched), `git status` shows no secret files, and the commit body
explains every changed pair.

## Invariants

- **`.env_core` is POSIX sh and idempotent** (`: "${VAR:=...}"` guards);
  bash sources it before the interactive check so non-interactive shells get PATH.
- **The exec-nu guard** in `dot_profile`/`dot_bashrc` stays POSIX-safe and
  fires only for a real interactive TTY outside a Claude Code session
  (rationale: `docs/CLAUDE_SETUP_T9K.md`).
- **`dot_config/nushell/env.nu` keeps guarded `$env.JOEY? | default` bootstrap
  + `path add … uniq`** — standalone `nu` (spawned without bash) must still
  resolve `JSHELL`/`JOEY` for `micromamba.nu`.
- **JSONC files**: `dot_config/opencode/opencode.jsonc`,
  `dot_vscode-server/…/settings.json.tmpl`, `docs/vscode-win-settings.jsonc`
  — validate as JSON-with-comments, not shell (historical `.sh` naming retired).
- Not applied to `$HOME` (ignored): `system/`, `clash/`, `docs/` — `system/`
  reaches `/etc/bash.bashrc` only via `bootstrap.sh`.

## Known rough edges

- `config.nu` sources `~/.config/nushell/nu_scripts/...` — if bootstrap's clone
  failed (github.com unreachable; gh-proxy fallback also listed in
  `bootstrap.sh`), nu startup errors until it exists.
- `chezmoi init --source <dir>` does not persist sourceDir; `bootstrap.sh`
  uses `chezmoi init --apply <clone>` (verified), which clones the local repo.
- Legacy live tree (JSHELL) is still symlink-managed and ahead in places this
  source intentionally diverged from (portable paths, GLM-5.3, env_key
  secrets); when folding live changes in, adapt rather than copy verbatim.

## Commits

`[tag]: message`, lowercase imperative, one logical config area per commit,
body summarizing what drifted/changed. Tags in use: `chore`, `shell`, `bash`,
`nu`, `claude`, `agents`, `devops`, `direnv`, `conda`, `clash`.
