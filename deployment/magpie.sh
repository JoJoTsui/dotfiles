# The Magpie model gateway: the deployment's half.
#
# The repository owns the catalogs and the agent wiring. Magpie owns the
# credentials, the accounts, the usage store, and the generated agent
# artifacts. This file validates the catalogs, applies them through the
# Magpie CLI, and reports what the device runs.
#
# Sourcing this file declares functions only. The deployment step calls
# magpie_apply, and ~/.local/bin/dotfiles-magpie calls the same functions from
# the copy of this file that the source application leaves in the home.

# The catalogs, relative to the deployment source.
MAGPIE_CATALOG_SOURCE="deployment/magpie"
# The device state the apply records.
MAGPIE_STATE_SOURCE=".local/state/dotfiles/magpie"
# How many timestamped backups the apply keeps.
MAGPIE_BACKUP_KEEP=10
# The gateway the deployment expects. The running gateway reports its own
# address, and this is the fallback.
MAGPIE_GATEWAY_DEFAULT="http://127.0.0.1:3425"
# The Magpie provider presets a catalog row may name. Magpie owns this list,
# so a catalog may not invent a preset.
MAGPIE_PROVIDER_PRESETS="codex opencode-go kimi-code-cn minimax-cn"
# The device store that holds credentials the deployment may read.
MAGPIE_ENV_FILE=".config/dotfiles/magpie.env"

magpie_fail() {
    # The deployment owns the failure vocabulary; a standalone run reports the
    # same line and returns a failing status.
    if command -v fail >/dev/null 2>&1; then
        fail "magpie: $*"
    fi
    printf 'dotfiles: magpie: %s\n' "$*" >&2
    return 1
}

# The directory the catalogs are read from. The deployment reads the working
# tree; the managed command reads the copy the source application leaves in
# the home.
magpie_catalog_dir() {
    if [ -n "${MAGPIE_CATALOG_DIR:-}" ]; then printf '%s' "$MAGPIE_CATALOG_DIR"; return 0; fi
    if [ -n "${DEPLOY_SOURCE:-}" ] && [ -d "${DEPLOY_SOURCE}/${MAGPIE_CATALOG_SOURCE}" ]; then
        printf '%s' "${DEPLOY_SOURCE}/${MAGPIE_CATALOG_SOURCE}"
        return 0
    fi
    printf '%s' "${HOME}/.config/dotfiles/magpie"
}

# Whether a delimited list holds an item.
magpie_list_contains() {
    case "$1" in
        *"|$2|"*) return 0 ;;
    esac
    return 1
}

# A catalog identifier: letters, digits, dots, dashes, and underscores.
magpie_name_ok() {
    case "$1" in
        ''|*[!A-Za-z0-9._-]*) return 1 ;;
    esac
    return 0
}

# A catalog value that looks like a credential is rejected: a catalog names a
# source, never a secret.
magpie_value_is_secret() {
    local value=$1
    case "$value" in
        *-----BEGIN*|*eyJ[A-Za-z0-9_-]*|*glmfix_*|*ghp_*|*gho_*|*github_pat_*|*xoxb-*|*xoxp-*|*AKIA[0-9A-Z]*|*"Bearer "*|*[!A-Za-z]sk-[A-Za-z0-9]*|sk-[A-Za-z0-9]*|*[!A-Za-z]pk-[A-Za-z0-9]*|pk-[A-Za-z0-9]*)
            return 0 ;;
    esac
    # A long opaque token carries no path, colon, or space.
    case "$value" in *[/:\ ]*) return 1 ;; esac
    [ "${#value}" -ge 32 ] || return 1
    case "$value" in *[!A-Za-z0-9_=-]*) return 1 ;; esac
    return 0
}

