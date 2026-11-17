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
# How many timestamped backups the apply keeps.
MAGPIE_BACKUP_KEEP=10
# The gateway the deployment expects. The running gateway reports its own
# address, and this is the fallback.
MAGPIE_GATEWAY_DEFAULT="http://127.0.0.1:3425"
# The Magpie provider presets a catalog row may name. Magpie owns this list,
# so a catalog may not invent a preset.
MAGPIE_PROVIDER_PRESETS="codex opencode-go kimi-code-cn minimax-cn openai zed"
# The reasoning efforts Magpie accepts after a model id. A group member may pin
# one as "role:<effort>".
MAGPIE_EFFORTS="none minimal low medium high xhigh max"
# The device store that holds credentials the deployment may read.
MAGPIE_ENV_FILE=".config/dotfiles/magpie.env"
# The Homebrew cask the deployment adopts, and the lowest app version it
# accepts. The deployment never installs the cask and never upgrades it: the
# operator owns the app, the gateway process, and its login item.
MAGPIE_CASK_NAME="magpie"
MAGPIE_CASK_FLOOR="0.1.4325"

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

# Whether a comma-separated list holds an item.
magpie_csv_contains() {
    case ",$1," in
        *",$2,"*) return 0 ;;
    esac
    return 1
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

# A catalog identifier: letters, digits, dots, dashes, and underscores.
magpie_name_ok() {
    case "$1" in
        ''|*[!A-Za-z0-9._-]*) return 1 ;;
    esac
    return 0
}

