# shellcheck shell=bash
# Prepare the canonical live tree for a targeted agent update on a legacy
# symlink home. The public copy-mode boundary still refuses these homes; this
# helper runs only for --agents-only/--agent-update without an explicit --home.

LEGACY_AGENT_LINK_RECOVERY=''

legacy_agent_unique_backup() {
    local target=$1 stamp suffix candidate
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    candidate="$target.bak.$stamp"
    suffix=1
    while [ -e "$candidate" ] || [ -L "$candidate" ]; do
        candidate="$target.bak.$stamp-$suffix"
        suffix=$((suffix + 1))
    done
    printf '%s' "$candidate"
}

legacy_agent_link_journal() {
    local state batch
    [ -z "$LEGACY_AGENT_LINK_RECOVERY" ] || return 0
    state="$DEPLOY_HOME/.local/state/dotfiles/legacy-agent-links"
    [ ! -L "$DEPLOY_HOME/.local/state/dotfiles" ] ||
        fail 'the legacy agent link recovery parent is a symlink'
    [ ! -L "$state" ] || fail 'the legacy agent link recovery directory is a symlink'
    mkdir -p "$state" || fail 'cannot create the legacy agent link recovery directory'
    batch=$(mktemp -d "$state/$(date -u +%Y%m%dT%H%M%SZ).XXXXXX") ||
        fail 'cannot create the legacy agent link recovery batch'
    chmod 700 "$batch" || fail 'cannot protect the legacy agent link recovery batch'
    printf '# path|backup\n' > "$batch/restore.tsv" ||
        fail 'cannot create the legacy agent link recovery journal'
    chmod 600 "$batch/restore.tsv" || fail 'cannot protect the legacy agent link recovery journal'
    LEGACY_AGENT_LINK_RECOVERY=$batch
    printf 'dotfiles: legacy agent link recovery batch: %s\n' "$batch" >&2
}

legacy_agent_prepare_skill_roots() {
    local relative path parent physical backup
    local -a roots=(.agents/skills .claude/skills .minimax/skills)
    for relative in "${roots[@]}"; do
        path=$DEPLOY_HOME/$relative
        parent=${path%/*}
        physical=$(CDPATH='' cd -P -- "$parent" 2>/dev/null && pwd -P) ||
            fail "cannot resolve legacy skill-root parent: $relative"
        [ "$physical" = "$parent" ] ||
            fail "legacy skill-root parent is a symlink: $relative"
        if [ -d "$path" ] && [ ! -L "$path" ]; then
            continue
        fi
        legacy_agent_link_journal
        backup=NEW
        if [ -e "$path" ] || [ -L "$path" ]; then
            backup=$(legacy_agent_unique_backup "$path")
            mv "$path" "$backup" || fail "cannot back up legacy skill root: $relative"
        fi
        if ! mkdir -p "$path"; then
            [ "$backup" = NEW ] || mv "$backup" "$path"
            fail "cannot prepare legacy skill root: $relative"
        fi
        printf '%s|%s\n' "$relative" "$backup" >> "$LEGACY_AGENT_LINK_RECOVERY/restore.tsv" ||
            fail "cannot record legacy skill root: $relative"
        printf 'dotfiles: prepared legacy agent directory %s\n' "$relative" >&2
    done
}

adopt_legacy_agent_home() {
    "$DEPLOY_AGENTS_ONLY" || return 0
    "$DEPLOY_HOME_SET" && return 0
    [ ! -L "$DEPLOY_HOME" ] || return 0

    local original=$DEPLOY_HOME relative path target expected candidate backup
    local anchor count best='' best_count=0
    local -a core=(.local .config .cache .pixi .bun)
    local -a roots=(.local .config .cache .pixi .bun .codex .claude .kimi-code .pi
        .qoder .minimax .minimax-code .minimax-code-install-logs .cargo .rustup
        .agents .opencode .codegraph .herdr .dsh .dsh-tui)

    # Pick the live tree shared by the largest number of core links. Three
    # matching roots distinguish the legacy layout from an ordinary device
    # that happens to symlink one cache or state directory elsewhere.
    for anchor in "${core[@]}"; do
        path=$original/$anchor
        [ -L "$path" ] || continue
        target=$(CDPATH='' cd -P -- "$path" 2>/dev/null && pwd -P) || continue
        [ "${target##*/}" = "$anchor" ] || continue
        candidate=${target%/*}
        [ -n "$candidate" ] && [ "$candidate" != / ] || continue
        count=0
        for relative in "${core[@]}"; do
            path=$original/$relative
            [ -L "$path" ] || continue
            target=$(CDPATH='' cd -P -- "$path" 2>/dev/null && pwd -P) || continue
            [ "$target" = "$candidate/$relative" ] && count=$((count + 1))
        done
        if [ "$count" -gt "$best_count" ]; then
            best=$candidate
            best_count=$count
        fi
    done
    [ "$best_count" -ge 3 ] || return 0
    [ "$best" != "$DEPLOY_SOURCE" ] || fail 'legacy agent live tree cannot equal the source'

    DEPLOY_HOME=$best
    # Consumed by deployment/agents.sh after this helper is sourced.
    # shellcheck disable=SC2034
    DEPLOY_LEGACY_AGENT_HOME=true
    printf 'dotfiles: using legacy agent home %s for symlinked %s\n' "$DEPLOY_HOME" "$original" >&2
    "$DEPLOY_PLAN" && return 0

    # Prepare every managed top-level root. Missing roots are created in the
    # live tree and linked into the account home. A conflicting file, directory,
    # or symlink is moved to a timestamped backup before the correct link is
    # published, so the update never needs a manual removal step.
    for relative in "${roots[@]}"; do
        expected=$DEPLOY_HOME/$relative
        path=$original/$relative
        [ ! -L "$expected" ] || fail "legacy live state root is a symlink: $expected"
        [ ! -e "$expected" ] || [ -d "$expected" ] ||
            fail "legacy live state root is not a directory: $expected"
        mkdir -p "$expected" || fail "cannot prepare legacy live state root: $relative"
        if [ -L "$path" ]; then
            target=$(CDPATH='' cd -P -- "$path" 2>/dev/null && pwd -P) || target=''
            [ "$target" != "$expected" ] || continue
        fi
        legacy_agent_link_journal
        backup=NEW
        if [ -e "$path" ] || [ -L "$path" ]; then
            backup=$(legacy_agent_unique_backup "$path")
            mv "$path" "$backup" || fail "cannot back up legacy agent state root: $relative"
        fi
        if ! ln -s "$expected" "$path"; then
            [ "$backup" = NEW ] || mv "$backup" "$path"
            fail "cannot link legacy agent state root: $relative"
        fi
        printf '%s|%s\n' "$relative" "$backup" >> "$LEGACY_AGENT_LINK_RECOVERY/restore.tsv" ||
            fail "cannot record legacy agent state root: $relative"
        printf 'dotfiles: prepared legacy agent link %s -> %s\n' "$relative" "$expected" >&2
    done
    # The public payload copier requires regular skill roots. Legacy aliases
    # such as .minimax/skills -> ../.agents/skills are backed up and replaced
    # with the copy root the repository actually manages.
    legacy_agent_prepare_skill_roots
}
