# Raw portable resources are copied after chezmoi, never interpreted as source
# filename attributes or executed as deployment hooks. Bash 3.2-compatible.
payload_safe_destination() {
    local candidate=$1
    while [ "$candidate" != "$DEPLOY_HOME" ]; do
        [ ! -L "$candidate" ] || fail "agent payload destination is a symlink: $candidate"
        candidate=${candidate%/*}
        [ -n "$candidate" ] || fail 'agent payload destination is outside the designated home'
    done
}

payload_validate_tree() {
    local source=$1 target=$2 entry
    [ ! -L "$source" ] || fail "agent payload source is a symlink: $source"
    payload_safe_destination "$target"
    if [ -d "$source" ]; then
        [ ! -e "$target" ] || [ -d "$target" ] || fail "agent payload directory conflicts with a file: $target"
        for entry in "$source"/* "$source"/.[!.]* "$source"/..?*; do
            [ -e "$entry" ] || [ -L "$entry" ] || continue
            payload_validate_tree "$entry" "$target/${entry##*/}"
        done
    elif [ -f "$source" ]; then
        [ ! -e "$target" ] || [ -f "$target" ] || fail "agent payload file conflicts with a directory: $target"
    else
        fail "unsupported agent payload resource: $source"
    fi
}

payload_source_path() {
    if [ "$1" = skills ] && [ -n "${PAYLOAD_SKILLS_DIR:-}" ]; then
        printf '%s' "$PAYLOAD_SKILLS_DIR"
    else
        printf '%s' "$DEPLOY_SOURCE/deployment/agent-payload/$1"
    fi
}

validate_agent_payload() {
    local payload="$DEPLOY_SOURCE/deployment/agent-payload" kind source target value origin
    [ ! -L "$payload/targets.tsv" ] || fail 'agent payload catalog is a symlink'
    while IFS=$'|\r' read -r kind source target; do
        case "$kind" in ''|\#*) continue ;; tree|file|block|retire) ;; *) fail "unknown agent payload kind: $kind" ;; esac
        for value in "$source" "$target"; do
            case "$value" in ''|/*|..|../*|*/../*|*/..) fail "agent payload catalog path must be relative: $value" ;; esac
        done
        if [ "$kind" = retire ]; then
            payload_safe_destination "$DEPLOY_HOME/$target"
            continue
        fi
        # Skill bytes come from the fetch stage, which runs after the early
        # pre-flight; defer their existence check to deployment time.
        if [ "$source" = skills ] && [ -z "${PAYLOAD_SKILLS_DIR:-}" ]; then
            continue
        fi
        origin=$(payload_source_path "$source")
        if [ "$kind" = tree ]; then
            [ -d "$origin" ] || fail "agent payload tree is missing: $source"
        else
            [ -f "$origin" ] || fail "agent payload file is missing: $source"
        fi
        payload_validate_tree "$origin" "$DEPLOY_HOME/$target"
    done < "$payload/targets.tsv"
}

payload_instruction() {
    local target=$1 source=$2 existing='' content prefix suffix remaining
    local start='<!-- DOTFILES_AGENT_START -->' end='<!-- DOTFILES_AGENT_END -->'
    if [ -f "$target" ]; then
        # The sentinel retains final newlines lost by command substitution.
        existing=$(cat "$target"; printf '.')
        existing=${existing%.}
    fi
    content=$(cat "$source"; printf '.')
    content=${content%.}
    case "$existing" in
        *"$start"*)
            prefix=${existing%%"$start"*}
            remaining=${existing#*"$start"}
            case "$remaining" in *"$start"*) fail "duplicate managed instruction marker: $target" ;; esac
            case "$remaining" in *"$end"*) ;; *) fail "unfinished managed instruction block: $target" ;; esac
            suffix=${remaining#*"$end"}
            case "$suffix" in *"$end"*) fail "duplicate managed instruction marker: $target" ;; esac
            ;;
        *)
            case "$existing" in *"$end"*) fail "unfinished managed instruction block: $target" ;; esac
            prefix=$existing
            if [ -n "$prefix" ]; then prefix="$prefix"$'\n'; fi
            suffix=$'\n'
            ;;
    esac
    mkdir -p "${target%/*}"
    printf '%s%s\n%s%s%s' "$prefix" "$start" "$content" "$end" "$suffix" > "$target"
    chmod 644 "$target"
}

# Retire an owned instruction block from a target that is no longer a managed
# destination, preserving device text and removing the file when nothing else
# remains. Idempotent: a target without the markers is left alone.
payload_retire_block() {
    local target=$1 existing prefix suffix remaining result
    local start='<!-- DOTFILES_AGENT_START -->' end='<!-- DOTFILES_AGENT_END -->'
    [ -f "$target" ] || return 0
    existing=$(cat "$target"; printf '.')
    existing=${existing%.}
    case "$existing" in
        *"$start"*)
            prefix=${existing%%"$start"*}
            remaining=${existing#*"$start"}
            case "$remaining" in *"$start"*) fail "duplicate managed instruction marker: $target" ;; esac
            case "$remaining" in *"$end"*) ;; *) fail "unfinished managed instruction block: $target" ;; esac
            suffix=${remaining#*"$end"}
            case "$suffix" in *"$end"*) fail "duplicate managed instruction marker: $target" ;; esac
            ;;
        *)
            case "$existing" in *"$end"*) fail "unfinished managed instruction block: $target" ;; esac
            return 0
            ;;
    esac
    # The deploy step inserted one newline between device text and the block.
    case "$prefix" in *$'\n') prefix=${prefix%$'\n'} ;; esac
    case "$suffix" in $'\n'*) suffix=${suffix#$'\n'} ;; esac
    result="${prefix}${suffix}"
    case "$result" in
        *[![:space:]]*) printf '%s' "$result" > "$target"; chmod 644 "$target" ;;
        *) rm -f "$target" ;;
    esac
}

deploy_agent_payload() {
    local payload="$DEPLOY_SOURCE/deployment/agent-payload" kind source target origin
    validate_agent_payload
    while IFS=$'|\r' read -r kind source target; do
        case "$kind" in
            ''|\#*) continue ;;
            tree)
                mkdir -p "$HOME/$target"
                origin=$(payload_source_path "$source")
                cp -Rp "$origin/." "$HOME/$target/"
                ;;
            file)
                mkdir -p "$HOME/${target%/*}"
                origin=$(payload_source_path "$source")
                cp -p "$origin" "$HOME/$target"
                ;;
            block) payload_instruction "$HOME/$target" "$payload/$source" ;;
            retire) payload_retire_block "$HOME/$target" ;;
        esac
    done < "$payload/targets.tsv"
}
