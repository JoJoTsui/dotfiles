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

# A payload source holds regular resources only. A symlink in the source
# would carry a copy outside the managed tree.
payload_validate_source() {
    local source=$1 entry
    [ ! -L "$source" ] || fail "agent payload source is a symlink: $source"
    if [ -d "$source" ]; then
        for entry in "$source"/* "$source"/.[!.]* "$source"/..?*; do
            [ -e "$entry" ] || [ -L "$entry" ] || continue
            payload_validate_source "$entry"
        done
        return 0
    fi
    [ -f "$source" ] || fail "unsupported agent payload resource: $source"
    return 0
}

payload_validate_tree() {
    local source=$1 target=$2 entry
    payload_validate_source "$source"
    payload_safe_destination "$target"
    if [ -d "$source" ]; then
        [ ! -e "$target" ] || [ -d "$target" ] || fail "agent payload directory conflicts with a file: $target"
        for entry in "$source"/* "$source"/.[!.]* "$source"/..?*; do
            [ -e "$entry" ] || [ -L "$entry" ] || continue
            payload_validate_tree "$entry" "$target/${entry##*/}"
        done
    elif [ -f "$source" ]; then
        [ ! -e "$target" ] || [ -f "$target" ] || fail "agent payload file conflicts with a directory: $target"
    fi
}

payload_source_path() {
    if [ "$1" = skills ] && [ -n "${PAYLOAD_SKILLS_DIR:-}" ]; then
        printf '%s' "$PAYLOAD_SKILLS_DIR"
    else
        printf '%s' "$DEPLOY_SOURCE/deployment/agent-payload/$1"
    fi
}

# Validate the sources of the skills the deployment writes. A skill the
# selection leaves out is not written, so its destination is not the
# deployment's business; the prune reports that entry and preserves it. The
# destination of a written skill is inspected when the skill is copied: a
# device entry there is preserved and reported, never written through.
payload_validate_skills() {
    local origin=$1 target=$2 entry name selection
    [ ! -L "$origin" ] || fail "agent payload source is a symlink: $origin"
    payload_safe_destination "$target"
    for entry in "$origin"/* "$origin"/.[!.]* "$origin"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        name=${entry##*/}
        payload_skill_disabled "$name" && continue
        selection=$(skill_catalog_selection "$name")
        [ -n "$selection" ] || continue
        skill_selected "$name" "$selection" || continue
        payload_validate_source "$entry"
    done
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
        if [ "$source" = skills ] && [ -n "${PAYLOAD_SKILLS_DIR:-}" ]; then
            payload_validate_skills "$origin" "$DEPLOY_HOME/$target"
            continue
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

# The skill directories this deployment wrote into each managed root. The
# prune step reads the record to tell a managed skill from a device skill.
PAYLOAD_SKILL_WRITTEN=()

# The generated skill rows the deployment owns in the other managed roots.
PAYLOAD_GENERATED_SKILL_ROWS=()

# Whether the previous inventory recorded a managed skill in a root. The copy
# step reads that record before the prune rewrites it, so it knows which
# destinations the deployment owns.
payload_previous_managed_skill() {
    local state name=$1 root=$2
    state=$(payload_managed_skills_state)
    [ -f "$state" ] || return 1
    PAYLOAD_MANAGED_NAME=$name PAYLOAD_MANAGED_ROOT=$root awk -F '|' '
        BEGIN { name = ENVIRON["PAYLOAD_MANAGED_NAME"]; root = ENVIRON["PAYLOAD_MANAGED_ROOT"] }
        !/^#/ && NF >= 2 && $1 == name && $2 == root { found = 1 }
        END { exit !found }
    ' "$state"
}

# The entries of a skill directory, with their kinds. Two trees with the same
# entries hold the same resources.
payload_tree_entries() {
    local root=$1
    (
        cd "$root" || exit 1
        find . -mindepth 1 | LC_ALL=C sort | while IFS= read -r path; do
            if [ -L "$path" ]; then
                printf 'l %s\n' "$path"
            elif [ -d "$path" ]; then
                printf 'd %s\n' "$path"
            else
                printf 'f %s\n' "$path"
            fi
        done
    )
}

