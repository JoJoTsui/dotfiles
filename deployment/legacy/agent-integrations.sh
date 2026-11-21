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

# The managed-skill inventory records the skill directories the deployment
# owns. Its path is resolved before it is read: a leaf symlink is either the
# accepted in-live-root alias, whose canonical path is kept, or a refusal.
# Nothing outside the live tree is ever read as an ownership record.
INVENTORY_STATE=''
INVENTORY_RELATIVE=''
INVENTORY_JOURNALED=''
policy_inventory_state() {
    local raw canonical
    raw=$(payload_managed_skills_state)
    payload_safe_destination "$raw"
    canonical=$raw
    if [ -L "$raw" ]; then
        canonical=$(realpath_py "$raw") || fail 'cannot resolve the managed skill inventory'
        case "$canonical" in "$LIVE_ROOT"/*) ;; *) fail "managed skill inventory escapes the live tree: $raw" ;; esac
    fi
    [ ! -e "$canonical" ] || [ -f "$canonical" ] ||
        fail "managed skill inventory is not a regular file: $raw"
    INVENTORY_STATE=$canonical
    case "$raw" in
        "$HOME"/*) INVENTORY_RELATIVE=${raw#"$HOME"/} ;;
        *) INVENTORY_RELATIVE=${raw##*/} ;;
    esac
}

# Whether the inventory records a managed skill in a root. The read uses the
# validated path, so a symlinked inventory outside the live tree can never
# answer for the deployment.
policy_previous_managed_skill() {
    local name=$1 root=$2
    policy_inventory_state
    [ -f "$INVENTORY_STATE" ] || return 1
    PAYLOAD_MANAGED_NAME=$name PAYLOAD_MANAGED_ROOT=$root awk -F '|' '
        BEGIN { name = ENVIRON["PAYLOAD_MANAGED_NAME"]; root = ENVIRON["PAYLOAD_MANAGED_ROOT"] }
        !/^#/ && NF >= 2 && $1 == name && $2 == root { found = 1 }
        END { exit !found }
    ' "$INVENTORY_STATE"
}

# The inventory is recoverable state, so it is backed up and journaled once
# before its first change in this apply. A rollback that withdraws a new
# skill also withdraws the row that would otherwise let a later apply
# overwrite a new device directory.
policy_journal_inventory() {
    local state=$1 mode
    [ -z "$INVENTORY_JOURNALED" ] || return 0
    INVENTORY_JOURNALED=1
    policy_batch
    if [ -f "$state" ]; then
        mkdir -p "$batch/$(dirname "$INVENTORY_RELATIVE")"
        cp -p "$state" "$batch/$INVENTORY_RELATIVE"
        chmod 600 "$batch/$INVENTORY_RELATIVE"
        mode=$(stat -c '%a' "$state")
        printf '%s|%s|%s\n' "$state" "$batch/$INVENTORY_RELATIVE" "$mode" >> "$batch/restore.tsv"
    else
        printf '%s|NEW|-\n' "$state" >> "$batch/restore.tsv"
    fi
}

