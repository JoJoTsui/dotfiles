#!/usr/bin/env bash
# Reconcile the approved global agent policy on a legacy symlink home.
# --fetch provisions reviewed resources once; --apply is strictly offline.
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
TARGET_HOME=${HOME:?}
LIVE_ROOT=$(dirname "$ROOT")
ACTION=check
while [ "$#" -gt 0 ]; do
    case "$1" in
        --fetch|--apply|--check) ACTION=${1#--}; shift ;;
        --home) TARGET_HOME=$2; shift 2 ;;
        --live-root) LIVE_ROOT=$2; shift 2 ;;
        -h|--help)
            printf '%s\n' 'usage: agent-integrations.sh [--fetch|--apply|--check] [--home DIR] [--live-root DIR]'
            exit 0 ;;
        *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done
fail() { printf 'agent-integrations: %s\n' "$*" >&2; exit 1; }
realpath_py() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
LIVE_ROOT=$(realpath_py "$LIVE_ROOT")
[ -d "$LIVE_ROOT" ] && [ -d "$TARGET_HOME" ] || fail 'home and live root must exist'
export HOME=$TARGET_HOME
DEPLOY_HOME=$HOME
DEPLOY_SOURCE=$ROOT
DEPLOY_PLATFORM=linux
export XDG_STATE_HOME=$HOME/.local/state
export TMPDIR=$HOME/.cache/tmp

# The public copier remains strict. This explicit legacy adapter permits only
# aliases whose canonical destination is inside the designated persistent tree.
source "$ROOT/deployment/payload.sh"
payload_safe_destination() {
    local resolved
    resolved=$(realpath_py "$1") || fail 'cannot resolve destination'
    case "$resolved" in "$LIVE_ROOT"/*) ;; *) fail "destination escapes live tree: $1" ;; esac
}
for path in "$HOME/.local" "$HOME/.cache" "$XDG_STATE_HOME" "$TMPDIR"; do
    payload_safe_destination "$path"
done
mkdir -p "$TMPDIR"
stage=$(mktemp -d "$TMPDIR/agent-integrations.XXXXXX")
chmod 700 "$stage"
trap 'rm -rf "$stage"' EXIT HUP INT TERM
cache=$HOME/.local/share/dotfiles/agent-integrations
payload_safe_destination "$cache"
chezmoi=${DOTFILES_CHEZMOI_BIN:-$HOME/.local/bin/chezmoi}
if [ "$ACTION" = fetch ] && [ ! -x "$chezmoi" ]; then
    source "$ROOT/deployment/managers.sh"
    DEPLOY_ARCH=$(uname -m)
    case "$DEPLOY_ARCH" in arm64) DEPLOY_ARCH=aarch64 ;; esac
    mkdir -p "$HOME/.local/bin"
    install_chezmoi
    chezmoi=$DEPLOY_CHEZMOI
fi
[ -x "$chezmoi" ] || fail 'Chezmoi is missing; run --fetch once before reboot'

source "$ROOT/deployment/skills.sh"
validate_skill_cache_tree "$cache"
row=$(awk -F '|' '$1 == "graphify" {print}' "$ROOT/deployment/skills.tsv")
IFS='|' read -r name kind source_url ref path selection <<< "$row"
[ "$name" = graphify ] && [ "$kind" = git ] || fail 'Graphify declaration is missing'
skill_pin_for "$name" "$kind" "$source_url" "$ROOT/deployment/skills.lock.tsv"
repo=$cache/git/$(skill_slug "$source_url")
payload_safe_destination "$repo"
if [ "$ACTION" != fetch ]; then
    git -C "$repo" cat-file -e "$SKILL_PIN^{commit}" 2>/dev/null ||
        fail 'pinned Graphify source is missing; run --fetch once before reboot'
fi
SKILL_REFRESH=0
mkdir -p "$cache/git" "$stage/skills"
skill_fetch_git "$name" "$source_url" "$ref" "$path" "$cache" "$stage/skills" "$stage/index" ||
    fail 'cannot stage the pinned official Graphify skill'
PAYLOAD_SKILLS_DIR=$stage/skills
if [ "$ACTION" = fetch ]; then
    printf 'agent-integrations: pinned Graphify source and Chezmoi prepared; run --apply after verification\n'
    exit 0
fi

validate_agent_payload
payload_quarantine_disabled --validate
# Build every desired file before changing a config, instruction, or skill.
plan=$stage/plan.tsv
: > "$plan"
plan_file() {
    local from=$1 relative=$2 mode=$3
    payload_safe_destination "$HOME/$relative"
    [ ! -e "$HOME/$relative" ] || [ -f "$HOME/$relative" ] || fail "file conflict: $relative"
    printf '%s|%s|%s\n' "$relative" "$from" "$mode" >> "$plan"
}
plan_tree() {
    local from=$1 relative=$2 entry
    for entry in "$from"/* "$from"/.[!.]* "$from"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        [ ! -L "$entry" ] || fail 'skill resource is a symlink'
        if [ -d "$entry" ]; then
            plan_tree "$entry" "$relative/${entry##*/}"
        else
            plan_file "$entry" "$relative/${entry##*/}" 0644
        fi
    done
}
i=0
while IFS='|' read -r operation resource relative; do
    case "$operation" in ''|\#*) continue ;; esac
    i=$((i + 1))
    file=$stage/instruction.$i
    case "$operation" in
        tree) [ "$resource" = skills ] || fail 'unsupported legacy payload tree'; plan_tree "$PAYLOAD_SKILLS_DIR" "$relative" ;;
        file) plan_file "$ROOT/deployment/agent-payload/$resource" "$relative" 0644 ;;
        block|retire)
            if [ -f "$HOME/$relative" ]; then cp -p "$HOME/$relative" "$file"; else : > "$file"; fi
            if [ "$operation" = block ]; then
                # Retire only the old standalone repository-owned graph block.
                # Managed blocks already include the current graph guidance.
                if ! grep -q '<!-- DOTFILES_AGENT_START -->' "$file"; then
                    payload_retire_block "$file" '<!-- CODEGRAPH_START -->' '<!-- CODEGRAPH_END -->'
                fi
                payload_instruction "$file" "$ROOT/deployment/agent-payload/$resource"
                plan_file "$file" "$relative" 0644
            else
                payload_retire_block "$file"
                # A retired device file without managed text is preserved.
                if [ -f "$file" ] && [ -s "$file" ]; then plan_file "$file" "$relative" 0644; fi
                if [ ! -e "$file" ] && [ -f "$HOME/$relative" ]; then plan_file '' "$relative" DELETE; fi
            fi
            ;;
        *) fail 'unsupported payload operation' ;;
    esac