# One catalog row, split into its fields. A row with the wrong field count is
# rejected by name.
magpie_row_fields() {
    local row=$1 wanted=$2 label=$3 count
    MAGPIE_ROW_FIELDS=()
    IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$row"
    count=${#MAGPIE_ROW_FIELDS[@]}
    if [ "$count" != "$wanted" ]; then
        magpie_fail "$label row needs $wanted fields, found $count: $row"
        return 1
    fi
    return 0
}

# The provider catalog: role, Magpie provider, key source, required.
magpie_catalog_providers() {
    local file=$1 line role preset source required count
    local variable rest path key
    MAGPIE_PROVIDER_ROLES=''
    MAGPIE_PROVIDER_PRESET_ROWS=''
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        magpie_row_fields "$line" 4 provider || return 1
        role=${MAGPIE_ROW_FIELDS[0]}; preset=${MAGPIE_ROW_FIELDS[1]}
        source=${MAGPIE_ROW_FIELDS[2]}; required=${MAGPIE_ROW_FIELDS[3]}
        magpie_name_ok "$role" || { magpie_fail "invalid provider role: $role"; return 1; }
        if magpie_list_contains "$MAGPIE_PROVIDER_ROLES" "$role"; then
            magpie_fail "duplicate provider role: $role"
            return 1
        fi
        case " $MAGPIE_PROVIDER_PRESETS " in
            *" $preset "*) ;;
            *) magpie_fail "unknown Magpie provider preset: $preset"; return 1 ;;
        esac
        if magpie_list_contains "$MAGPIE_PROVIDER_PRESET_ROWS" "$preset"; then
            magpie_fail "duplicate Magpie provider preset: $preset"
            return 1
        fi
        case "$source" in
            codex-account) ;;
            env:*)
                variable=${source#env:}
                case "$variable" in
                    ''|*[!A-Z0-9_]*) magpie_fail "invalid provider key source: $source"; return 1 ;;
                esac ;;
            json:*)
                rest=${source#json:}
                key=${rest##*:}
                path=${rest%:*}
                case "$path" in
                    '~/'*|/*) ;;
                    *) magpie_fail "invalid provider key source: $source"; return 1 ;;
                esac
                case "$key" in
                    ''|*[!A-Za-z0-9._-]*) magpie_fail "invalid provider key source: $source"; return 1 ;;
                esac ;;
            *) magpie_fail "invalid provider key source: $source"; return 1 ;;
        esac
        case "$required" in
            yes|no) ;;
            *) magpie_fail "invalid provider required flag: $required"; return 1 ;;
        esac
        MAGPIE_PROVIDER_ROLES="$MAGPIE_PROVIDER_ROLES|$role|"
        MAGPIE_PROVIDER_PRESET_ROWS="$MAGPIE_PROVIDER_PRESET_ROWS|$role=$preset|"
    done < "$file"
    return 0
}

# The model catalog: role, ordered candidate ids, required.
magpie_catalog_models() {
    local file=$1 line role candidates required count candidate id provider model
    local -a candidate_list
    MAGPIE_MODEL_ROLES=''
    MAGPIE_MODEL_CANDIDATES=''
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        magpie_row_fields "$line" 3 model || return 1
        role=${MAGPIE_ROW_FIELDS[0]}; candidates=${MAGPIE_ROW_FIELDS[1]}; required=${MAGPIE_ROW_FIELDS[2]}
        magpie_name_ok "$role" || { magpie_fail "invalid model role: $role"; return 1; }
        if magpie_list_contains "$MAGPIE_MODEL_ROLES" "$role"; then
            magpie_fail "duplicate model role: $role"
            return 1
        fi
        IFS=, read -r -a candidate_list <<< "$candidates"
        [ "${#candidate_list[@]}" -gt 0 ] || { magpie_fail "model role has no candidate: $role"; return 1; }
        for candidate in "${candidate_list[@]}"; do
            id=$candidate
            case "$candidate" in
                *'?'*) id=${candidate%?} ;;
            esac
            case "$id" in
                */*) provider=${id%%/*}; model=${id#*/} ;;
                *) magpie_fail "invalid model id: $candidate"; return 1 ;;
            esac
            magpie_name_ok "$provider" || { magpie_fail "invalid model id: $candidate"; return 1; }
            magpie_name_ok "$model" || { magpie_fail "invalid model id: $candidate"; return 1; }
        done
        case "$required" in
            yes|no) ;;
            *) magpie_fail "invalid model required flag: $required"; return 1 ;;
        esac
        MAGPIE_MODEL_ROLES="$MAGPIE_MODEL_ROLES|$role|"
        MAGPIE_MODEL_CANDIDATES="$MAGPIE_MODEL_CANDIDATES|$role=$candidates|"
    done < "$file"
    return 0
}