# The managed skill inventory records the skill directories the deployment
# owns. The adapter writes its own rows and keeps every row of another owner.
policy_record_skill() {
    local name=$1 root=$2 state previous inventory staged
    [ "$ACTION" = apply ] || return 0
    policy_inventory_state
    state=$INVENTORY_STATE
    mkdir -p "$(dirname "$state")"
    previous=$(mktemp "$TMPDIR/policy-skills.XXXXXX") || fail 'cannot record the managed skill'
    inventory=$(mktemp "$TMPDIR/policy-skills.XXXXXX") || fail 'cannot record the managed skill'
    if [ -f "$state" ]; then grep -v '^#' "$state" > "$previous" || true; else : > "$previous"; fi
    {
        printf '# name|root\n'
        { grep -v -F -x "$name|$root" "$previous" || true; printf '%s|%s\n' "$name" "$root"; } | sort -u
    } > "$inventory"
    # An unchanged inventory is left alone, so a repeated apply neither
    # rewrites it nor journals it again.
    if [ -f "$state" ] && cmp -s "$inventory" "$state"; then
        rm -f "$previous" "$inventory"
        return 0
    fi
    policy_journal_inventory "$state"
    staged=$(mktemp "$state.XXXXXX") || fail 'cannot record the managed skill'
    cat "$inventory" > "$staged"
    mv -f "$staged" "$state"
    rm -f "$previous" "$inventory"
}
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
# The managed-skill inventory decides which skill directories the deployment
# owns, so its path is validated before the plan is built and before any
# ownership read: an inventory outside the live tree never authorizes an
# overwrite.
policy_inventory_state
# Build every desired file before changing a config, instruction, or skill.
plan=$stage/plan.tsv
: > "$plan"
plan_file() {
    local from=$1 relative=$2 mode=$3
    payload_safe_destination "$HOME/$relative"
    [ ! -e "$HOME/$relative" ] || [ -f "$HOME/$relative" ] || fail "file conflict: $relative"
    printf '%s|%s|%s\n' "$relative" "$from" "$mode" >> "$plan"
}
# A selected skill is copied as a unit. The public copier's ownership policy
# decides what happens at the destination: a device entry keeps its own bytes,
# a directory that already holds these bytes is adopted, and a directory the
# inventory records belongs to the deployment.
plan_skill_tree() {
    local from=$1 relative=$2 entry name selection
    payload_safe_destination "$HOME/$relative"
    for entry in "$from"/* "$from"/.[!.]* "$from"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        [ -d "$entry" ] || fail "staged skill is not a directory: ${entry##*/}"
        [ ! -L "$entry" ] || fail 'skill resource is a symlink'
        name=${entry##*/}
        payload_skill_disabled "$name" && continue
        selection=$(skill_catalog_selection "$name")
        [ -n "$selection" ] || continue
        skill_selected "$name" "$selection" || continue
        printf '%s|%s|%s\n' "$relative/$name" "$entry" tree >> "$plan"
    done
}
i=0
while IFS='|' read -r operation resource relative; do
    case "$operation" in ''|\#*) continue ;; esac
    i=$((i + 1))
    file=$stage/instruction.$i
    case "$operation" in
        tree) [ "$resource" = skills ] || fail 'unsupported legacy payload tree'; plan_skill_tree "$PAYLOAD_SKILLS_DIR" "$relative" ;;
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

# The recovery batch holds the bytes the apply replaces, so every change stays
# reversible.
policy_batch() {
    [ -n "$batch" ] && return 0
    local batch_state=$XDG_STATE_HOME/dotfiles/disabled-integrations
    payload_safe_destination "$batch_state"
    mkdir -p "$batch_state"
    batch=$(mktemp -d "$batch_state/files.XXXXXX")
    chmod 700 "$batch"
}

# Back up one replaced file and record its original mode.
policy_backup_file() {
    local target=$1 relative=$2 resolved=$3 original_mode
    if [ -f "$target" ]; then
        mkdir -p "$batch/$(dirname "$relative")"
        cp -p "$target" "$batch/$relative"
        chmod 600 "$batch/$relative"
        original_mode=$(stat -c '%a' "$resolved")
        printf '%s|%s|%s\n' "$target" "$batch/$relative" "$original_mode" >> "$batch/restore.tsv"
    else
        printf '%s|NEW|-\n' "$target" >> "$batch/restore.tsv"
    fi
}

# Report a device entry the deployment preserved. A shared alias names one
# physical entry, so the report happens once per physical path.
policy_report_preserved() {
    local name=$1 root=$2 reason=$3 target=$4 resolved
    resolved=$(realpath_py "$target")
    if [ -f "$stage/reported" ] && grep -q -F -x "$resolved" "$stage/reported"; then
        return 0
    fi
    printf '%s\n' "$resolved" >> "$stage/reported"
    printf 'dotfiles: preserved skill %s in %s; %s\n' "$name" "$root" "$reason" >&2
}