# Whether two skill directories hold the same entries and the same bytes.
payload_tree_identical() {
    local staged=$1 existing=$2 staged_entries existing_entries
    [ -d "$existing" ] || return 1
    staged_entries=$(mktemp "$TMPDIR/payload-tree-staged.XXXXXX") || return 1
    existing_entries=$(mktemp "$TMPDIR/payload-tree-existing.XXXXXX") || {
        rm -f "$staged_entries"
        return 1
    }
    payload_tree_entries "$staged" > "$staged_entries"
    payload_tree_entries "$existing" > "$existing_entries"
    if ! cmp -s "$staged_entries" "$existing_entries"; then
        rm -f "$staged_entries" "$existing_entries"
        return 1
    fi
    rm -f "$staged_entries" "$existing_entries"
    # The entries match, so the contents decide. A difference of any kind
    # leaves the device directory alone.
    diff -r "$staged" "$existing" >/dev/null 2>&1
}

# Report a device entry that carries the name of a selected skill. The
# deployment preserves it and never writes through it.
payload_report_collision() {
    local name=$1 root=$2 reason=$3
    printf 'dotfiles: preserved skill %s in %s; %s\n' "$name" "$root" "$reason" >&2
}

# Copy one selected skill into a managed root. The destination decides what
# happens: a device entry is preserved and reported, a directory the
# deployment owns is replaced, and a directory that already holds these bytes
# is adopted without a rewrite.
payload_copy_skill() {
    local staged=$1 destination=$2 name=$3 root=$4
    if [ -L "$destination" ]; then
        payload_report_collision "$name" "$root" 'a device symlink has that name'
        return 0
    fi
    if [ -e "$destination" ] && [ ! -d "$destination" ]; then
        payload_report_collision "$name" "$root" 'a device file has that name'
        return 0
    fi
    if [ -d "$destination" ]; then
        if payload_previous_managed_skill "$name" "$root"; then
            # The deployment owns the directory, so the staged copy replaces
            # it and the bytes it no longer carries are gone.
            rm -rf -- "$destination" || fail "cannot replace the managed skill $name in $root"
            [ ! -e "$destination" ] || fail "cannot replace the managed skill $name in $root"
        elif payload_tree_identical "$staged" "$destination"; then
            # The device already holds these bytes, so the deployment adopts
            # the directory and never rewrites it.
            PAYLOAD_SKILL_WRITTEN+=("$name|$root")
            return 0
        else
            payload_report_collision "$name" "$root" 'a device directory has that name and its bytes differ'
            return 0
        fi
    fi
    cp -Rp "$staged" "$destination" || fail "cannot copy the skill $name into $root"
    PAYLOAD_SKILL_WRITTEN+=("$name|$root")
}

payload_copy_skills() {
    local origin=$1 target=$2 root=$3 entry name selection
    mkdir -p "$target"
    for entry in "$origin"/* "$origin"/.[!.]* "$origin"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        name=${entry##*/}
        payload_skill_disabled "$name" && continue
        # The catalog owns a managed root. A name the catalog does not
        # declare is device content and never enters one, and a tagged skill
        # enters only when the host asks for it by tag or by name.
        selection=$(skill_catalog_selection "$name")
        [ -n "$selection" ] || continue
        skill_selected "$name" "$selection" || continue
        payload_copy_skill "$entry" "$target/$name" "$name" "$root"
    done
}