# A group member, split into its role and its optional reasoning effort. A
# member is "role" or "role:<effort>"; the effort is one of Magpie's
# reasoning levels and is appended to every model id the role resolves to. A
# group reference keeps its own routing, so it carries no effort.
magpie_member_split() {
    local member=$1 role effort
    MAGPIE_MEMBER_ROLE=''
    MAGPIE_MEMBER_EFFORT=''
    case "$member" in
        group/*)
            case "$member" in
                *:*)
                    magpie_fail "a group member cannot carry a reasoning effort: $member"
                    return 1 ;;
            esac
            MAGPIE_MEMBER_ROLE=$member
            return 0 ;;
    esac
    case "$member" in
        *:*)
            role=${member%%:*}
            effort=${member#*:}
            case " $MAGPIE_EFFORTS " in
                *" $effort "*) ;;
                *) magpie_fail "unknown reasoning effort in group member: $member"; return 1 ;;
            esac
            MAGPIE_MEMBER_ROLE=$role
            MAGPIE_MEMBER_EFFORT=$effort
            ;;
        *) MAGPIE_MEMBER_ROLE=$member ;;
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

# The Magpie CLI. Every external call goes through this helper, so a test can
# substitute a fake binary and record the exact command sequence.
magpie_run() {
    "${MAGPIE_BIN:-magpie}" "$@"
}

# The platform the deployment runs on.
magpie_platform() {
    if [ -n "${DEPLOY_PLATFORM:-}" ]; then printf '%s' "$DEPLOY_PLATFORM"; return 0; fi
    case "$(uname -s)" in
        Darwin) printf 'macos' ;;
        *) printf 'unsupported' ;;
    esac
}

# The device state directory the apply records. The state belongs to the home
# the apply runs against, so an inherited XDG path never redirects it.
magpie_state_dir() {
    local state="${XDG_STATE_HOME:-$HOME/.local/state}"
    case "$state" in
        "$HOME"/*) ;;
        *) state="$HOME/.local/state" ;;
    esac
    printf '%s' "$state/dotfiles/magpie"
}

# The digest of one file. A missing file has no digest.
magpie_sha256() {
    local file=$1
    [ -f "$file" ] || return 1
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file" | awk '{print $1}'
    else
        shasum -a 256 "$file" | awk '{print $1}'
    fi
}

# The Python the deployment reads JSON with.
magpie_python() {
    local candidate
    for candidate in "${MAGPIE_PYTHON:-}" "${DOTFILES_COMMON_BIN:-}/python3" "${PIXI_HOME:-}/bin/python3" "$(command -v python3 2>/dev/null || true)"; do
        [ -n "$candidate" ] || continue
        [ -x "$candidate" ] || continue
        printf '%s' "$candidate"
        return 0
    done
    return 1
}

# One value of a JSON store, read by a dotted key path. The store is read
# only, and the value never reaches a log or a report.
magpie_json_value() {
    local path=$1 key=$2 python
    case "$path" in
        '~/'*) path="$HOME/${path#\~/}" ;;
    esac
    [ -f "$path" ] || return 1
    python=$(magpie_python) || return 1
    "$python" - "$path" "$key" <<'PYTHON'
import json
import sys

path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    raise SystemExit(1)
for part in key.split("."):
    if not isinstance(data, dict) or part not in data:
        raise SystemExit(1)
    data = data[part]
if not isinstance(data, str) or not data:
    raise SystemExit(1)
sys.stdout.write(data)
PYTHON
}

# Magpie's settings file. The app owns it; the deployment reads the picked
# list and writes only the pickedModels block back.
magpie_settings_file() {
    printf '%s/magpie/settings.json' "${XDG_CONFIG_HOME:-$HOME/.config}"
}

# One agent's picked list, as a comma-separated string. Empty when unset.
magpie_picked_current() {
    local agent=$1 settings python
    settings=$(magpie_settings_file)
    [ -f "$settings" ] || { printf ''; return 0; }
    python=$(magpie_python) || return 1
    "$python" - "$settings" "$agent" <<'PYTHON'
import json
import sys

path, agent = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
except FileNotFoundError:
    data = {}
except Exception:
    raise SystemExit(1)
picked = data.get("pickedModels") if isinstance(data, dict) else None
value = picked.get(agent) if isinstance(picked, dict) else None
if not isinstance(value, list):
    value = []
sys.stdout.write(",".join(str(item) for item in value))
PYTHON
}

# Write every catalog agent's picked list into Magpie's settings. Other keys
# and other agents' picks are preserved; the file is replaced atomically at
# 0600. Magpie has no CLI for an individual pick, so this is the one write the
# deployment makes into Magpie's own store, and only for this key.
magpie_picked_write() {
    local settings python input index status
    settings=$(magpie_settings_file)
    python=$(magpie_python) || return 1
    input=$(mktemp "${TMPDIR:-/tmp}/magpie-picked.XXXXXX") || return 1
    {
        for (( index=0; index<${#MAGPIE_PICKED_AGENT[@]}; index++ )); do
            printf '%s|%s\n' "${MAGPIE_PICKED_AGENT[index]}" "${MAGPIE_PICKED_MODELS[index]}"
        done
    } > "$input" || { rm -f "$input"; return 1; }
    "$python" - "$settings" "$input" <<'PYTHON'
import json
import os
import sys
import tempfile

settings, incoming_path = sys.argv[1], sys.argv[2]
incoming = {}
with open(incoming_path, encoding="utf-8") as handle:
    for line in handle:
        line = line.rstrip("\n")
        if not line:
            continue
        agent, models = line.split("|", 1)
        incoming[agent] = [model for model in models.split(",") if model]
data = {}
try:
    with open(settings, encoding="utf-8") as handle:
        data = json.load(handle)
except FileNotFoundError:
    data = {}
except Exception:
    raise SystemExit(1)
if not isinstance(data, dict):
    raise SystemExit(1)
picked = data.get("pickedModels")
if not isinstance(picked, dict):
    picked = {}
picked.update(incoming)
data["pickedModels"] = picked
folder = os.path.dirname(settings)
os.makedirs(folder, mode=0o700, exist_ok=True)
descriptor, temporary = tempfile.mkstemp(prefix="settings.", suffix=".tmp", dir=folder)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"), ensure_ascii=False)
        handle.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, settings)
except BaseException:
    try:
        os.unlink(temporary)
    except OSError:
        pass
    raise
PYTHON
    status=$?
    rm -f "$input"
    return "$status"
}

# One variable of the device credential store. The store is parsed, never
# sourced, so a line in it cannot run a command.
magpie_env_value() {
    local name=$1 file line value=''
    file="$HOME/$MAGPIE_ENV_FILE"
    [ -f "$file" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in
            '#'*) continue ;;
            "$name="*) value=${line#*=} ;;
        esac
    done < "$file"
    [ -n "$value" ] || return 1
    case "$value" in
        \"*\") value=${value#\"}; value=${value%\"} ;;
        \'*\') value=${value#\'}; value=${value%\'} ;;
    esac
    [ -n "$value" ] || return 1
    printf '%s' "$value"
}

# The credential of one provider row, read from the store the catalog names.
# The value is used once, to add the provider, and never printed.
magpie_provider_credential() {
    local source=$1 rest key path
    case "$source" in
        env:*)
            magpie_env_value "${source#env:}"
            return $?
            ;;
        json:*)
            rest=${source#json:}
            key=${rest##*:}
            path=${rest%:*}
            magpie_json_value "$path" "$key"
            return $?
            ;;
    esac
    return 1
}

# Whether the deployment runs against the real account home. The engine also
# runs outside the deployment, so it resolves the account home itself.
magpie_real_account_home() {
    if command -v installer_real_account_home >/dev/null 2>&1; then
        installer_real_account_home
        return $?
    fi
    local account_home
    account_home=$(magpie_account_home) || return 1
    [ -n "$account_home" ] && [ "$HOME" = "$account_home" ]
}

# The home directory of the current account.
magpie_account_home() {
    case "$(uname -s)" in
        Darwin)
            /usr/bin/dscl . -read "/Users/$(/usr/bin/id -un)" NFSHomeDirectory 2>/dev/null |
                /usr/bin/awk '{print $2}'
            ;;
        *)
            getent passwd "$(id -u)" 2>/dev/null | awk -F: '{print $6}'
            ;;
    esac
}

# The provider catalog: role, Magpie provider, key source, required.
magpie_catalog_providers() {
    local file=$1 line role preset source required
    local variable rest path key
    MAGPIE_PROVIDER_ROLE=(); MAGPIE_PROVIDER_PRESET=(); MAGPIE_PROVIDER_SOURCE=(); MAGPIE_PROVIDER_REQUIRED=()
    MAGPIE_PROVIDER_ROLES=''
    MAGPIE_PROVIDER_PRESET_ROWS=''
    MAGPIE_PROVIDER_PRESET_IDS=''
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
            plugin-account) ;;
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
        MAGPIE_PROVIDER_ROLE+=("$role"); MAGPIE_PROVIDER_PRESET+=("$preset")
        MAGPIE_PROVIDER_SOURCE+=("$source"); MAGPIE_PROVIDER_REQUIRED+=("$required")
        MAGPIE_PROVIDER_ROLES="$MAGPIE_PROVIDER_ROLES|$role|"
        MAGPIE_PROVIDER_PRESET_ROWS="$MAGPIE_PROVIDER_PRESET_ROWS|$role=$preset|"
        MAGPIE_PROVIDER_PRESET_IDS="$MAGPIE_PROVIDER_PRESET_IDS|$preset|"
    done < "$file"
    return 0
}

# The model catalog: role, ordered candidate ids, required.
magpie_catalog_models() {
    local file=$1 line role candidates required candidate id provider model
    local -a candidate_list
    MAGPIE_MODEL_ROLE=(); MAGPIE_MODEL_CANDIDATES=(); MAGPIE_MODEL_REQUIRED=()
    MAGPIE_MODEL_ROLES=''
    MAGPIE_MODEL_CANDIDATE_ROWS=''
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
        MAGPIE_MODEL_ROLE+=("$role"); MAGPIE_MODEL_CANDIDATES+=("$candidates"); MAGPIE_MODEL_REQUIRED+=("$required")
        MAGPIE_MODEL_ROLES="$MAGPIE_MODEL_ROLES|$role|"
        MAGPIE_MODEL_CANDIDATE_ROWS="$MAGPIE_MODEL_CANDIDATE_ROWS|$role=$candidates|"
    done < "$file"
    return 0
}

# Whether a group reaches a model role, directly or through a nested group.
# A group that only nests groups which nest nothing has no model role, and a
# cycle of group references reaches none either.
magpie_group_reaches_role() {
    local id=$1 depth=$2 members member member_role
    local -a member_list
    [ "$depth" -le 8 ] || return 1
    members=$(magpie_list_value "$MAGPIE_GROUP_MEMBERS" "$id") || return 1
    IFS=, read -r -a member_list <<< "$members"
    for member in "${member_list[@]}"; do
        magpie_member_split "$member" || return 1
        member_role=$MAGPIE_MEMBER_ROLE
        case "$member_role" in
            group/*) magpie_group_reaches_role "${member_role#group/}" $((depth + 1)) && return 0 ;;
            *) return 0 ;;
        esac
    done
    return 1
}

# The routing group catalog: id, members, routing, stays, listed, purpose.
magpie_catalog_groups() {
    local file=$1 line id members routing stays listed purpose member
    local -a member_list
    MAGPIE_GROUP_ID=(); MAGPIE_GROUP_MEMBER=(); MAGPIE_GROUP_ROUTING=(); MAGPIE_GROUP_STAYS=(); MAGPIE_GROUP_LISTED=()
    MAGPIE_GROUP_IDS=''
    MAGPIE_GROUP_MEMBERS=''
    MAGPIE_GROUP_ROUTING_ROWS=''
    MAGPIE_GROUP_STAYS_ROWS=''
    MAGPIE_GROUP_LISTED_ROWS=''
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
            magpie_member_split "$member" || return 1
            magpie_name_ok "${MAGPIE_MEMBER_ROLE#group/}" || { magpie_fail "invalid group member: $member"; return 1; }
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
        MAGPIE_GROUP_ID+=("$id"); MAGPIE_GROUP_MEMBER+=("$members")
        MAGPIE_GROUP_ROUTING+=("$routing"); MAGPIE_GROUP_STAYS+=("$stays"); MAGPIE_GROUP_LISTED+=("$listed")
        MAGPIE_GROUP_IDS="$MAGPIE_GROUP_IDS|$id|"
        MAGPIE_GROUP_MEMBERS="$MAGPIE_GROUP_MEMBERS|$id=$members|"
        MAGPIE_GROUP_ROUTING_ROWS="$MAGPIE_GROUP_ROUTING_ROWS|$id=$routing|"
        MAGPIE_GROUP_STAYS_ROWS="$MAGPIE_GROUP_STAYS_ROWS|$id=$stays|"
        MAGPIE_GROUP_LISTED_ROWS="$MAGPIE_GROUP_LISTED_ROWS|$id=$listed|"
    done < "$file"
    return 0
}

# The plugin catalog: name, npm package, pinned version, enabled.
magpie_catalog_plugins() {
    local file=$1 line name source version enabled
    MAGPIE_PLUGIN_NAME=(); MAGPIE_PLUGIN_SOURCE=(); MAGPIE_PLUGIN_VERSION=(); MAGPIE_PLUGIN_ENABLED=()
    MAGPIE_PLUGIN_NAMES=''
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        magpie_row_fields "$line" 4 plugin || return 1
        name=${MAGPIE_ROW_FIELDS[0]}; source=${MAGPIE_ROW_FIELDS[1]}
        version=${MAGPIE_ROW_FIELDS[2]}; enabled=${MAGPIE_ROW_FIELDS[3]}
        magpie_name_ok "$name" || { magpie_fail "invalid plugin name: $name"; return 1; }
        if magpie_list_contains "$MAGPIE_PLUGIN_NAMES" "$name"; then
            magpie_fail "duplicate plugin name: $name"
            return 1
        fi
        case "$source" in
            ''|*[!A-Za-z0-9._@/-]*) magpie_fail "invalid plugin source: $source"; return 1 ;;
        esac
        case "$source" in
            @*/?*) ;;
            @*) magpie_fail "invalid plugin source: $source"; return 1 ;;
            */?*) ;;
            */*) magpie_fail "invalid plugin source: $source"; return 1 ;;
        esac
        case "$version" in
            ''|*[!0-9.]*|.*|*.|*..*) magpie_fail "invalid plugin version: $version"; return 1 ;;
        esac
        case "$enabled" in
            yes|no) ;;
            *) magpie_fail "invalid plugin enabled flag: $enabled"; return 1 ;;
        esac
        MAGPIE_PLUGIN_NAME+=("$name"); MAGPIE_PLUGIN_SOURCE+=("$source")
        MAGPIE_PLUGIN_VERSION+=("$version"); MAGPIE_PLUGIN_ENABLED+=("$enabled")
        MAGPIE_PLUGIN_NAMES="$MAGPIE_PLUGIN_NAMES|$name|"
    done < "$file"
    return 0
}

# The agent visibility catalog: agent, names the agent is shown.
magpie_catalog_visible() {
    local file=$1 line agent names name
    local -a name_list
    MAGPIE_VISIBLE_AGENT=(); MAGPIE_VISIBLE_NAMES=()
    MAGPIE_VISIBLE_AGENTS=''
    MAGPIE_VISIBLE_ROWS=''
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        magpie_row_fields "$line" 2 visible || return 1
        agent=${MAGPIE_ROW_FIELDS[0]}; names=${MAGPIE_ROW_FIELDS[1]}
        magpie_name_ok "$agent" || { magpie_fail "invalid visible agent: $agent"; return 1; }
        if magpie_list_contains "$MAGPIE_VISIBLE_AGENTS" "$agent"; then
            magpie_fail "duplicate visible agent: $agent"
            return 1
        fi
        IFS=, read -r -a name_list <<< "$names"
        [ "${#name_list[@]}" -gt 0 ] || { magpie_fail "visible agent has no name: $agent"; return 1; }
        for name in "${name_list[@]}"; do
            magpie_name_ok "$name" || { magpie_fail "invalid visible name: $name"; return 1; }
        done
        MAGPIE_VISIBLE_AGENT+=("$agent"); MAGPIE_VISIBLE_NAMES+=("$names")
        MAGPIE_VISIBLE_AGENTS="$MAGPIE_VISIBLE_AGENTS|$agent|"
        MAGPIE_VISIBLE_ROWS="$MAGPIE_VISIBLE_ROWS|$agent=$names|"
    done < "$file"
    return 0
}

# The per-agent picked model catalog: agent, entries. A group entry is
# group/<id>; a model entry is provider/model.
magpie_catalog_picked() {
    local file=$1 line agent entries entry provider model
    local -a entry_list
    MAGPIE_PICKED_AGENT=(); MAGPIE_PICKED_MODELS=()
    MAGPIE_PICKED_AGENTS=''
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        magpie_row_fields "$line" 2 picked || return 1
        agent=${MAGPIE_ROW_FIELDS[0]}; entries=${MAGPIE_ROW_FIELDS[1]}
        magpie_name_ok "$agent" || { magpie_fail "invalid picked agent: $agent"; return 1; }
        if magpie_list_contains "$MAGPIE_PICKED_AGENTS" "$agent"; then
            magpie_fail "duplicate picked agent: $agent"
            return 1
        fi
        IFS=, read -r -a entry_list <<< "$entries"
        [ "${#entry_list[@]}" -gt 0 ] || { magpie_fail "picked agent has no entry: $agent"; return 1; }
        for entry in "${entry_list[@]}"; do
            case "$entry" in
                group/*)
                    magpie_name_ok "${entry#group/}" ||
                        { magpie_fail "invalid picked group: $entry"; return 1; } ;;
                */*)
                    provider=${entry%%/*}; model=${entry#*/}
                    magpie_name_ok "$provider" ||
                        { magpie_fail "invalid picked provider: $entry"; return 1; }
                    case "$model" in
                        ''|*[!A-Za-z0-9._:/-]*) magpie_fail "invalid picked model: $entry"; return 1 ;;
                    esac ;;
                *)
                    magpie_fail "picked entry is not group/<id> or provider/model: $entry"
                    return 1 ;;
            esac
        done
        MAGPIE_PICKED_AGENT+=("$agent"); MAGPIE_PICKED_MODELS+=("$entries")
        MAGPIE_PICKED_AGENTS="$MAGPIE_PICKED_AGENTS|$agent|"
    done < "$file"
    return 0
}

# The agent wiring catalog: agent, group, owner, enabled.
magpie_catalog_wiring() {
    local file=$1 line agent group owner enabled
    MAGPIE_WIRING_AGENT=(); MAGPIE_WIRING_GROUP=(); MAGPIE_WIRING_OWNER=(); MAGPIE_WIRING_ENABLED=()
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
        MAGPIE_WIRING_AGENT+=("$agent"); MAGPIE_WIRING_GROUP+=("$group")
        MAGPIE_WIRING_OWNER+=("$owner"); MAGPIE_WIRING_ENABLED+=("$enabled")
        MAGPIE_WIRING_ROWS="$MAGPIE_WIRING_ROWS|$agent=$group=$owner=$enabled|"
    done < "$file"
    return 0
}

