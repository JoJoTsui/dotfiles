#!/usr/bin/env bash
# Supervisor-side live verification after the real-home apply.
# Prints counts, versions, and states. Never prints a credential.
set -uo pipefail

printf '=== managed versions ===\n'
for c in codex python3 node bun nu chezmoi pixi git rg; do
    if command -v "$c" >/dev/null 2>&1; then
        printf '%-12s %s\n' "$c" "$("$c" --version 2>&1 | head -1)"
    else
        printf '%-12s absent\n' "$c"
    fi
done

printf '\n=== selected agent commands ===\n'
# The agent catalog names the agent "minimax" and the command it exposes
# "mcode" (deployment/agents/providers.tsv). Asking for "minimax" would
# report a command the deployment never promises.
for c in kimi pi opencode claude codex mcode qoder; do
    if command -v "$c" >/dev/null 2>&1; then
        printf '%-10s present\n' "$c"
    else
        printf '%-10s absent\n' "$c"
    fi
done

printf '\n=== managed command ===\n'
for p in "$HOME/.local/bin/dotfiles-codex-resume" "$HOME/.local/bin/dotfiles-magpie" \
         "$HOME/.local/bin/dotfiles-agents" "$HOME/.local/bin/dotfiles-agent-health"; do
    if [ -f "$p" ]; then
        printf '%s %s\n' "$(stat -f '%Lp' "$p")" "$p"
    else
        printf 'absent %s\n' "$p"
    fi
done

printf '\n=== codex profile (magpie) ===\n'
for p in "$HOME/.codex/magpie.config.toml" "$HOME/.codex/magpie-models.json"; do
    if [ -f "$p" ]; then
        printf '%s %s bytes\n' "$(stat -f '%Lp' "$p")" "$(stat -f '%z' "$p")"
    else
        printf 'absent %s\n' "$p"
    fi
done

printf '\n=== plain codex configuration is untouched by the deployment ===\n'
for p in "$HOME/.codex/config.toml" "$HOME/.codex/auth.json"; do
    if [ -f "$p" ]; then
        printf '%s %s %s\n' "$(stat -f '%Lp' "$p")" "$(stat -f '%z' "$p")" "$p"
    else
        printf 'absent %s\n' "$p"
    fi
done

printf '\n=== magpie gateway ===\n'
magpie status 2>&1 | grep -v '^plugin: host starts' | head -3

printf '\n=== deployment status ===\n'
if [ -x "$HOME/.local/bin/dotfiles-magpie" ]; then
    "$HOME/.local/bin/dotfiles-magpie" status 2>&1 | head -40
fi