done < "$ROOT/deployment/agent-payload/targets.tsv"
while IFS='|' read -r format relative; do
    case "$format" in ''|\#*) continue ;; esac
    [ -f "$HOME/$relative" ] || continue
    payload_safe_destination "$HOME/$relative"
    i=$((i + 1))
    file=$stage/config.$i
    policy=agent-integrations-only
    case "$relative" in
        .claude/settings*.json) policy=claude-settings ;;
        .codex/config.toml) policy=codex-update-only ;;
        .kimi-code/tui.toml) policy=kimi-tui ;;
    esac
    if ! DOTFILES_SETTINGS_FORMAT="$format" DOTFILES_SETTINGS_POLICY="$policy" DOTFILES_SETTINGS_OUTPUT=config \
        DOTFILES_SETTINGS_TARGET="$HOME/$relative" DOTFILES_SETTINGS_BASELINE="$stage/no-baseline" \
        DOTFILES_SETTINGS_SOURCE="$ROOT/deployment/client-settings/agent-policy.tmpl" \
        "$chezmoi" --source "$ROOT" --config /dev/null --config-format toml --override-data '{"platform":"linux"}' \
        execute-template --file "$ROOT/deployment/client-settings/merge.tmpl" > "$file" 2> "$stage/parser.log"; then
        fail "cannot parse/merge client config: $relative (no settings have been written)"
    fi
    plan_file "$file" "$relative" 0600
done < "$ROOT/deployment/agent-payload/client-configs.tsv"

drift=0
batch=''
while IFS='|' read -r relative from mode; do
    target=$HOME/$relative
    if [ "$mode" = DELETE ]; then
        [ -f "$target" ] || continue
    elif [ -f "$target" ] && cmp -s "$from" "$target"; then continue; fi
    drift=$((drift + 1))
    if [ "$ACTION" = check ]; then printf 'DRIFT %s\n' "$relative"; continue; fi
    if [ -z "$batch" ]; then
        state=$XDG_STATE_HOME/dotfiles/disabled-integrations
        payload_safe_destination "$state"
        mkdir -p "$state"
        batch=$(mktemp -d "$state/files.XXXXXX")
        chmod 700 "$batch"
    fi
    resolved=$(realpath_py "$target")
    payload_safe_destination "$target"
    if [ -f "$target" ]; then
        mkdir -p "$batch/$(dirname "$relative")"
        cp -p "$target" "$batch/$relative"
        chmod 600 "$batch/$relative"
        original_mode=$(stat -c '%a' "$resolved")
        printf '%s|%s|%s\n' "$target" "$batch/$relative" "$original_mode" >> "$batch/restore.tsv"
    else
        printf '%s|NEW|-\n' "$target" >> "$batch/restore.tsv"
    fi
    if [ "$mode" = DELETE ]; then
        rm -f "$resolved"
        continue
    fi
    mkdir -p "$(dirname "$resolved")"
    temporary=$(mktemp "$(dirname "$resolved")/.agent-policy.XXXXXX")
    cp "$from" "$temporary"
    chmod "$mode" "$temporary"
    mv -f "$temporary" "$resolved"
done < "$plan"
if [ "$ACTION" = apply ]; then
    payload_quarantine_disabled
else
    while IFS= read -r relative; do
        case "$relative" in ''|\#*) continue ;; esac
        [ -e "$HOME/$relative" ] || [ -L "$HOME/$relative" ] || continue
        payload_safe_destination "$HOME/$relative"
        while IFS='|' read -r name source_url; do
            case "$name" in ''|\#*) continue ;; esac
            if [ -e "$HOME/$relative/$name" ] || [ -L "$HOME/$relative/$name" ]; then
                printf 'DISABLED_SKILL_PRESENT %s/%s\n' "$relative" "$name"
                drift=$((drift + 1))
            fi
        done < "$ROOT/deployment/disabled-skills.tsv"
    done < "$ROOT/deployment/agent-payload/discovery-roots.tsv"
fi
if [ "$ACTION" = check ] && [ "$drift" -ne 0 ]; then exit 1; fi
printf 'agent-integrations: %s passed; Graphify available, disabled integrations excluded\n' "$ACTION"