# Validate the catalogs against each other. A bad catalog is rejected by
# name before the deployment writes a file.
magpie_catalog_validate() {
    local dir=${1:-}
    [ -n "$dir" ] || dir=$(magpie_catalog_dir)
    local providers="$dir/providers.tsv" models="$dir/models.tsv"
    local groups="$dir/groups.tsv" wiring="$dir/wiring.tsv" visible="$dir/visible.tsv"
    local plugins="$dir/plugins.tsv" picked="$dir/picked.tsv"
    local file line member role candidates candidate id provider agent names name
    local member_list_text entry
    local -a candidate_list member_list name_list entry_list
    for file in "$providers" "$models" "$groups" "$wiring" "$visible" "$plugins" "$picked"; do
        [ -f "$file" ] || { magpie_fail "catalog is missing: ${file##*/}"; return 1; }
        [ ! -L "$file" ] || { magpie_fail "catalog is a symlink: ${file##*/}"; return 1; }
    done
    # No catalog value carries a credential. The scan runs before the shape
    # checks, so a pasted key is reported as a credential.
    for file in "$providers" "$models" "$groups" "$wiring" "$visible" "$plugins" "$picked"; do
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
    magpie_catalog_visible "$visible" || return 1
    magpie_catalog_picked "$picked" || return 1
    magpie_catalog_plugins "$plugins" || return 1
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
    # Every group member exists, and every group reaches a model role.
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$line"
        id=${MAGPIE_ROW_FIELDS[0]}; member_list_text=${MAGPIE_ROW_FIELDS[1]}
        IFS=, read -r -a member_list <<< "$member_list_text"
        for member in "${member_list[@]}"; do
            magpie_member_split "$member" || return 1
            case "$MAGPIE_MEMBER_ROLE" in
                group/*)
                    if [ "${MAGPIE_MEMBER_ROLE#group/}" = "$id" ]; then
                        magpie_fail "group $id references itself"
                        return 1
                    fi
                    if ! magpie_list_contains "$MAGPIE_GROUP_IDS" "${MAGPIE_MEMBER_ROLE#group/}"; then
                        magpie_fail "group $id names an undeclared group: ${MAGPIE_MEMBER_ROLE#group/}"
                        return 1
                    fi ;;
                *)
                    if ! magpie_list_contains "$MAGPIE_MODEL_ROLES" "$MAGPIE_MEMBER_ROLE"; then
                        magpie_fail "group $id names an unknown model role: $MAGPIE_MEMBER_ROLE"
                        return 1
                    fi ;;
            esac
        done
        if ! magpie_group_reaches_role "$id" 0; then
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
    # Every narrowed agent is a declared agent, and every name it is shown is a
    # declared group or Magpie provider.
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$line"
        agent=${MAGPIE_ROW_FIELDS[0]}; names=${MAGPIE_ROW_FIELDS[1]}
        if ! magpie_list_value "$MAGPIE_WIRING_ROWS" "$agent" >/dev/null; then
            magpie_fail "visible names an unknown agent: $agent"
            return 1
        fi
        IFS=, read -r -a name_list <<< "$names"
        for name in "${name_list[@]}"; do
            if magpie_list_contains "$MAGPIE_GROUP_IDS" "$name"; then continue; fi
            if magpie_list_contains "$MAGPIE_PROVIDER_PRESET_IDS" "$name"; then continue; fi
            magpie_fail "visible agent $agent names an unknown group or provider: $name"
            return 1
        done
    done < "$visible"
    # Every picked agent has a visible row, and every picked entry is a
    # declared group or provider inside that row.
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        IFS='|' read -r -a MAGPIE_ROW_FIELDS <<< "$line"
        agent=${MAGPIE_ROW_FIELDS[0]}; entries=${MAGPIE_ROW_FIELDS[1]}
        names=$(magpie_list_value "$MAGPIE_VISIBLE_ROWS" "$agent") ||
            { magpie_fail "picked names an agent with no visible row: $agent"; return 1; }
        IFS=, read -r -a entry_list <<< "$entries"
        for entry in "${entry_list[@]}"; do
            case "$entry" in
                group/*)
                    id=${entry#group/}
                    if ! magpie_list_contains "$MAGPIE_GROUP_IDS" "$id"; then
                        magpie_fail "picked group is not declared: $entry"
                        return 1
                    fi
                    if ! magpie_csv_contains "$names" "$id"; then
                        magpie_fail "picked group is not visible to $agent: $entry"
                        return 1
                    fi ;;
                *)
                    provider=${entry%%/*}
                    if ! magpie_list_contains "$MAGPIE_PROVIDER_PRESET_IDS" "$provider"; then
                        magpie_fail "picked model names an undeclared provider: $entry"
                        return 1
                    fi
                    if ! magpie_csv_contains "$names" "$provider"; then
                        magpie_fail "picked provider is not visible to $agent: $entry"
                        return 1
                    fi ;;
            esac
        done
    done < "$picked"
    return 0
}

# The gateway the deployment talks to, and whether it answers.
magpie_gateway_status() {
    MAGPIE_GATEWAY_JSON=$(magpie_run status --json 2>/dev/null) || return 1
    MAGPIE_GATEWAY=$(printf '%s' "$MAGPIE_GATEWAY_JSON" |
        sed -n 's/.*"gateway"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
    [ -n "$MAGPIE_GATEWAY" ] || MAGPIE_GATEWAY="$MAGPIE_GATEWAY_DEFAULT"
    return 0
}

# Ensure the gateway answers. The app owns the gateway, so the deployment
# opens it on the real account home and waits; elsewhere it reports the
# command and continues with a named warning.
magpie_gateway_ensure() {
    local attempt=0
    MAGPIE_GATEWAY_READY=no
    if magpie_gateway_status; then
        MAGPIE_GATEWAY_READY=yes
        printf 'dotfiles: magpie: the gateway answers on %s\n' "$MAGPIE_GATEWAY"
        return 0
    fi
    if magpie_real_account_home; then
        printf 'dotfiles: magpie: the gateway does not answer; opening the Magpie app\n'
        open -a magpie >/dev/null 2>&1 || true
        while [ "$attempt" -lt 30 ]; do
            sleep 1
            attempt=$((attempt + 1))
            if magpie_gateway_status; then
                MAGPIE_GATEWAY_READY=yes
                printf 'dotfiles: magpie: the gateway answers on %s\n' "$MAGPIE_GATEWAY"
                return 0
            fi
        done
        printf 'dotfiles: magpie: the gateway still does not answer; open the Magpie app and apply again\n' >&2
        return 1
    fi
    printf 'dotfiles: magpie: the gateway does not answer; open the Magpie app with: open -a magpie\n' >&2
    return 1
}

# The proxy endpoint the template names for this device.
magpie_template_proxy() {
    local config="${XDG_CONFIG_HOME:-$HOME/.config}/chezmoi/chezmoi.toml"
    [ -f "$config" ] || return 1
    sed -n 's/^[[:space:]]*proxyUrl[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$config" | head -n1
}

# The proxy endpoint the device resolves at call time.
magpie_with_proxy_url() {
    local helper="$HOME/.local/bin/with-proxy" url=''
    [ -x "$helper" ] || helper=$(command -v with-proxy 2>/dev/null || true)
    [ -n "$helper" ] || return 1
    url=$("$helper" --print-url 2>/dev/null) || return 1
    [ -n "$url" ] || return 1
    printf '%s' "$url"
}

# The proxy the deployment gives the gateway. The template's proxyUrl names
# the device's endpoint, but a local port belongs to whichever proxy client
# the device runs, so a loopback endpoint is resolved at call time through
# with-proxy, the way the shell helpers resolve it.
magpie_proxy_resolve() {
    local url='' template=''
    if [ -n "${MAGPIE_PROXY_URL:-}" ]; then
        printf '%s' "$MAGPIE_PROXY_URL"
        return 0
    fi
    template=$(magpie_template_proxy || true)
    case "$template" in
        http://127.0.0.1:*|http://localhost:*|https://127.0.0.1:*|https://localhost:*)
            url=$(magpie_with_proxy_url || true)
            [ -n "$url" ] || url=$template
            ;;
        *) url=$template ;;
    esac
    [ -n "$url" ] || url=$(magpie_with_proxy_url || true)
    [ -n "$url" ] || return 1
    printf '%s' "$url"
}

# Whether a version is at least a floor.
magpie_version_at_least() {
    local have=$1 want=$2
    [ -n "$have" ] || return 1
    awk -v have="$have" -v want="$want" 'BEGIN {
        sub(/_[0-9]+$/, "", have)
        sub(/_[0-9]+$/, "", want)
        if (have !~ /^[0-9]+(\.[0-9]+)*$/ || want !~ /^[0-9]+(\.[0-9]+)*$/) exit 1
        split(have, h, "."); split(want, w, ".")
        for (i = 1; i <= 3; i++) {
            if (h[i] + 0 > w[i] + 0) exit 0
            if (h[i] + 0 < w[i] + 0) exit 1
        }
        exit 0
    }'
}

# The version of the adopted cask, or nothing when the app is not installed.
magpie_cask_version() {
    local version='' root=${MAGPIE_APP_ROOT:-/Applications}
    if command -v brew >/dev/null 2>&1; then
        version=$(brew list --cask --versions "$MAGPIE_CASK_NAME" 2>/dev/null | awk '{print $2}')
        version=${version%%_*}
    fi
    if [ -z "$version" ] && [ -d "$root/${MAGPIE_CASK_NAME}.app" ]; then
        version=$(defaults read "$root/${MAGPIE_CASK_NAME}.app/Contents/Info.plist" \
            CFBundleShortVersionString 2>/dev/null || true)
    fi
    [ -n "$version" ] || return 1
    printf '%s' "$version"
}

# Report the adopted cask. A missing or old app is a warning: the gateway
# may still answer from an earlier install.
magpie_cask_report() {
    local version
    if ! version=$(magpie_cask_version); then
        printf 'dotfiles: magpie: the %s app is not installed; install it with: brew install --cask %s\n' \
            "$MAGPIE_CASK_NAME" "$MAGPIE_CASK_NAME" >&2
        return 1
    fi
    if ! magpie_version_at_least "$version" "$MAGPIE_CASK_FLOOR"; then
        printf 'dotfiles: magpie: the %s app is %s, below the floor %s\n' \
            "$MAGPIE_CASK_NAME" "$version" "$MAGPIE_CASK_FLOOR" >&2
        return 1
    fi
    printf 'dotfiles: magpie: the %s app %s is adopted\n' "$MAGPIE_CASK_NAME" "$version"
    return 0
}

# The proxy the gateway currently uses.
magpie_proxy_current() {
    magpie_run settings get proxy 2>/dev/null || true
}

# Whether Magpie knows one provider.
magpie_provider_present() {
    magpie_run provider "$1" >/dev/null 2>&1
}

# Whether Magpie knows a ChatGPT account for the Codex provider.
magpie_account_present() {
    local accounts
    accounts=$(magpie_run accounts codex --json 2>/dev/null) || return 1
    [ -n "$accounts" ] || return 1
    case "$accounts" in
        '[]'|'{}'|'') return 1 ;;
    esac
    return 0
}

# The package a plugin spec names: "pkg@1.2.3" and "@scope/pkg@1.2.3" both
# report the package without its version.
magpie_plugin_package() {
    local spec=$1 rest
    case "$spec" in
        @*/*)
            rest=${spec#@}
            case "$rest" in
                *@*) printf '@%s' "${rest%@*}" ;;
                *) printf '%s' "$spec" ;;
            esac ;;
        *@*) printf '%s' "${spec%@*}" ;;
        *) printf '%s' "$spec" ;;
    esac
}