# Stage the candidate beside the canonical destination and publish it there.
# The staged tree is complete before the owned directory is touched, so a
# failed copy leaves the bytes the deployment owns in place. The old tree is
# moved aside for the publish and restored when the publish fails.
policy_stage_skill() {
    local from=$1 relative=$2 resolved=$3 name=$4 root=$5 parent candidate replaced mode original_mode
    parent=$(dirname "$resolved")
    mkdir -p "$parent"
    candidate=$(mktemp -d "$parent/.agent-policy-candidate.XXXXXX") ||
        fail "cannot stage the skill $name in $root"
    if ! cp -Rp "$from/." "$candidate/"; then
        rm -rf -- "$candidate"
        fail "cannot copy the skill $name into $root"
    fi
    mode=$(stat -c '%a' "$from")
    chmod "$mode" "$candidate"
    replaced=''
    if [ -d "$resolved" ]; then
        # The deployment owns the directory, so the staged copy replaces it
        # and the bytes it no longer carries are gone. The replaced bytes
        # reach the recovery batch before the change.
        mkdir -p "$batch/$(dirname "$relative")"
        cp -Rp "$resolved" "$batch/$relative"
        original_mode=$(stat -c '%a' "$resolved")
        printf '%s|%s|%s\n' "$HOME/$relative" "$batch/$relative" "$original_mode" >> "$batch/restore.tsv"
        replaced=$(mktemp -d "$parent/.agent-policy-old.XXXXXX") ||
            fail "cannot replace the managed skill $name in $root"
        rmdir "$replaced"
        if ! mv -- "$resolved" "$replaced"; then
            rm -rf -- "$candidate"
            fail "cannot replace the managed skill $name in $root"
        fi
    else
        printf '%s|NEW|-\n' "$HOME/$relative" >> "$batch/restore.tsv"
    fi
    if ! mv -- "$candidate" "$resolved"; then
        if [ -n "$replaced" ]; then
            mv -- "$replaced" "$resolved" || fail "cannot restore the managed skill $name in $root"
        fi
        rm -rf -- "$candidate"
        fail "cannot copy the skill $name into $root"
    fi
    [ -z "$replaced" ] || rm -rf -- "$replaced"
}

# Copy one selected skill into a managed root as a unit. A device entry keeps
# its own bytes, a directory that already holds these bytes is adopted
# without a rewrite, and a directory the inventory records belongs to the
# deployment, so the staged copy replaces it.
apply_skill_tree() {
    local relative=$1 from=$2 target root name resolved original_mode
    target=$HOME/$relative
    root=${relative%/*}
    name=${relative##*/}
    if [ -L "$target" ]; then
        policy_report_preserved "$name" "$root" 'a device symlink has that name' "$target"
        return 0
    fi
    if [ -e "$target" ] && [ ! -d "$target" ]; then
        policy_report_preserved "$name" "$root" 'a device file has that name' "$target"
        return 0
    fi
    if [ -d "$target" ] && payload_tree_identical "$from" "$target"; then
        # The device already holds these bytes, so the deployment adopts the
        # directory and never rewrites it.
        policy_record_skill "$name" "$root"
        return 0
    fi
    if [ -d "$target" ] && ! policy_previous_managed_skill "$name" "$root"; then
        policy_report_preserved "$name" "$root" 'a device directory has that name and its bytes differ' "$target"
        return 0
    fi
    drift=$((drift + 1))
    if [ "$ACTION" = check ]; then printf 'DRIFT %s\n' "$relative"; return 0; fi
    policy_batch
    resolved=$(realpath_py "$target")
    payload_safe_destination "$target"
    policy_stage_skill "$from" "$relative" "$resolved" "$name" "$root"
    policy_record_skill "$name" "$root"
}

drift=0
batch=''
while IFS='|' read -r relative from mode; do
    target=$HOME/$relative
    if [ "$mode" = tree ]; then
        apply_skill_tree "$relative" "$from"
        continue
    fi
    if [ "$mode" = DELETE ]; then
        [ -f "$target" ] || continue
    elif [ -f "$target" ] && cmp -s "$from" "$target"; then continue; fi
    drift=$((drift + 1))
    if [ "$ACTION" = check ]; then printf 'DRIFT %s\n' "$relative"; continue; fi
    policy_batch
    resolved=$(realpath_py "$target")
    payload_safe_destination "$target"
    policy_backup_file "$target" "$relative" "$resolved"
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
