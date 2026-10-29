# Skill library provisioning: the repository owns the catalog, not skill bytes.
# Every catalog row names an upstream source; the reviewed lock selects bytes
# fetched into staging before the agent payload copies them to discovery paths.
# Bash 3.2-compatible.

skill_refresh_check() {
    local marker age max_age
    case "${DOTFILES_SKILLS_REFRESH:-auto}" in
        0) SKILL_REFRESH=0; return 0 ;;
        1) SKILL_REFRESH=1; return 0 ;;
    esac
    marker=$(skills_cache_root)/.refreshed
    max_age=${DOTFILES_SKILLS_MAX_AGE:-21600}
    if [ ! -s "$marker" ]; then
        SKILL_REFRESH=1
        return 0
    fi
    age=$(( $(date +%s) - $(cat "$marker" 2>/dev/null || printf 0) ))
    if [ "$age" -ge "$max_age" ]; then SKILL_REFRESH=1; else SKILL_REFRESH=0; fi
}

skills_cache_root() {
    if [ -n "${DOTFILES_SKILLS_CACHE:-}" ]; then
        printf '%s' "$DOTFILES_SKILLS_CACHE"
    else
        printf '%s' "$XDG_CACHE_HOME/dotfiles/skills"
    fi
}

skill_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

skill_pin_for() {
    local name=$1 kind=$2 source=$3 entry entry_kind entry_source revision
    local lock=${DOTFILES_SKILLS_LOCK:-$DEPLOY_SOURCE/deployment/skills.lock.tsv}
    SKILL_PIN=''
    [ -f "$lock" ] || return 0
    [ ! -L "$lock" ] || fail 'skill lock is a symlink'
    while IFS=$'|\r' read -r entry entry_kind entry_source revision; do
        [ "$entry" = "$name" ] || continue
        [ "$entry_kind" = "$kind" ] && [ "$entry_source" = "$source" ] || fail "skill lock source mismatch: $name"
        [ -z "$SKILL_PIN" ] || fail "duplicate skill lock entry: $name"
        SKILL_PIN=$revision
    done < "$lock"
    case "$SKILL_PIN" in ''|*[!a-f0-9]*) fail "invalid or missing skill pin: $name" ;; esac
    if [ "$kind" = git ]; then
        [ "${#SKILL_PIN}" = 40 ] || fail "invalid git skill pin: $name"
    else
        [ "${#SKILL_PIN}" = 64 ] || fail "invalid archive skill pin: $name"
    fi
}

skill_slug() {
    printf '%s' "$1" | sed -e 's#^[A-Za-z][A-Za-z0-9+.-]*://##' -e 's#/*$##' -e 's#[^A-Za-z0-9._-]#_#g'
}

validate_skill_catalog() {
    local catalog="$DEPLOY_SOURCE/deployment/skills.tsv" name kind source ref path seen=' '
    [ -f "$catalog" ] || fail 'skill catalog is missing'
    [ ! -L "$catalog" ] || fail 'skill catalog is a symlink'
    while IFS=$'|\r' read -r name kind source ref path; do
        case "$name" in ''|\#*) continue ;; esac
        case " $seen " in *" $name "*) fail "duplicate skill catalog entry: $name" ;; esac
        seen="$seen$name "
        case "$name" in */*|*..*) fail "skill name must be a plain directory: $name" ;; esac
        [ -n "$source" ] || fail "skill source is missing: $name"
        case "$kind" in
            git)
                [ -n "$ref" ] || fail "skill ref is missing: $name"
                case "$path" in ''|/*|..|../*|*/../*|*/..) fail "skill path must be relative: $name" ;; esac
                ;;
            tarball) ;;
            *) fail "unknown skill kind: $kind" ;;
        esac
    done < "$catalog"
}