# What Magpie reports for its plugins: one "loaded|<spec>" line for each
# plugin that is on, then one "plugins|<spec>" line for each installed one.
magpie_plugin_state() {
    local output python
    output=$(magpie_run plugin list --json 2>/dev/null) || return 1
    python=$(magpie_python) || return 1
    printf '%s' "$output" | "$python" -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
# Magpie 0.1.4351 returns [] before a fresh home has any plugins.
if data == []:
    raise SystemExit(0)
if not isinstance(data, dict):
    raise SystemExit(1)
for key in ("loaded", "plugins"):
    for entry in data.get(key) or []:
        spec = entry.get("spec") if isinstance(entry, dict) else None
        if spec:
            print(key + "|" + spec)
'
}

# The state of one plugin package in that list: loaded, plugins, or nothing.
magpie_plugin_state_of() {
    local specs=$1 package=$2 line
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        [ "$(magpie_plugin_package "${line#*|}")" = "$package" ] || continue
        printf '%s' "${line%%|*}"
        return 0
    done <<< "$specs"
    return 0
}

# The models the gateway serves.
magpie_models_fetch() {
    local gateway=$1
    command -v curl >/dev/null 2>&1 || return 1
    curl --noproxy '*' --fail --silent --show-error --connect-timeout 5 --max-time 20 \
        -H 'Authorization: Bearer magpie' "$gateway/v1/models" 2>/dev/null
}

# The model ids of a gateway answer.
magpie_model_ids() {
    printf '%s' "$1" | tr ',' '\n' |
        sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

# Whether Magpie knows one group.
magpie_group_present() {
    magpie_run group "$1" >/dev/null 2>&1
}

# A comma list normalized for comparison: no spaces, sorted.
magpie_names_sorted() {
    printf '%s' "$1" | tr ',' '\n' | sed '/^$/d' | sort | paste -sd, -
}

# The names one agent is narrowed to, as `magpie visible <agent>` reports
# them, comma-joined and space-free. An agent shown every model prints
# nothing.
magpie_visible_names() {
    local agent=$1 output line names
    output=$(magpie_run visible "$agent" 2>/dev/null) || return 1
    while IFS= read -r line; do
        case "$line" in
            *" is shown "*)
                names=${line#* is shown }
                # The only-picked banner is not the visibility list; the
                # names line follows it.
                case "$names" in
                    "only the models picked"*) continue ;;
                esac
                printf '%s' "${names// /}"
                return 0 ;;
        esac
    done <<< "$output"
    return 0
}

# The models a group holds, in the order the gateway reports them. The
# catalog knows every model id, so the report is read by looking for them.
# The member ids of a group as `magpie group <id>` lists them: the token after
# the first bare number on each member line. Magpie puts the first member on
# the `models` line and the rest on continuation lines. A nested group stays
# group/<id>.
magpie_group_models() {
    printf '%s\n' "$1" | awk '
        /^[[:space:]]*(models[[:space:]]+)?[0-9]+[[:space:]]/ {
            for (i = 1; i <= NF; i++) {
                if ($i ~ /^[0-9]+$/) { print $(i + 1); break }
            }
        }' | paste -sd, -
}

# The candidates of one model role whose provider the gateway knows.
magpie_role_servable() {
    local candidates=$1 ready=$2 candidate id provider servable=''
    local -a candidate_list
    IFS=, read -r -a candidate_list <<< "$candidates"
    for candidate in "${candidate_list[@]}"; do
        id=$candidate
        case "$candidate" in
            *'?'*) id=${candidate%?} ;;
        esac
        provider=${id%%/*}
        magpie_list_contains "$ready" "$provider" || continue
        servable="$servable$id,"
    done
    printf '%s' "${servable%,}"
}

# The live models that satisfy one model role, in candidate order. A
# candidate is served only when the gateway knows its provider.
magpie_role_models() {
    local role=$1 candidates=$2 live=$3 ready=$4 candidate id bare provider matched=''
    local -a candidate_list
    IFS=, read -r -a candidate_list <<< "$candidates"
    for candidate in "${candidate_list[@]}"; do
        id=$candidate
        case "$candidate" in
            *'?'*) id=${candidate%?} ;;
        esac
        bare=${id#*/}
        provider=${id%%/*}
        magpie_list_contains "$ready" "$provider" || continue
        if magpie_list_contains "$live" "$id" || magpie_list_contains "$live" "$bare"; then
            matched="$matched$id,"
        fi
    done
    printf '%s' "${matched%,}"
}

# The models one group holds, in order. A member is a model role, a model
# role with a pinned reasoning effort, or another group. A group with an
# unresolved member is incomplete.
magpie_group_models_for() {
    local id=$1 depth=${2:-0} members member part models='' status
    local member_role member_effort
    local -a member_list
    [ "$depth" -le 8 ] || return 1
    members=$(magpie_list_value "$MAGPIE_GROUP_MEMBERS" "$id") || return 1
    IFS=, read -r -a member_list <<< "$members"
    for member in "${member_list[@]}"; do
        magpie_member_split "$member" || return 1
        member_role=$MAGPIE_MEMBER_ROLE
        member_effort=$MAGPIE_MEMBER_EFFORT
        case "$member_role" in
            group/*)
                # Keep the reference: Magpie treats the group as one member
                # with its own routing and listed setting. Resolve it first so
                # a reference to a group whose members are unavailable fails.
                magpie_group_models_for "${member_role#group/}" $((depth + 1)) >/dev/null || return 1
                part=$member_role
                ;;
            *)
                status=$(magpie_list_value "$MAGPIE_ROLE_STATUS" "$member_role") || return 1
                [ "$status" = resolved ] || return 1
                part=$(magpie_list_value "$MAGPIE_ROLE_MODELS" "$member_role") || return 1
                if [ -n "$member_effort" ]; then
                    part=$(printf '%s' "$part" | tr ',' '\n' |
                        sed "s/\$/:$member_effort/" | paste -sd, -)
                fi
                ;;
        esac
        [ -n "$part" ] || return 1
        models="$models$part,"
    done
    printf '%s' "${models%,}"
}

# The groups that are in use: the ones an enabled agent selects and the ones
# an agent's picker lists.
magpie_enabled_groups() {
    local index agent group enabled=''
    for (( index=0; index<${#MAGPIE_WIRING_AGENT[@]}; index++ )); do
        [ "${MAGPIE_WIRING_ENABLED[index]}" = yes ] || continue
        group=${MAGPIE_WIRING_GROUP[index]}
        [ "$group" = '-' ] && continue
        enabled="$enabled|${group#group/}|"
    done
    for (( index=0; index<${#MAGPIE_GROUP_ID[@]}; index++ )); do
        if [ "${MAGPIE_GROUP_LISTED[index]}" = yes ]; then
            enabled="$enabled|${MAGPIE_GROUP_ID[index]}|"
        fi
    done
    printf '%s' "$enabled"
}

# The provider presets the enabled groups use. A provider outside this list
# may be missing without failing the apply.
magpie_enabled_providers() {
    local index group used='' groups
    groups=$(magpie_enabled_groups)
    for (( index=0; index<${#MAGPIE_GROUP_ID[@]}; index++ )); do
        group=${MAGPIE_GROUP_ID[index]}
        magpie_list_contains "$groups" "$group" || continue
        used="$used$(magpie_group_providers "$group" 0)"
    done
    printf '%s' "$used"
}

# The provider presets one group uses, including the groups it holds.
magpie_group_providers() {
    local id=$1 depth=$2 members member role candidates provider used=''
    local member_role
    local -a member_list MAGPIE_LOCAL_CANDIDATES
    [ "$depth" -le 8 ] || return ''
    members=$(magpie_list_value "$MAGPIE_GROUP_MEMBERS" "$id") || return ''
    IFS=, read -r -a member_list <<< "$members"
    for member in "${member_list[@]}"; do
        magpie_member_split "$member" || continue
        member_role=$MAGPIE_MEMBER_ROLE
        case "$member_role" in
            group/*)
                used="$used$(magpie_group_providers "${member_role#group/}" $((depth + 1)))"
                ;;
            *)
                role=$member_role
                candidates=$(magpie_list_value "$MAGPIE_MODEL_CANDIDATE_ROWS" "$role") || continue
                IFS=, read -r -a MAGPIE_LOCAL_CANDIDATES <<< "$candidates"
                for candidate in "${MAGPIE_LOCAL_CANDIDATES[@]}"; do
                    provider=${candidate%%/*}
                    provider=${provider%%\?*}
                    used="$used|$provider|"
                done ;;
        esac
    done
    printf '%s' "$used"
}

# The key source of one provider role.
magpie_provider_source() {
    local role=$1 index
    for (( index=0; index<${#MAGPIE_PROVIDER_ROLE[@]}; index++ )); do
        if [ "${MAGPIE_PROVIDER_ROLE[index]}" = "$role" ]; then
            printf '%s' "${MAGPIE_PROVIDER_SOURCE[index]}"
            return 0
        fi
    done
    return 1
}

# The timestamp of one backup directory.
magpie_backup_stamp() {
    date -u +%Y%m%dT%H%M%SZ
}

# Copy the client files Magpie may touch into a timestamped backup.
magpie_backup_create() (
    local stamp=$1 root file rel profile count=0 name
    root="$(magpie_state_dir)/backups/$stamp"
    [ ! -L "$root" ] || { magpie_fail "the Magpie backup directory is a symlink: $root"; return 1; }
    mkdir -p "$root" || { magpie_fail "cannot create the Magpie backup directory: $root"; return 1; }
    chmod 700 "$root"
    # Keep each file's path below the home: Claude's and Pi's settings.json
    # share a basename, and one must never overwrite the other.
    for file in "$HOME/.claude/settings.json" "$HOME/.pi/agent/settings.json" \
        "$HOME/.pi/agent/models.json" "$HOME/.codex/config.toml"; do
        [ -f "$file" ] || continue
        rel=${file#"$HOME/"}
        mkdir -p "$root/$(dirname "$rel")"
        cp -p "$file" "$root/$rel" || { magpie_fail "cannot back up $file"; return 1; }
    done
    for file in "$HOME"/.dsh/profiles/*/cordis.patch.yml; do
        [ -f "$file" ] || continue
        profile=$(basename "$(dirname "$file")")
        mkdir -p "$root/dsh-$profile"
        cp -p "$file" "$root/dsh-$profile/cordis.patch.yml" || { magpie_fail "cannot back up $file"; return 1; }
    done
    find "$root" -type f -exec chmod 600 {} +
    # Keep the newest backups only.
    for name in $(ls -1 "$(magpie_state_dir)/backups" 2>/dev/null | sort -r); do
        count=$((count + 1))
        case "$name" in
            [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) ;;
            *) continue ;;
        esac
        if [ "$count" -gt "$MAGPIE_BACKUP_KEEP" ]; then
            rm -rf "$(magpie_state_dir)/backups/$name"
        fi
    done
    printf '%s' "$root"
)

# The official DeepSeek row of one DSH profile patch. The patch is a YAML
# list of entries; the row is the entry whose id is llm-deepseek. The
# deployment reads it and never writes it.
magpie_dsh_official_row() {
    local file=$1
    [ -f "$file" ] || return 1
    awk '
        /^- id: / {
            if (capture) { exit }
            capture = ($0 ~ /^- id: "?llm-deepseek"?$/)
        }
        capture { print }
    ' "$file"
}

# The official DeepSeek row must survive the wiring. Magpie adds its own
# route; the official row keeps its own settings, so the DeepSeek entry in
# DSH's Models page still switches back.
magpie_dsh_verify_official_row() {
    local backup=$1 file profile before after
    for file in "$HOME"/.dsh/profiles/*/cordis.patch.yml; do
        [ -f "$file" ] || continue
        profile=$(basename "$(dirname "$file")")
        [ -f "$backup/dsh-$profile/cordis.patch.yml" ] || continue
        before=$(magpie_dsh_official_row "$backup/dsh-$profile/cordis.patch.yml" || true)
        after=$(magpie_dsh_official_row "$file" || true)
        if [ "$before" != "$after" ]; then
            magpie_fail "the official DeepSeek row of the DSH profile $profile changed during the apply"
            return 1
        fi
    done
    return 0
}

# The state of the official DeepSeek row of every DSH profile, read only.
magpie_dsh_official_state() {
    local file profile before after state
    for file in "$HOME"/.dsh/profiles/*/cordis.patch.yml; do
        [ -f "$file" ] || continue
        profile=$(basename "$(dirname "$file")")
        before=$(magpie_dsh_official_row "$file" || true)
        [ -n "$before" ] || { printf 'dsh-official-row|%s|absent\n' "$profile"; continue; }
        state=present
        for candidate in "$(magpie_state_dir)"/backups/*/dsh-$profile/cordis.patch.yml; do
            [ -f "$candidate" ] || continue
            after=$(magpie_dsh_official_row "$candidate" || true)
            if [ "$before" != "$after" ]; then state=changed; fi
        done
        printf 'dsh-official-row|%s|%s\n' "$profile" "$state"
    done
}

# The state the apply records: the providers, the groups with their model
# order, the wiring, the proxy, and the guard result.
magpie_state_content() {
    local guard=$1 index role group agent provider
    {
        printf '# Magpie apply state. The deployment owns this file.\n'
        printf '# kind|key|value\n'
        for (( index=0; index<${#MAGPIE_PROVIDER_ROLE[@]}; index++ )); do
            role=${MAGPIE_PROVIDER_ROLE[index]}
            provider=${MAGPIE_PROVIDER_PRESET[index]}
            if magpie_list_contains "$MAGPIE_PROVIDER_PRESENT" "$provider"; then
                printf 'provider|%s|present\n' "$role"
            else
                printf 'provider|%s|missing\n' "$role"
            fi
        done
        for (( index=0; index<${#MAGPIE_GROUP_ID[@]}; index++ )); do
            group=${MAGPIE_GROUP_ID[index]}
            printf 'group|%s|%s\n' "$group" "$(magpie_list_value "$MAGPIE_GROUP_MODELS" "$group")"
        done
        for (( index=0; index<${#MAGPIE_WIRING_AGENT[@]}; index++ )); do
            agent=${MAGPIE_WIRING_AGENT[index]}
            printf 'wiring|%s|%s\n' "$agent" "${MAGPIE_WIRING_GROUP[index]}"
        done
        printf 'proxy|current|%s\n' "$MAGPIE_PROXY"
        printf 'codex-guard|%s\n' "$guard"
    }
}

# Whether the recorded state already describes the desired state.
magpie_state_current() {
    local recorded=$1 desired=$2 left right
    [ -f "$recorded" ] || return 1
    left=$(grep -v '^applied|' "$recorded" 2>/dev/null || true)
    right=$(printf '%s\n' "$desired" | grep -v '^applied|' 2>/dev/null || true)
    [ "$left" = "$right" ]
}

# The wiring the recorded state holds for one agent.
magpie_recorded_wiring() {
    local state=$1 agent=$2 line
    [ -f "$state" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            "wiring|$agent|"*) printf '%s' "${line#wiring|$agent|}"; return 0 ;;
        esac
    done < "$state"
    return 1
}

# Write the state file through a temporary file.
magpie_state_write() {
    local content=$1 state staged
    state="$(magpie_state_dir)/state.tsv"
    [ ! -L "$(magpie_state_dir)" ] || { magpie_fail 'the Magpie state directory is a symlink'; return 1; }
    mkdir -p "$(magpie_state_dir)" || { magpie_fail 'cannot create the Magpie state directory'; return 1; }
    [ ! -L "$state" ] || { magpie_fail 'the Magpie state file is a symlink'; return 1; }
    staged=$(mktemp "$state.XXXXXX") || { magpie_fail 'cannot stage the Magpie state file'; return 1; }
    {
        printf '%s\n' "$content"
        printf 'applied|%s\n' "$(magpie_backup_stamp)"
    } > "$staged"
    chmod 600 "$staged"
    mv -f "$staged" "$state"
}

# Apply the catalogs to the gateway. The deployment owns the intent; Magpie
# owns the credentials and the generated files.
magpie_apply() {
    local platform dir index role preset source required group agent owner enabled
    local credential output live known current desired change='' entry used rest variable servable
    local fatal='' missing='' guard='unchanged' backup='' codex_before codex_after forced
    local id recorded names name version plugin_state state
    local -a candidate_list
    platform=$(magpie_platform)
    if [ "$platform" != macos ]; then
        printf 'dotfiles: magpie: Magpie is not available on this platform; skipped\n'
        return 0
    fi
    dir=$(magpie_catalog_dir)
    DEPLOY_STEP=magpie-apply.catalog
    magpie_catalog_validate "$dir" || return 1
    printf 'dotfiles: magpie: %s provider(s), %s model role(s), %s group(s), %s agent(s) declared\n' \
        "${#MAGPIE_PROVIDER_ROLE[@]}" "${#MAGPIE_MODEL_ROLE[@]}" \
        "${#MAGPIE_GROUP_ID[@]}" "${#MAGPIE_WIRING_AGENT[@]}"

    DEPLOY_STEP=magpie-apply.cask
    magpie_cask_report || true

    DEPLOY_STEP=magpie-apply.gateway
    # The gateway is the step's subject. A host that cannot run Magpie is
    # skipped by the platform guard above; a Mac that is missing the app, or
    # has not opened it once, fails here with the command that fixes it, so a
    # deployment can never leave agents wired to a gateway that is not there.
    if ! magpie_gateway_ensure; then
        magpie_fail 'the Magpie gateway does not answer; install or open the app and apply again'
        return 1
    fi

    DEPLOY_STEP=magpie-apply.proxy
    MAGPIE_PROXY=$(magpie_proxy_resolve || true)
    [ -n "$MAGPIE_PROXY" ] || { magpie_fail 'cannot resolve the proxy endpoint for the Magpie providers'; return 1; }
    MAGPIE_PROXY_CURRENT=$(magpie_proxy_current)
    if [ "$MAGPIE_PROXY_CURRENT" != "$MAGPIE_PROXY" ]; then
        change="$change
proxy"
    fi
    printf 'dotfiles: magpie: the providers use the proxy %s\n' "$MAGPIE_PROXY"

    DEPLOY_STEP=magpie-apply.plugins
    # An unreadable plugin list is not an absent plugin: the deployment never
    # installs on a guess.
    if ! plugin_state=$(magpie_plugin_state); then
        magpie_fail 'cannot read the Magpie plugin list'
        return 1
    fi
    for (( index=0; index<${#MAGPIE_PLUGIN_NAME[@]}; index++ )); do
        name=${MAGPIE_PLUGIN_NAME[index]}; source=${MAGPIE_PLUGIN_SOURCE[index]}
        version=${MAGPIE_PLUGIN_VERSION[index]}; enabled=${MAGPIE_PLUGIN_ENABLED[index]}
        state=$(magpie_plugin_state_of "$plugin_state" "$source")
        if [ "$state" = loaded ]; then
            printf 'dotfiles: magpie: the plugin %s is loaded\n' "$name"
            continue
        fi
        if [ "$enabled" != yes ]; then
            printf 'dotfiles: magpie: the plugin %s is parked\n' "$name"
            continue
        fi
        if [ "$state" = plugins ]; then
            change="$change
plugin-on:$name"
            printf 'dotfiles: magpie: the plugin %s will be turned on\n' "$name"
        else
            change="$change
plugin-add:$name"
            printf 'dotfiles: magpie: the plugin %s will be installed as npm:%s@%s\n' "$name" "$source" "$version"
        fi
    done

    DEPLOY_STEP=magpie-apply.providers
    MAGPIE_PROVIDER_PRESENT=''
    MAGPIE_PROVIDER_READY=''
    for (( index=0; index<${#MAGPIE_PROVIDER_ROLE[@]}; index++ )); do
        role=${MAGPIE_PROVIDER_ROLE[index]}; preset=${MAGPIE_PROVIDER_PRESET[index]}
        source=${MAGPIE_PROVIDER_SOURCE[index]}; required=${MAGPIE_PROVIDER_REQUIRED[index]}
        if magpie_provider_present "$preset"; then
            MAGPIE_PROVIDER_PRESENT="$MAGPIE_PROVIDER_PRESENT|$preset|"
            MAGPIE_PROVIDER_READY="$MAGPIE_PROVIDER_READY|$preset|"
            printf 'dotfiles: magpie: the provider %s is present\n' "$role"
            continue
        fi
        if [ "$source" = codex-account ]; then
            if magpie_account_present; then
                MAGPIE_PROVIDER_READY="$MAGPIE_PROVIDER_READY|$preset|"
                change="$change
provider:$role"
                printf 'dotfiles: magpie: the provider %s will be added from the ChatGPT account\n' "$role"
                continue
            fi
            missing="$missing
$role|$preset|$required|codex-account|none"
            continue
        fi
        credential=$(magpie_provider_credential "$source" || true)
        if [ -z "$credential" ]; then
            case "$source" in
                env:*) variable=${source#env:} ;;
                json:*)
                    rest=${source#json:}
                    variable=${rest##*:}
                    source="json:${rest%:*}"
                    ;;
                *) variable=none ;;
            esac
            missing="$missing
$role|$preset|$required|$source|$variable"
            continue
        fi
        MAGPIE_PROVIDER_READY="$MAGPIE_PROVIDER_READY|$preset|"
        change="$change
provider:$role"
        printf 'dotfiles: magpie: the provider %s will be added from %s\n' "$role" "$source"
    done
    if [ -n "$missing" ]; then
        used=$(magpie_enabled_providers)
        while IFS= read -r entry; do
            [ -n "$entry" ] || continue
            role=${entry%%|*}
            rest=${entry#*|}
            preset=${rest%%|*}
            rest=${rest#*|}
            required=${rest%%|*}
            rest=${rest#*|}
            source=${rest%%|*}
            variable=${rest#*|}
            if [ "$required" = yes ] && magpie_list_contains "$used" "$preset"; then
                fatal="$fatal
$role (source: $source; variable: $variable)"
            else
                printf 'dotfiles: magpie: the provider %s has no credential; source %s\n' "$role" "$source"
            fi
        done <<< "$missing"
    fi

    DEPLOY_STEP=magpie-apply.models
    output=$(magpie_models_fetch "$MAGPIE_GATEWAY" || true)
    if [ -z "$output" ]; then
        magpie_fail "cannot read the model list from $MAGPIE_GATEWAY/v1/models"
        return 1
    fi
    live=''
    for id in $(magpie_model_ids "$output"); do
        live="$live|$id|"
    done
    known=$(printf '%s' "$live" | tr '|' '\n' | sed '/^$/d' | tr '\n' ' ')
    MAGPIE_ROLE_MODELS=''
    MAGPIE_ROLE_STATUS=''
    for (( index=0; index<${#MAGPIE_MODEL_ROLE[@]}; index++ )); do
        role=${MAGPIE_MODEL_ROLE[index]}
        candidates=${MAGPIE_MODEL_CANDIDATES[index]}
        required=${MAGPIE_MODEL_REQUIRED[index]}
        servable=$(magpie_role_servable "$candidates" "$MAGPIE_PROVIDER_READY")
        if [ -z "$servable" ]; then
            printf 'dotfiles: magpie: the model role %s has no provider the gateway knows; skipped\n' "$role"
            MAGPIE_ROLE_STATUS="$MAGPIE_ROLE_STATUS|$role=unresolved|"
            continue
        fi
        current=$(magpie_role_models "$role" "$servable" "$live" "$MAGPIE_PROVIDER_READY")
        if [ -z "$current" ]; then
            if [ "$required" = yes ]; then
                magpie_fail "the model role $role has no model the gateway serves; the gateway serves: ${known// /, }"
                return 1
            fi
            printf 'dotfiles: magpie: the model role %s has no live model; skipped\n' "$role"
            MAGPIE_ROLE_STATUS="$MAGPIE_ROLE_STATUS|$role=unresolved|"
            continue
        fi
        IFS=, read -r -a candidate_list <<< "$candidates"
        for candidate in "${candidate_list[@]}"; do
            case "$candidate" in
                *'?'*)
                    id=${candidate%?}
                    if ! magpie_list_contains "$live" "$id"; then
                        printf 'dotfiles: magpie: the optional model %s is not served; skipped\n' "$id"
                    fi ;;
            esac
        done
        MAGPIE_ROLE_MODELS="$MAGPIE_ROLE_MODELS|$role=$current|"
        MAGPIE_ROLE_STATUS="$MAGPIE_ROLE_STATUS|$role=resolved|"
    done

    DEPLOY_STEP=magpie-apply.groups
    MAGPIE_GROUP_MODELS=''
    for (( index=0; index<${#MAGPIE_GROUP_ID[@]}; index++ )); do
        group=${MAGPIE_GROUP_ID[index]}
        desired=$(magpie_group_models_for "$group" || true)
        if [ -z "$desired" ]; then
            printf 'dotfiles: magpie: the group %s is incomplete; one of its members has no credential\n' "$group"
            MAGPIE_GROUP_MODELS="$MAGPIE_GROUP_MODELS|$group=|"
            continue
        fi
        MAGPIE_GROUP_MODELS="$MAGPIE_GROUP_MODELS|$group=$desired|"
        if magpie_group_present "$group"; then
            output=$(magpie_run group "$group" 2>/dev/null || true)
            current=$(magpie_group_models "$output" "$known")
            if [ "$current" != "$desired" ]; then
                change="$change
group-set:$group"
                printf 'dotfiles: magpie: the group %s will be set to %s\n' "$group" "$desired"
            else
                printf 'dotfiles: magpie: the group %s holds %s\n' "$group" "$desired"
            fi
        else
            change="$change
group-add:$group"
            printf 'dotfiles: magpie: the group %s will be created with %s\n' "$group" "$desired"
        fi
    done

    DEPLOY_STEP=magpie-apply.visible
    for (( index=0; index<${#MAGPIE_VISIBLE_AGENT[@]}; index++ )); do
        agent=${MAGPIE_VISIBLE_AGENT[index]}; desired=${MAGPIE_VISIBLE_NAMES[index]}
        current=$(magpie_visible_names "$agent" || true)
        if [ "$(magpie_names_sorted "$current")" = "$(magpie_names_sorted "$desired")" ]; then
            printf 'dotfiles: magpie: the agent %s is shown %s\n' "$agent" "$desired"
            continue
        fi
        change="$change
visible:$agent"
        printf 'dotfiles: magpie: the agent %s will be shown %s\n' "$agent" "$desired"
    done

    DEPLOY_STEP=magpie-apply.picked
    for (( index=0; index<${#MAGPIE_PICKED_AGENT[@]}; index++ )); do
        agent=${MAGPIE_PICKED_AGENT[index]}; desired=${MAGPIE_PICKED_MODELS[index]}
        current=$(magpie_picked_current "$agent") ||
            { magpie_fail "cannot read the picked models for $agent"; return 1; }
        if [ "$(magpie_names_sorted "$current")" = "$(magpie_names_sorted "$desired")" ]; then
            printf 'dotfiles: magpie: the agent %s picks %s\n' "$agent" "$desired"
            continue
        fi
        change="$change
picked:$agent"
        printf 'dotfiles: magpie: the agent %s will pick %s\n' "$agent" "$desired"
    done

    DEPLOY_STEP=magpie-apply.wiring
    for (( index=0; index<${#MAGPIE_WIRING_AGENT[@]}; index++ )); do
        agent=${MAGPIE_WIRING_AGENT[index]}; group=${MAGPIE_WIRING_GROUP[index]}
        owner=${MAGPIE_WIRING_OWNER[index]}; enabled=${MAGPIE_WIRING_ENABLED[index]}
        [ "$enabled" = yes ] || continue
        [ "$owner" = magpie ] || continue
        case "$agent" in
            codex)
                magpie_fail 'the deployment never wires Codex'
                return 1 ;;
            claude)
                magpie_fail 'the deployment writes the Claude Code settings itself'
                return 1 ;;
        esac
        recorded=$(magpie_recorded_wiring "$(magpie_state_dir)/state.tsv" "$agent" || true)
        # A visibility or picked change rewrites the agent's model list and
        # can reset its default; wire it again after the visible step.
        forced=no
        if printf '%s\n' "$change" | grep -qx "visible:$agent" ||
           printf '%s\n' "$change" | grep -qx "picked:$agent"; then
            forced=yes
        fi
        if [ "$recorded" = "$group" ] && [ "$forced" = no ]; then
            printf 'dotfiles: magpie: the agent %s is already wired to %s\n' "$agent" "$group"
            continue
        fi
        if ! printf '%s\n' "$change" | grep -qx "wiring:$agent:$group"; then
            change="$change
wiring:$agent:$group"
        fi
        printf 'dotfiles: magpie: the agent %s will be wired to %s\n' "$agent" "$group"
    done

    # The Codex configuration is never written by the deployment. Its digest is
    # taken before the changes and compared after them.
    codex_before=$(magpie_sha256 "$HOME/.codex/config.toml" || true)
    # A visibility- or pick-only run changes no client file, so it takes no
    # backup. The picked list is Magpie's own settings, rewritten atomically
    # for the pickedModels key alone.
    client_change=$(printf '%s\n' "$change" | grep -v '^visible:' | grep -v '^picked:' | grep -v '^$' || true)
    if [ -n "$change" ]; then
        if [ -n "$client_change" ]; then
            DEPLOY_STEP=magpie-apply.backup
            backup=$(magpie_backup_create "$(magpie_backup_stamp)") || return 1
            printf 'dotfiles: magpie: the client files are backed up in %s\n' "$backup"
        fi

        DEPLOY_STEP=magpie-apply.proxy
        if printf '%s\n' "$change" | grep -qx 'proxy'; then
            magpie_run settings set proxy "$MAGPIE_PROXY" >/dev/null ||
                { magpie_fail 'cannot set the Magpie proxy'; return 1; }
            printf 'dotfiles: magpie: the proxy was set to %s\n' "$MAGPIE_PROXY"
        fi

        DEPLOY_STEP=magpie-apply.plugins
        for (( index=0; index<${#MAGPIE_PLUGIN_NAME[@]}; index++ )); do
            name=${MAGPIE_PLUGIN_NAME[index]}
            if printf '%s\n' "$change" | grep -qx "plugin-add:$name"; then
                magpie_run plugin add "npm:${MAGPIE_PLUGIN_SOURCE[index]}@${MAGPIE_PLUGIN_VERSION[index]}" >/dev/null ||
                    { magpie_fail "cannot install the Magpie plugin $name"; return 1; }
                printf 'dotfiles: magpie: the plugin %s was installed\n' "$name"
            elif printf '%s\n' "$change" | grep -qx "plugin-on:$name"; then
                magpie_run plugin on "$name" >/dev/null ||
                    { magpie_fail "cannot turn on the Magpie plugin $name"; return 1; }
                printf 'dotfiles: magpie: the plugin %s was turned on\n' "$name"
            fi
        done

        DEPLOY_STEP=magpie-apply.providers
        while IFS= read -r entry; do
            case "$entry" in
                provider:*) ;;
                *) continue ;;
            esac
            role=${entry#provider:}
            preset=$(magpie_list_value "$MAGPIE_PROVIDER_PRESET_ROWS" "$role")
            preset=${preset#*=}
            source=$(magpie_provider_source "$role")
            if [ "$source" = codex-account ]; then
                magpie_run provider add "$preset" >/dev/null ||
                    { magpie_fail "cannot add the Magpie provider $preset"; return 1; }
            else
                credential=$(magpie_provider_credential "$source" || true)
                [ -n "$credential" ] || { magpie_fail "the credential for $role is missing"; return 1; }
                magpie_run provider add "$preset" "$credential" >/dev/null ||
                    { magpie_fail "cannot add the Magpie provider $preset"; return 1; }
            fi
            MAGPIE_PROVIDER_PRESENT="$MAGPIE_PROVIDER_PRESENT|$preset|"
            printf 'dotfiles: magpie: the provider %s was added\n' "$preset"
        done <<< "$change"

        DEPLOY_STEP=magpie-apply.groups
        for (( index=0; index<${#MAGPIE_GROUP_ID[@]}; index++ )); do
            group=${MAGPIE_GROUP_ID[index]}
            desired=$(magpie_list_value "$MAGPIE_GROUP_MODELS" "$group")
            [ -n "$desired" ] || continue
            routing=$(magpie_list_value "$MAGPIE_GROUP_ROUTING_ROWS" "$group")
            stays=$(magpie_list_value "$MAGPIE_GROUP_STAYS_ROWS" "$group")
            listed=$(magpie_list_value "$MAGPIE_GROUP_LISTED_ROWS" "$group")
            if printf '%s\n' "$change" | grep -qx "group-add:$group"; then
                magpie_run group add "$group" "models=$desired" "routing=$routing" "stays=$stays" "listed=$listed" >/dev/null ||
                    { magpie_fail "cannot create the Magpie group $group"; return 1; }
                printf 'dotfiles: magpie: the group %s was created\n' "$group"
            elif printf '%s\n' "$change" | grep -qx "group-set:$group"; then
                magpie_run group set "$group" "models=$desired" "routing=$routing" "stays=$stays" "listed=$listed" >/dev/null ||
                    { magpie_fail "cannot update the Magpie group $group"; return 1; }
                printf 'dotfiles: magpie: the group %s was updated\n' "$group"
            fi
        done

        DEPLOY_STEP=magpie-apply.picked
        if printf '%s\n' "$change" | grep -q '^picked:'; then
            magpie_picked_write ||
                { magpie_fail 'cannot write the picked models into Magpie settings'; return 1; }
            printf 'dotfiles: magpie: the picked models were written\n'
        fi

        DEPLOY_STEP=magpie-apply.visible
        for (( index=0; index<${#MAGPIE_VISIBLE_AGENT[@]}; index++ )); do
            agent=${MAGPIE_VISIBLE_AGENT[index]}
            # A picked change also refreshes the agent's list, so a group or
            # model ticked after the last apply reaches the gateway.
            if ! printf '%s\n' "$change" | grep -qx "visible:$agent" &&
               ! printf '%s\n' "$change" | grep -qx "picked:$agent"; then
                continue
            fi
            names=${MAGPIE_VISIBLE_NAMES[index]}
            magpie_run visible "$agent" "$names" >/dev/null ||
                { magpie_fail "cannot narrow the agent $agent to $names"; return 1; }
            printf 'dotfiles: magpie: the agent %s is shown %s\n' "$agent" "$names"
        done

        DEPLOY_STEP=magpie-apply.wiring
        while IFS= read -r entry; do
            case "$entry" in
                wiring:*) ;;
                *) continue ;;
            esac
            agent=${entry#wiring:}; group=${agent#*:}; agent=${agent%:*}
            magpie_run "$agent" "$group" >/dev/null ||
                { magpie_fail "cannot wire the agent $agent to $group"; return 1; }
            printf 'dotfiles: magpie: the agent %s is wired to %s\n' "$agent" "$group"
        done <<< "$change"
    fi

    DEPLOY_STEP=magpie-apply.dsh
    if [ -n "$backup" ]; then
        magpie_dsh_verify_official_row "$backup" || return 1
        printf 'dotfiles: magpie: the official DeepSeek row of every DSH profile is unchanged\n'
    fi

    DEPLOY_STEP=magpie-apply.codex-guard
    codex_after=$(magpie_sha256 "$HOME/.codex/config.toml" || true)
    if [ "$codex_before" != "$codex_after" ]; then
        guard='changed'
        magpie_fail 'the Codex configuration changed during the apply; the backup is kept'
        return 1
    fi
    printf 'dotfiles: magpie: the Codex configuration is unchanged\n'

    DEPLOY_STEP=magpie-apply.state
    content=$(magpie_state_content "$guard")
    if magpie_state_current "$(magpie_state_dir)/state.tsv" "$content"; then
        printf 'dotfiles: magpie: the recorded state is current; nothing was written\n'
    else
        magpie_state_write "$content" || return 1
        printf 'dotfiles: magpie: the state was recorded in %s\n' "$(magpie_state_dir)/state.tsv"
    fi

    if [ -n "$fatal" ]; then
        while IFS= read -r entry; do
            [ -n "$entry" ] || continue
            printf 'dotfiles: magpie: the required credential is missing: %s\n' "$entry" >&2
        done <<< "$fatal"
        magpie_fail 'a required model provider has no credential'
        return 1
    fi
    magpie_apply_summary
    return 0
}

# What the device runs, in one report.
magpie_apply_summary() {
    local index role group agent preset
    printf 'dotfiles: magpie: the gateway is %s\n' "$MAGPIE_GATEWAY"
    printf 'dotfiles: magpie: the proxy is %s\n' "$MAGPIE_PROXY"
    for (( index=0; index<${#MAGPIE_PROVIDER_ROLE[@]}; index++ )); do
        role=${MAGPIE_PROVIDER_ROLE[index]}; preset=${MAGPIE_PROVIDER_PRESET[index]}
        if magpie_list_contains "$MAGPIE_PROVIDER_PRESENT" "$preset"; then
            printf 'dotfiles: magpie: the provider %s is present\n' "$role"
        else
            printf 'dotfiles: magpie: the provider %s is missing\n' "$role"
        fi
    done
    for (( index=0; index<${#MAGPIE_GROUP_ID[@]}; index++ )); do
        group=${MAGPIE_GROUP_ID[index]}
        printf 'dotfiles: magpie: the group %s holds %s\n' "$group" \
            "$(magpie_list_value "$MAGPIE_GROUP_MODELS" "$group")"
    done
    for (( index=0; index<${#MAGPIE_WIRING_AGENT[@]}; index++ )); do
        agent=${MAGPIE_WIRING_AGENT[index]}
        printf 'dotfiles: magpie: the agent %s uses %s\n' "$agent" "${MAGPIE_WIRING_GROUP[index]}"
    done
    for (( index=0; index<${#MAGPIE_VISIBLE_AGENT[@]}; index++ )); do
        printf 'dotfiles: magpie: the agent %s is shown %s\n' \
            "${MAGPIE_VISIBLE_AGENT[index]}" "${MAGPIE_VISIBLE_NAMES[index]}"
    done
}

# Whether one credential source resolves. The value is never printed.
magpie_credential_resolves() {
    local source=$1
    case "$source" in
        codex-account) magpie_account_present ;;
        plugin-account) return 1 ;;
        *) magpie_provider_credential "$source" >/dev/null 2>&1 ;;
    esac
}

# Every model id the catalog knows, space separated.
magpie_catalog_model_ids() {
    local index candidates candidate id known=''
    local -a candidate_list
    for (( index=0; index<${#MAGPIE_MODEL_ROLE[@]}; index++ )); do
        candidates=${MAGPIE_MODEL_CANDIDATES[index]}
        IFS=, read -r -a candidate_list <<< "$candidates"
        for candidate in "${candidate_list[@]}"; do
            id=$candidate
            case "$candidate" in
                *'?'*) id=${candidate%?} ;;
            esac
            known="$known $id"
        done
    done
    printf '%s' "$known"
}

# The model provider catalog with the state of every credential source. A
# provider already in Magpie owns its credential there; the source is only
# needed to add it. The value of a credential is never printed.
magpie_providers() {
    local index role preset source required state
    magpie_catalog_validate "$(magpie_catalog_dir)" || return 1
    printf 'role|magpie provider|key source|required|credential\n'
    for (( index=0; index<${#MAGPIE_PROVIDER_ROLE[@]}; index++ )); do
        role=${MAGPIE_PROVIDER_ROLE[index]}; preset=${MAGPIE_PROVIDER_PRESET[index]}
        source=${MAGPIE_PROVIDER_SOURCE[index]}; required=${MAGPIE_PROVIDER_REQUIRED[index]}
        if magpie_provider_present "$preset"; then
            state=present
        elif magpie_credential_resolves "$source"; then
            state=resolves
        else
            state=missing
        fi
        printf '%s|%s|%s|%s|%s\n' "$role" "$preset" "$source" "$required" "$state"
    done
    return 0
}

# The current time in milliseconds. The gateway report needs a wall clock a
# shell cannot read portably on macOS.
magpie_now_ms() {
    local python
    python=$(magpie_python) || return 1
    "$python" -c 'import time; print(int(time.time() * 1000))'
}

# One completion against the gateway, and its verdict. The model is the first
# candidate the gateway serves for the role, so OpenCode Go is tested through
# its DeepSeek model and never through its Gemini endpoint. The request is
# 16 tokens: the cost of the check is one short turn per role.
magpie_test_role() {
    local role=$1 gateway=$2 live=$3 candidates candidate id response code body
    local start end message
    local -a candidate_list
    candidates=$(magpie_list_value "$MAGPIE_MODEL_CANDIDATE_ROWS" "$role") || return 1
    IFS=, read -r -a candidate_list <<< "$candidates"
    id=''
    for candidate in "${candidate_list[@]}"; do
        case "$candidate" in
            *'?'*) candidate=${candidate%?} ;;
        esac
        if magpie_list_contains "$live" "$candidate" || magpie_list_contains "$live" "${candidate#*/}"; then
            id=$candidate
            break
        fi
    done
    if [ -z "$id" ]; then
        printf '%s|-|error|no candidate the gateway serves\n' "$role"
        return 1
    fi
    start=$(magpie_now_ms || true)
    response=$(curl --noproxy '*' --silent --show-error --connect-timeout 5 --max-time 120 \
        -H 'Authorization: Bearer magpie' -H 'Content-Type: application/json' \
        -d "{\"model\":\"$id\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":128}" \
        -w '\n%{http_code}' "$gateway/v1/chat/completions" 2>&1 || true)
    end=$(magpie_now_ms || true)
    code=${response##*$'\n'}
    body=${response%$'\n'*}
    case "$code" in
        [0-9][0-9][0-9]) ;;
        *) body=$(printf '%s' "$response" | head -n1); code='' ;;
    esac
    if [ "$code" = 200 ] && printf '%s' "$body" | grep -q '"choices"'; then
        if [ -n "$start" ] && [ -n "$end" ]; then
            printf '%s|%s|ok|%s\n' "$role" "$id" "$((end - start))"
        else
            printf '%s|%s|ok|0\n' "$role" "$id"
        fi
        return 0
    fi
    message=$(printf '%s' "$body" |
        sed -n 's/.*"message"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
    [ -n "$message" ] || message=$body
    [ -n "$message" ] || message="http ${code:-none}"
    # The report is pipe-separated and one line per role.
    message=${message//|//}
    message=${message:0:120}
    printf '%s|%s|error|%s\n' "$role" "$id" "$message"
    return 1
}

# Probe model roles through the gateway's OpenAI-compatible endpoint. A role
# is tested through the first candidate the gateway serves; a role with no
# live candidate fails by name. The command never runs `magpie provider test`,
# which probes a provider's own endpoints rather than the models the routers
# use.
magpie_test() {
    local gateway output live id role
    local -a roles
    local failed=0
    magpie_catalog_validate "$(magpie_catalog_dir)" || return 1
    if ! magpie_gateway_status; then
        magpie_fail "the Magpie gateway does not answer on $MAGPIE_GATEWAY_DEFAULT"
        return 1
    fi
    gateway=$MAGPIE_GATEWAY
    if [ "$#" -gt 0 ]; then
        for role in "$@"; do
            if ! magpie_list_contains "$MAGPIE_MODEL_ROLES" "$role"; then
                magpie_fail "unknown model role: $role"
                return 1
            fi
        done
        roles=("$@")
    else
        roles=("${MAGPIE_MODEL_ROLE[@]}")
    fi
    output=$(magpie_models_fetch "$gateway" || true)
    if [ -z "$output" ]; then
        magpie_fail "cannot read the model list from $gateway/v1/models"
        return 1
    fi
    live=''
    for id in $(magpie_model_ids "$output"); do
        live="$live|$id|"
    done
    printf 'role|model|state|detail\n'
    for role in "${roles[@]}"; do
        magpie_test_role "$role" "$gateway" "$live" || failed=1
    done
    return "$failed"
}

# The state of the gateway, the proxy, the providers, the groups, the wiring,
# and the last Codex guard result. A missing required piece is a failing
# status.
magpie_status() {
    local index role preset source required group agent proxy output models
    local known guard='' missing='' state credential version name plugin_state current desired count
    magpie_catalog_validate "$(magpie_catalog_dir)" || return 1
    if magpie_gateway_status; then
        printf 'gateway|%s|answers\n' "$MAGPIE_GATEWAY"
    else
        printf 'gateway|%s|does not answer\n' "$MAGPIE_GATEWAY_DEFAULT"
        missing="$missing gateway"
    fi
    proxy=$(magpie_proxy_current)
    if [ -n "$proxy" ]; then
        printf 'proxy|%s\n' "$proxy"
    else
        printf 'proxy|none\n'
        missing="$missing proxy"
    fi
    if version=$(magpie_cask_version); then
        printf 'cask|%s|%s\n' "$MAGPIE_CASK_NAME" "$version"
    else
        printf 'cask|%s|not installed\n' "$MAGPIE_CASK_NAME"
    fi
    for (( index=0; index<${#MAGPIE_PROVIDER_ROLE[@]}; index++ )); do
        role=${MAGPIE_PROVIDER_ROLE[index]}; preset=${MAGPIE_PROVIDER_PRESET[index]}
        source=${MAGPIE_PROVIDER_SOURCE[index]}; required=${MAGPIE_PROVIDER_REQUIRED[index]}
        if magpie_provider_present "$preset"; then
            state=present
            credential=owned
        else
            state=missing
            if magpie_credential_resolves "$source"; then credential=resolves; else credential=missing; fi
        fi
        printf 'provider|%s|%s|credential %s\n' "$role" "$state" "$credential"
        if [ "$state" = missing ] && [ "$required" = yes ]; then
            missing="$missing provider $role"
        fi
        if [ "$state" = missing ] && [ "$credential" = missing ] && [ "$required" = yes ]; then
            missing="$missing credential $role"
        fi
    done
    known=$(magpie_catalog_model_ids)
    plugin_state=$(magpie_plugin_state || true)
    for (( index=0; index<${#MAGPIE_PLUGIN_NAME[@]}; index++ )); do
        name=${MAGPIE_PLUGIN_NAME[index]}
        state=$(magpie_plugin_state_of "$plugin_state" "${MAGPIE_PLUGIN_SOURCE[index]}")
        case "$state" in
            loaded) printf 'plugin|%s|loaded\n' "$name" ;;
            plugins)
                printf 'plugin|%s|off\n' "$name"
                missing="$missing plugin $name" ;;
            *)
                printf 'plugin|%s|missing\n' "$name"
                missing="$missing plugin $name" ;;
        esac
    done
    for (( index=0; index<${#MAGPIE_GROUP_ID[@]}; index++ )); do
        group=${MAGPIE_GROUP_ID[index]}
        if output=$(magpie_run group "$group" 2>/dev/null); then
            models=$(magpie_group_models "$output" "$known")
            printf 'group|%s|%s\n' "$group" "$models"
        else
            printf 'group|%s|missing\n' "$group"
            missing="$missing group $group"
        fi
    done
    for (( index=0; index<${#MAGPIE_WIRING_AGENT[@]}; index++ )); do
        agent=${MAGPIE_WIRING_AGENT[index]}
        printf 'wiring|%s|%s\n' "$agent" "${MAGPIE_WIRING_GROUP[index]}"
    done
    for (( index=0; index<${#MAGPIE_VISIBLE_AGENT[@]}; index++ )); do
        agent=${MAGPIE_VISIBLE_AGENT[index]}
        if names=$(magpie_visible_names "$agent"); then
            [ -n "$names" ] || names='every model'
            printf 'visible|%s|%s\n' "$agent" "$names"
        else
            printf 'visible|%s|unknown\n' "$agent"
            missing="$missing visible $agent"
        fi
    done
    for (( index=0; index<${#MAGPIE_PICKED_AGENT[@]}; index++ )); do
        agent=${MAGPIE_PICKED_AGENT[index]}; desired=${MAGPIE_PICKED_MODELS[index]}
        if current=$(magpie_picked_current "$agent"); then
            if [ -z "$current" ]; then
                count=0
            else
                count=$(printf '%s' "$current" | awk -F, '{print NF}')
            fi
            printf 'picked|%s|%s entries\n' "$agent" "$count"
            if [ "$(magpie_names_sorted "$current")" != "$(magpie_names_sorted "$desired")" ]; then
                missing="$missing picked $agent"
            fi
        else
            printf 'picked|%s|unknown\n' "$agent"
            missing="$missing picked $agent"
        fi
    done
    magpie_dsh_official_state
    if [ -f "$(magpie_state_dir)/state.tsv" ]; then
        guard=$(grep '^codex-guard|' "$(magpie_state_dir)/state.tsv" 2>/dev/null | head -n1)
        [ -n "$guard" ] || guard='codex-guard|unknown'
    else
        guard='codex-guard|not recorded'
    fi
    printf '%s\n' "$guard"
    if [ -n "$missing" ]; then
        printf 'dotfiles: magpie: missing:%s\n' "$missing" >&2
        return 1
    fi
    return 0
}
