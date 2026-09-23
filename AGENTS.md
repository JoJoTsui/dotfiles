# AGENTS.md

Read `README.md` first for orientation. It explains the environment; this file
covers how to work in the repo without breaking the live environment.

## Model

The **live tree** `/t9k/mnt/joey/SHELL` (JSHELL) is the source of truth. This
repo is a curated mirror of a subset of it, pushed to GitHub. Every task here is
fundamentally either *syncing drift* (live → repo) or *proposing a change*
(repo → live, applied by the human). Verify against the live tree before
trusting any file here; the mirror is allowed to lag.

## Mirrored files (repo ↔ live)

| Repo | Live |
| --- | --- |
| `.env_core`, `.gitconfig`, `.profile` | `JSHELL/<same name>` |
| `bash/.bashrc` | `JSHELL/.bashrc` |
| `bash/bash.bashrc` | `JSHELL/bash.bashrc` |
| `conda/.condarc` | `JSHELL/.condarc` |
| `direnv/direnvrc` | `JSHELL/.config/direnv/direnvrc` |
| `starship/starship.toml` | `JSHELL/.config/starship.toml` |
| `nushell/{env,config}.nu` | `JSHELL/.config/nushell/{env,config}.nu` |
| `nushell/{micromamba,direnv,proxy}.nu` | `JSHELL/CLIs/nushell/<same name>` |
| `claude/glm-settings.json`, `claude/mcp.json` | `JSHELL/.claude/settings.json`, `~/.claude.json` (shape has diverged — diff first) |
| `vscode/t9k_settings.sh` | `JSHELL/.vscode-server/data/Machine/settings.json` (partial) |
| `clash/Merge.yaml` | superseded: `JSHELL/clash/` is now its own git repo — leave out of syncs |

## Syncing drift (live → repo)

1. Diff every mirrored pair with the table above (`diff -u repo live`).
2. For each drifted pair, copy the live version into the repo path. Keep repo
   paths as listed even when live paths differ (the split layout is deliberate).
3. Redact every credential in the copied text — `ANTHROPIC_AUTH_TOKEN`,
   `CONTEXT7_TOKEN`, `sk-…`, `glmfix_…`, and any bearer header — to an obvious
   placeholder such as `REPLACE_ME`. `*keys.json` files stay untracked.
4. Summarize every drifted pair in the commit body; one commit per logical
   config area works better than one giant sync commit.

Done when: every mirrored pair is either identical or its difference is
explained in a commit message, and `git status` shows no `*keys.json` staged.

## Invariants

- **`.env_core` is POSIX sh and idempotent** — bash and (indirectly) nushell both
  consume it; every assignment is guarded (`: "${VAR:=default}"`) so re-sourcing
  is safe.
- **The interactive-TTY guard stays.** `.profile` and `.bashrc` may only
  `exec nu` when attached to a real interactive terminal outside a Claude Code
  session; background agent shells break otherwise (see
  `claude/CLAUDE_SETUP_T9K.md`).
- **`vscode/*.sh` are JSONC**, not shell, despite the extension. Validate as
  JSON with comments.
- **`nushell/nu_history.txt` is a history dump**, not config — refresh it only
  deliberately.
- Vendored or foreign content, left untouched: `JSHELL/CLIs/nushell/nu_scripts`
  (upstream git checkout) and everything in `gizmo/` / `bio_gizmo/` (tool
  binaries on PATH).

## Known rough edges

- `link_dotfiles.new.sh` links the **live tree** into `$HOME`; its paths assume
  JSHELL, not this repo's layout. `--dry-run` is parsed but ignored, and the
  `/etc/bash.bashrc` swap runs its `ln` unconditionally (`&&`…`;`).
- `.profile` uses `[[ ]]`, a bashism, in a file POSIX sh may read.
- `claude/` snapshots lag the live Claude config badly (live is GLM-5.2 via a
  gateway with plugins/hooks/statusline; the snapshot is GLM-4.7 + MCP servers).
  Diff `JSHELL/.claude/settings*.json` before editing anything under `claude/`.

## Commits

`[tag]: message`, lowercase, imperative. Tags in use: `bash`, `nu`, `shell`,
`claude`, `conda`, `direnv`, `clash`, `devops`, `cli`, `chore`.