# Copy a generated skill into every managed skill root but the one that holds
# the generated bytes. The deployment owns the generated skill in each root,
# so the copy refreshes it when the tool changed; a device entry at the
# destination is preserved and reported, and the copy never writes through it.
payload_copy_generated_skill() {
    local name=$1 source=$2 origin_root=$3 generator=$4 root destination
    PAYLOAD_GENERATED_SKILL_ROWS=()
    while IFS= read -r root; do
        [ -n "$root" ] || continue
        [ "$root" = "$origin_root" ] && continue
        payload_safe_destination "$HOME/$root"
        destination="$HOME/$root/$name"
        if [ -L "$destination" ]; then
            payload_report_collision "$name" "$root" 'a device symlink has that name'
            continue
        fi
        if [ -e "$destination" ] && [ ! -d "$destination" ]; then
            payload_report_collision "$name" "$root" 'a device file has that name'
            continue
        fi
        if [ -L "$destination/SKILL.md" ]; then
            payload_report_collision "$name" "$root" 'a device symlink has that name'
            continue
        fi
        mkdir -p "$destination" || fail "cannot create the generated skill directory: $destination"
        if [ ! -f "$destination/SKILL.md" ] || ! cmp -s "$source" "$destination/SKILL.md"; then
            cp "$source" "$destination/SKILL.md" ||
                fail "cannot write the generated skill: $destination/SKILL.md"
            chmod 644 "$destination/SKILL.md" ||
                fail "cannot set the permissions of the generated skill: $destination/SKILL.md"
        fi
        PAYLOAD_GENERATED_SKILL_ROWS+=("$name|$root|$generator")
    done <<EOF
$(payload_skill_roots)
EOF
    return 0
}

# The managed skill roots: the tree rows that copy the skill library. A root
# the deployment does not own is never recorded and never pruned.
payload_skill_roots() {
    local payload="$DEPLOY_SOURCE/deployment/agent-payload" kind source target
    [ -f "$payload/targets.tsv" ] || return 0
    while IFS=$'|\r' read -r kind source target; do
        [ "$kind" = tree ] || continue
        [ "$source" = skills ] || continue
        case "$target" in ''|\#*) continue ;; esac
        printf '%s\n' "$target"
    done < "$payload/targets.tsv"
}

# Whether the deployment owns a skill root.
payload_owned_skill_root() {
    local root=$1 owned
    while IFS= read -r owned; do
        [ -n "$owned" ] || continue
        [ "$owned" = "$root" ] && return 0
    done <<EOF
$(payload_skill_roots)
EOF
    return 1
}

# The managed skill inventory: the device-state record of the skill
# directories the deployment wrote into each managed root.
payload_managed_skills_state() {
    printf '%s' "${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/managed-skills.tsv"
}

# A generated skill comes from a tool installed on the device, so the prune
# leaves it alone even when the catalog knows the same name.
payload_generated_skill() {
    local state="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/generated-skills.tsv" name=$1 root=$2
    [ -f "$state" ] || return 1
    PAYLOAD_GENERATED_NAME=$name PAYLOAD_GENERATED_ROOT=$root awk -F '|' '
        BEGIN { name = ENVIRON["PAYLOAD_GENERATED_NAME"]; root = ENVIRON["PAYLOAD_GENERATED_ROOT"] }
        !/^#/ && NF >= 2 && $1 == name && $2 == root { found = 1 }
        END { exit !found }
    ' "$state"
}

# Report the entries a managed root holds that the deployment does not own.
# They are device content: they are named and never removed.
report_device_skills() {
    local inventory=$1 root entry name selection
    while IFS= read -r root; do
        [ -n "$root" ] || continue
        [ -d "$HOME/$root" ] || continue
        for entry in "$HOME/$root"/* "$HOME/$root"/.[!.]* "$HOME/$root"/..?*; do
            [ -e "$entry" ] || [ -L "$entry" ] || continue
            name=${entry##*/}
            if grep -q -F -x "$name|$root" "$inventory"; then continue; fi
            if payload_generated_skill "$name" "$root"; then continue; fi
            selection=$(skill_catalog_selection "$name")
            # A selected skill belongs to the profile even when the library
            # did not carry it, so it is not a leftover.
            if [ -n "$selection" ] && skill_selected "$name" "$selection"; then continue; fi
            if [ -n "$selection" ]; then
                printf 'dotfiles: preserved skill %s in %s; the selection does not include it\n' \
                    "$name" "$root" >&2
            else
                printf 'dotfiles: preserved device skill %s in %s\n' "$name" "$root" >&2
            fi
        done
    done <<EOF
$(payload_skill_roots)
EOF
    return 0
}

