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
    local target=$1 source=$2 existing='' content prefix suffix remaining overlay
    local start='<!-- DOTFILES_AGENT_START -->' end='<!-- DOTFILES_AGENT_END -->'
    if [ -f "$target" ]; then
        # The sentinel retains final newlines lost by command substitution.
        existing=$(cat "$target"; printf '.')
        existing=${existing%.}
    fi
    content=$(cat "$source"; printf '.')
    content=${content%.}
    overlay="$DEPLOY_SOURCE/deployment/agent-payload/overlays/$DEPLOY_PLATFORM.md"
    case "$DEPLOY_PLATFORM" in
        linux|wsl|macos) [ -f "$overlay" ] || fail "missing platform overlay: $overlay" ;;
    esac
    if [ -f "$overlay" ]; then
        content="$content"$'\n\n'"$(cat "$overlay"; printf '.')"
        content=${content%.}
    fi
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
    local start=${2:-'<!-- DOTFILES_AGENT_START -->'} end=${3:-'<!-- DOTFILES_AGENT_END -->'}
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
    # Only our managed block adds separators. A legacy marker block may sit
    # inside personal text; removing it must preserve surrounding whitespace.
    if [ "$#" -eq 1 ]; then
        case "$prefix" in *$'\n') prefix=${prefix%$'\n'} ;; esac
        case "$suffix" in $'\n'*) suffix=${suffix#$'\n'} ;; esac
    fi
    result="${prefix}${suffix}"
    case "$result" in
        *[![:space:]]*) printf '%s' "$result" > "$target"; chmod 644 "$target" ;;
        *) rm -f "$target" ;;
    esac
}

payload_skill_disabled() {
    local catalog="$DEPLOY_SOURCE/deployment/disabled-skills.tsv"
    [ -f "$catalog" ] || return 1
    awk -F '|' -v name="$1" '$1 == name { found=1 } END { exit !found }' "$catalog"
}

payload_copy_skills() {
    local origin=$1 target=$2 entry
    mkdir -p "$target"
    for entry in "$origin"/* "$origin"/.[!.]* "$origin"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        payload_skill_disabled "${entry##*/}" && continue
        cp -Rp "$entry" "$target/"
    done
}

# Additive payload copies cannot retire an installed skill. Move disabled
# entries out of every discovery root; retain an exact, reversible copy.
payload_quarantine_disabled() {
    local catalog="$DEPLOY_SOURCE/deployment/disabled-skills.tsv"
    local roots="$DEPLOY_SOURCE/deployment/agent-payload/discovery-roots.tsv"
    local root name source target batch='' state="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/disabled-integrations"
    [ -f "$catalog" ] && [ -f "$roots" ] || return 0
    while IFS= read -r root; do
        case "$root" in ''|\#*) continue ;; /*|..|../*|*/../*|*/..) fail 'unsafe skill discovery root' ;; esac
        [ -e "$HOME/$root" ] || [ -L "$HOME/$root" ] || continue
        payload_safe_destination "$HOME/$root"
    done < "$roots"
    payload_safe_destination "$state"
    while IFS='|' read -r name source; do
        case "$name" in ''|\#*) continue ;; */*|*..*) fail 'unsafe disabled skill name' ;; esac
    done < "$catalog"
    [ "${1:-}" != --validate ] || return 0
    while IFS= read -r root; do
        case "$root" in ''|\#*) continue ;; esac
        [ -e "$HOME/$root" ] || [ -L "$HOME/$root" ] || continue
        while IFS='|' read -r name source; do
            case "$name" in ''|\#*) continue ;; */*|*..*) fail 'unsafe disabled skill name' ;; esac
            target="$HOME/$root/$name"
            [ -e "$target" ] || [ -L "$target" ] || continue
            if [ -z "$batch" ]; then
                mkdir -p "$state"
                batch=$(mktemp -d "$state/skills.XXXXXX") || fail 'cannot create disabled skill backup'
            fi
            mkdir -p "$batch/$root"
            mv "$target" "$batch/$root/$name" || fail "cannot quarantine disabled skill: $name"
            printf '%s|%s\n' "$root/$name" "$batch/$root/$name" >> "$batch/restore.tsv"
        done < "$catalog"
    done < "$roots"
}

deploy_agent_payload() {
    local payload="$DEPLOY_SOURCE/deployment/agent-payload" kind source target origin
    validate_agent_payload
    payload_quarantine_disabled
    while IFS=$'|\r' read -r kind source target; do
        case "$kind" in
            ''|\#*) continue ;;
            tree)
                mkdir -p "$HOME/$target"
                origin=$(payload_source_path "$source")
                if [ "$source" = skills ]; then
                    payload_copy_skills "$origin" "$HOME/$target"
                else
                    cp -Rp "$origin/." "$HOME/$target/"
                fi
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
    report_skill_collisions
}

# The skill names a client discovers in one root. A skill directory holds a
# SKILL.md; the declared name wins and the directory name is the fallback.
payload_skill_names() {
    local root=$1 file name
    [ -d "$root" ] || return 0
    find "$root" -maxdepth 3 -name SKILL.md -type f 2>/dev/null | while IFS= read -r file; do
        name=$(sed -n '1,10s/^name:[[:space:]]*//p' "$file" | head -1 | tr -d "\"'"[:space:])
        [ -n "$name" ] || name=$(basename "$(dirname "$file")")
        printf '%s\n' "$name"
    done | sort -u
}

# Report a skill name that the shared tree and a client root both provide. The
# client keeps the first copy it finds and warns about the second, so the
# shared tree is the portable home and the client root holds only names the
# shared tree does not provide. The deployment reports the duplicate instead
# of removing a file the client owns.
report_skill_collisions() {
    local shared="$HOME/.agents/skills"
    local catalog="$DEPLOY_SOURCE/deployment/agent-payload/skill-roots.tsv"
    local client root shared_names client_names duplicate name
    [ -f "$catalog" ] || return 0
    [ -d "$shared" ] || return 0
    while IFS='|' read -r client root; do
        case "$client" in ''|\#*) continue ;; esac
        [ -d "$HOME/$root" ] || continue
        shared_names=$(mktemp "$TMPDIR/skill-shared.XXXXXX") || return 0
        client_names=$(mktemp "$TMPDIR/skill-client.XXXXXX") || { rm -f "$shared_names"; return 0; }
        payload_skill_names "$shared" > "$shared_names"
        payload_skill_names "$HOME/$root" > "$client_names"
        duplicate=$(comm -12 "$shared_names" "$client_names")
        rm -f "$shared_names" "$client_names"
        for name in $duplicate; do
            printf 'dotfiles: skill %s is in both %s and %s; %s keeps the first copy and warns about the second\n' \
                "$name" "$shared" "$HOME/$root" "$client" >&2
        done
    done < "$catalog"
    return 0
}