# The routing group catalog: id, members, routing, stays, listed, purpose.
magpie_catalog_groups() {
    local file=$1 line id members routing stays listed purpose member
    local -a member_list
    MAGPIE_GROUP_IDS=''
    MAGPIE_GROUP_MEMBERS=''
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        magpie_row_fields "$line" 6 group || return 1
        id=${MAGPIE_ROW_FIELDS[0]}; members=${MAGPIE_ROW_FIELDS[1]}
        routing=${MAGPIE_ROW_FIELDS[2]}; stays=${MAGPIE_ROW_FIELDS[3]}
        listed=${MAGPIE_ROW_FIELDS[4]}; purpose=${MAGPIE_ROW_FIELDS[5]}
        magpie_name_ok "$id" || { magpie_fail "invalid group id: $id"; return 1; }
        if magpie_list_contains "$MAGPIE_GROUP_IDS" "$id"; then
            magpie_fail "duplicate group id: $id"
            return 1
        fi
        IFS=, read -r -a member_list <<< "$members"
        [ "${#member_list[@]}" -gt 0 ] || { magpie_fail "group has no member: $id"; return 1; }
        for member in "${member_list[@]}"; do
            case "$member" in
                group/*)
                    magpie_name_ok "${member#group/}" || { magpie_fail "invalid group member: $member"; return 1; } ;;
                *)
                    magpie_name_ok "$member" || { magpie_fail "invalid group member: $member"; return 1; } ;;
            esac
        done
        case "$routing" in
            drain) ;;
            *) magpie_fail "unknown routing mode: $routing"; return 1 ;;
        esac
        case "$stays" in
            auto) ;;
            *) magpie_fail "unknown stay mode: $stays"; return 1 ;;
        esac
        case "$listed" in
            yes|no) ;;
            *) magpie_fail "invalid group listed flag: $listed"; return 1 ;;
        esac
        [ -n "$purpose" ] || { magpie_fail "group has no purpose: $id"; return 1; }
        MAGPIE_GROUP_IDS="$MAGPIE_GROUP_IDS|$id|"
        MAGPIE_GROUP_MEMBERS="$MAGPIE_GROUP_MEMBERS|$id=$members|"
    done < "$file"
    return 0
}

# The agent wiring catalog: agent, group, owner, enabled.
magpie_catalog_wiring() {
    local file=$1 line agent group owner enabled
    MAGPIE_WIRING_ROWS=''
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        magpie_row_fields "$line" 4 wiring || return 1
        agent=${MAGPIE_ROW_FIELDS[0]}; group=${MAGPIE_ROW_FIELDS[1]}
        owner=${MAGPIE_ROW_FIELDS[2]}; enabled=${MAGPIE_ROW_FIELDS[3]}
        magpie_name_ok "$agent" || { magpie_fail "invalid wiring agent: $agent"; return 1; }
        case "$group" in
            -|group/*) ;;
            *) magpie_fail "invalid wiring group: $group"; return 1 ;;
        esac
        case "$owner" in
            repo|magpie|inherited) ;;
            *) magpie_fail "unknown wiring owner: $owner"; return 1 ;;
        esac
        case "$enabled" in
            yes|no) ;;
            *) magpie_fail "invalid wiring enabled flag: $enabled"; return 1 ;;
        esac
        MAGPIE_WIRING_ROWS="$MAGPIE_WIRING_ROWS|$agent=$group=$owner=$enabled|"
    done < "$file"
    return 0
}

# The value of one "|key=value|" list entry.
magpie_list_value() {
    local list=$1 key=$2 rest
    rest=${list#*"|$key="}
    case "$rest" in
        "$list") return 1 ;;
    esac
    printf '%s' "${rest%%|*}"
}

# Validate the four catalogs against each other. A bad catalog is rejected by
# name before the deployment writes a file.
magpie_catalog_validate() {
    local dir=${1:-}
    [ -n "$dir" ] || dir=$(magpie_catalog_dir)
    local providers="$dir/providers.tsv" models="$dir/models.tsv"
    local groups="$dir/groups.tsv" wiring="$dir/wiring.tsv"
    local file line group member role candidates candidate id provider agent
    local member_list_text has_role
    local -a candidate_list member_list
    for file in "$providers" "$models" "$groups" "$wiring"; do
        [ -f "$file" ] || { magpie_fail "catalog is missing: ${file##*/}"; return 1; }
        [ ! -L "$file" ] || { magpie_fail "catalog is a symlink: ${file##*/}"; return 1; }
    done
    # No catalog value carries a credential. The scan runs before the shape
    # checks, so a pasted key is reported as a credential.
    for file in "$providers" "$models" "$groups" "$wiring"; do
        while IFS= read -r line || [ -n "$line" ]; do
            line=${line%$'\r'}
            case "$line" in ''|\#*) continue ;; esac
            IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$line"
            for member in "${MAGPIE_ROW_FIELDS[@]}"; do
                if magpie_value_is_secret "$member"; then
                    magpie_fail "catalog value looks like a credential: ${file##*/}: $member"
                    return 1
                fi
            done
        done < "$file"
    done
    magpie_catalog_providers "$providers" || return 1
    magpie_catalog_models "$models" || return 1
    magpie_catalog_groups "$groups" || return 1
    magpie_catalog_wiring "$wiring" || return 1
    # Every model candidate names a declared Magpie provider.
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$line"
        role=${MAGPIE_ROW_FIELDS[0]}; candidates=${MAGPIE_ROW_FIELDS[1]}
        IFS=, read -r -a candidate_list <<< "$candidates"
        for candidate in "${candidate_list[@]}"; do
            case "$candidate" in
                *'?'*) candidate=${candidate%?} ;;
            esac
            provider=${candidate%%/*}
            case " $MAGPIE_PROVIDER_PRESETS " in
                *" $provider "*) ;;
                *) magpie_fail "model role $role names an undeclared provider: $provider"; return 1 ;;
            esac
        done
    done < "$models"
    # Every group member exists, and every group holds a model role.
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$line"
        id=${MAGPIE_ROW_FIELDS[0]}; member_list_text=${MAGPIE_ROW_FIELDS[1]}
        IFS=, read -r -a member_list <<< "$member_list_text"
        has_role=''
        for member in "${member_list[@]}"; do
            case "$member" in
                group/*)
                    if ! magpie_list_contains "$MAGPIE_GROUP_IDS" "${member#group/}"; then
                        magpie_fail "group $id names an undeclared group: ${member#group/}"
                        return 1
                    fi ;;
                *)
                    if ! magpie_list_contains "$MAGPIE_MODEL_ROLES" "$member"; then
                        magpie_fail "group $id names an unknown model role: $member"
                        return 1
                    fi
                    has_role=yes ;;
            esac
        done
        if [ -z "$has_role" ]; then
            magpie_fail "group $id has no model role"
            return 1
        fi
    done < "$groups"
    # Every wired group exists, and an inherited wiring names no group.
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$line"
        agent=${MAGPIE_ROW_FIELDS[0]}; group=${MAGPIE_ROW_FIELDS[1]}; owner=${MAGPIE_ROW_FIELDS[2]}
        if [ "$group" = '-' ]; then
            if [ "$owner" != inherited ]; then
                magpie_fail "agent $agent inherits its wiring but names owner $owner"
                return 1
            fi
            continue
        fi
        if ! magpie_list_contains "$MAGPIE_GROUP_IDS" "${group#group/}"; then
            magpie_fail "agent $agent names an undeclared group: ${group#group/}"
            return 1
        fi
    done < "$wiring"
    return 0
}