# Prune the managed skills that left the profile. The inventory names the
# directories the deployment wrote into each managed root; a directory that is
# no longer selected is removed from its root. A device skill, a generated
# skill, and a symlinked entry are preserved and reported instead.
prune_managed_skills() {
    local state previous written kept inventory staged row name root path selection
    state=$(payload_managed_skills_state)
    validate_skill_state "$state"
    previous=$(mktemp "$TMPDIR/skill-inventory-previous.XXXXXX") || fail 'cannot create the skill inventory'
    written=$(mktemp "$TMPDIR/skill-inventory-written.XXXXXX") || fail 'cannot create the skill inventory'
    kept=$(mktemp "$TMPDIR/skill-inventory-kept.XXXXXX") || fail 'cannot create the skill inventory'
    if [ -f "$state" ]; then
        grep -v '^#' "$state" > "$previous" || true
    else
        : > "$previous"
    fi
    for row in ${PAYLOAD_SKILL_WRITTEN[@]+"${PAYLOAD_SKILL_WRITTEN[@]}"}; do
        printf '%s\n' "$row" >> "$written"
    done
    while IFS='|' read -r name root; do
        [ -n "$name" ] && [ -n "$root" ] || continue
        # A root the deployment does not own is never recorded and never
        # pruned: the entries there belong to somebody else.
        if ! payload_owned_skill_root "$root"; then
            printf 'dotfiles: preserved skill %s in %s; the deployment does not own that root\n' \
                "$name" "$root" >&2
            continue
        fi
        selection=$(skill_catalog_selection "$name")
        if [ -n "$selection" ] && skill_selected "$name" "$selection"; then
            # The skill is still part of the profile, so the deployment keeps
            # managing it.
            printf '%s|%s\n' "$name" "$root" >> "$kept"
            continue
        fi
        path="$HOME/$root/$name"
        if [ ! -e "$path" ] && [ ! -L "$path" ]; then
            # The entry is already gone, so the inventory stops claiming it.
            continue
        fi
        if payload_generated_skill "$name" "$root"; then
            printf 'dotfiles: preserved generated skill %s in %s\n' "$name" "$root" >&2
            printf '%s|%s\n' "$name" "$root" >> "$kept"
            continue
        fi
        if [ -L "$path" ]; then
            # A symlinked entry is never followed and never deleted through.
            printf 'dotfiles: preserved managed skill %s in %s; refused to follow a symlink\n' \
                "$name" "$root" >&2
            printf '%s|%s\n' "$name" "$root" >> "$kept"
            continue
        fi
        if [ ! -d "$path" ]; then
            printf 'dotfiles: preserved managed skill %s in %s; it is not a managed directory\n' \
                "$name" "$root" >&2
            printf '%s|%s\n' "$name" "$root" >> "$kept"
            continue
        fi
        rm -rf -- "$path" || fail "cannot prune the managed skill $name from $root"
        printf 'dotfiles: pruned managed skill %s from %s\n' "$name" "$root" >&2
    done < "$previous"
    mkdir -p "$(dirname "$state")"
    inventory=$(mktemp "$TMPDIR/skill-inventory.XXXXXX") || fail 'cannot write the managed skill inventory'
    {
        printf '# name|root\n'
        cat "$written" "$kept" | sort -u
    } > "$inventory"
    staged=$(mktemp "$state.XXXXXX") || fail 'cannot write the managed skill inventory'
    cat "$inventory" > "$staged"
    mv -f "$staged" "$state"
    report_device_skills "$inventory"
    rm -f "$previous" "$written" "$kept" "$inventory"
    return 0
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
                    payload_copy_skills "$origin" "$HOME/$target" "$target"
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
# client keeps the first copy it finds, so the shared tree is the portable
# home and the client root holds only names the shared tree does not provide.
# The deployment reports the duplicate instead of removing a file the client
# owns.
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
            printf 'dotfiles: skill %s is in both %s and %s; %s keeps the first copy and neither entry is removed\n' \
                "$name" "$shared" "$HOME/$root" "$client" >&2
        done
    done < "$catalog"
    return 0
}