skill_archive_is_safe() {
    local archive=$1 listing entry mode
    listing=$(tar -tzf "$archive") || return 1
    while IFS= read -r entry; do
        case "$entry" in /*|..|../*|*/../*) return 1 ;; esac
    done <<EOF
$listing
EOF
    # Reject links: the payload promises regular resources only.
    while IFS= read -r mode; do
        case "$mode" in l*) return 1 ;; esac
    done <<EOF
$(tar -tzvf "$archive" | awk '{print substr($1,1,1)}')
EOF
}

skill_extract_archive() {
    local archive=$1 destination=$2
    mkdir -p "$destination"
    tar -xzf "$archive" -C "$destination" || return 1
    [ -f "$destination/SKILL.md" ] || return 1
}

skill_fetch_git() {
    local name=$1 source=$2 ref=$3 path=$4 cache=$5 destination=$6 index=$7
    local slug repo resolved depth
    slug=$(skill_slug "$source")
    repo="$cache/git/$slug"
    if [ -n "$SKILL_PIN" ]; then
        if [ ! -d "$repo/.git" ]; then
            git init --quiet "$repo" || return 1
            git -C "$repo" remote add origin "$source" || return 1
        fi
        if ! git -C "$repo" cat-file -e "$SKILL_PIN^{commit}" 2>/dev/null; then
            git -C "$repo" fetch --quiet --depth 1 origin "$SKILL_PIN" || return 1
        fi
        resolved=$SKILL_PIN
    elif [ ! -d "$repo/.git" ]; then
        git clone --quiet --no-checkout --depth 1 --branch "$ref" "$source" "$repo" >/dev/null 2>&1 || return 1
    elif [ "$SKILL_REFRESH" = 1 ]; then
        git -C "$repo" fetch --quiet --depth 1 origin "$ref" >/dev/null 2>&1 || SKILL_REFRESH_OK=0
    fi
    if [ -z "$SKILL_PIN" ]; then
        resolved=$(git -C "$repo" rev-parse FETCH_HEAD 2>/dev/null) || resolved=$(git -C "$repo" rev-parse HEAD 2>/dev/null) || return 1
    fi
    depth=$(printf '%s' "$path" | awk -F/ '{print NF}')
    mkdir -p "$destination/$name"
    git -C "$repo" archive "$resolved" "$path" 2>/dev/null | tar -x -C "$destination/$name" --strip-components="$depth" 2>/dev/null || return 1
    [ -f "$destination/$name/SKILL.md" ] || return 1
    printf '%s|git|%s|%s\n' "$name" "$source" "$resolved" >> "$index"
}

skill_fetch_tarball() {
    local name=$1 source=$2 cache=$3 destination=$4 index=$5
    local slug archive temporary
    slug=$(skill_slug "$source")
    archive="$cache/tarballs/$slug.tgz"
    mkdir -p "$cache/tarballs"
    temporary="$archive.part.$$"
    if [ "$SKILL_REFRESH" = 1 ] || [ ! -s "$archive" ]; then
        # Conditional download keeps repeat applies cheap and offline-safe.
        if ! curl -fsSL --connect-timeout 5 --max-time 90 -z "$archive" -o "$temporary" "$source" >/dev/null 2>&1; then
            SKILL_REFRESH_OK=0
            rm -f "$temporary"
            [ -s "$archive" ] || return 1
        fi
        if [ -s "$temporary" ]; then
            if [ -n "$SKILL_PIN" ] && [ "$(skill_sha256 "$temporary")" != "$SKILL_PIN" ]; then
                rm -f "$temporary"
                fail "skill archive checksum mismatch: $name; review an explicit skill update"
            fi
            mv "$temporary" "$archive"
        fi
    fi
    [ -s "$archive" ] || return 1
    [ -z "$SKILL_PIN" ] || [ "$(skill_sha256 "$archive")" = "$SKILL_PIN" ] || fail "skill archive checksum mismatch: $name"
    skill_archive_is_safe "$archive" || return 1
    skill_extract_archive "$archive" "$destination/$name" || return 1
    printf '%s|tarball|%s|%s\n' "$name" "$source" "$(skill_sha256 "$archive")" >> "$index"
}

# Fetch (or reuse) the catalog into PAYLOAD_SKILLS_DIR. A caller-supplied
# DOTFILES_SKILLS_DIR wins, which keeps tests and air-gapped hosts hermetic.
prepare_skill_library() {
    local catalog="$DEPLOY_SOURCE/deployment/skills.tsv"
    local cache name kind source ref path index
    local root="$TMPDIR/skills.$$"
    validate_skill_catalog
    if [ -n "${DOTFILES_SKILLS_DIR:-}" ]; then
        [ -d "$DOTFILES_SKILLS_DIR" ] || fail "DOTFILES_SKILLS_DIR is not a directory: $DOTFILES_SKILLS_DIR"
        PAYLOAD_SKILLS_DIR=$DOTFILES_SKILLS_DIR
        export PAYLOAD_SKILLS_DIR
        return 0
    fi
    cache=$(skills_cache_root)
    index="$root.index"
    rm -rf "$root" "$index"
    mkdir -p "$root" "$cache/git" "$cache/tarballs"
    skill_refresh_check
    SKILL_REFRESH_OK=1
    : > "$index"
    while IFS=$'|\r' read -r name kind source ref path; do
        case "$name" in ''|\#*) continue ;; esac
        skill_pin_for "$name" "$kind" "$source"
        case "$kind" in
            git)
                skill_fetch_git "$name" "$source" "$ref" "$path" "$cache" "$root" "$index" ||
                    fail "cannot fetch skill $name from $source ($ref)"
                ;;
            tarball)
                # A cached archive is usable even when the refresh fails.
                skill_fetch_tarball "$name" "$source" "$cache" "$root" "$index" ||
                    fail "cannot fetch skill $name from $source"
                ;;
        esac
    done < "$catalog"
    mkdir -p "$XDG_STATE_HOME/dotfiles"
    {
        printf '# name|kind|source|resolved\n'
        cat "$index"
    } > "$XDG_STATE_HOME/dotfiles/skills.lock.tsv"
    rm -f "$index"
    if [ "$SKILL_REFRESH" = 1 ] && [ "$SKILL_REFRESH_OK" = 1 ]; then
        date +%s > "$cache/.refreshed"
    fi
    PAYLOAD_SKILLS_DIR=$root
    export PAYLOAD_SKILLS_DIR
}

cleanup_skill_library() {
    case "${PAYLOAD_SKILLS_DIR:-}" in
        "$TMPDIR"/skills.*) rm -rf "$PAYLOAD_SKILLS_DIR" "$PAYLOAD_SKILLS_DIR.index" ;;
    esac
    unset PAYLOAD_SKILLS_DIR
}
