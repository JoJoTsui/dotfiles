# Device-owned version overrides.
#
# The repository catalogs own the default version of every managed component:
# an agent package, a Pixi tool, an installer command. A device may own a
# different version of a component it runs. The override file below records
# that ownership, and the deployment installs and verifies the declared
# version instead of the catalog pin. Removing an entry restores the
# repository default on the next apply.
#
# ~/.config/dotfiles/versions.tsv
#   agent|<agent name>|<exact version>     coding client, npm or native
#   tool|<conda package>|<exact version>    Pixi-managed command
#   cli|<installer tool>|<minimum version>  installer-owned command
#
# The file is device state. The deployment reads it and never writes it.
# shellcheck shell=bash

DEPLOY_OVERRIDE_FILE="${DEPLOY_HOME:-$HOME}/.config/dotfiles/versions.tsv"

override_lookup() {
    # $1 kind, $2 name. Prints the declared version, if any.
    local kind=$1 name=$2
    [ -f "$DEPLOY_OVERRIDE_FILE" ] || return 0
    awk -F'|' -v kind="$kind" -v name="$name" '
        { sub(/\r$/, "") }
        /^[[:space:]]*#/ { next }
        NF < 3 { next }
        $1 == kind && $2 == name { print $3; exit }
    ' "$DEPLOY_OVERRIDE_FILE"
}

override_agent_version() { override_lookup agent "$1"; }
override_tool_version() { override_lookup tool "$1"; }
override_cli_minimum() { override_lookup cli "$1"; }

override_agent_known() {
    local name=$1 entry
    [ -f "$DEPLOY_SOURCE/deployment/agents/catalog.tsv" ] || return 1
    while IFS=$'|\r' read -r entry _ _ _ _ _; do
        case "$entry" in ''|\#*) continue ;; esac
        if [ "$entry" = "$name" ]; then return 0; fi
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    [ -f "$DEPLOY_SOURCE/deployment/agents/native.tsv" ] || return 1
    while IFS=$'|\r' read -r entry _ _ _ _; do
        case "$entry" in ''|\#*) continue ;; esac
        if [ "$entry" = "$name" ]; then return 0; fi
    done < "$DEPLOY_SOURCE/deployment/agents/native.tsv"
    return 1
}

override_tool_known() {
    local package=$1 specifications specification
    [ -f "$DEPLOY_SOURCE/deployment/common-tools.tsv" ] || return 1
    while IFS=$'|\r' read -r _ specifications _ _; do
        case "${specifications:-}" in ''|\#*) continue ;; esac
        for specification in $(printf '%s' "$specifications" | tr ',' ' '); do
            if [ "${specification%%==*}" = "$package" ]; then return 0; fi
        done
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
    [ -f "$DEPLOY_SOURCE/deployment/bundle-tools.tsv" ] || return 1
    while IFS=$'|\r' read -r _ _ specifications _ _ _; do
        case "${specifications:-}" in ''|\#*) continue ;; esac
        for specification in $(printf '%s' "$specifications" | tr ',' ' '); do
            if [ "${specification%%==*}" = "$package" ]; then return 0; fi
        done
    done < "$DEPLOY_SOURCE/deployment/bundle-tools.tsv"
    return 1
}

override_cli_known() {
    local name=$1 entry
    [ -f "$DEPLOY_SOURCE/deployment/installer-tools.tsv" ] || return 1
    while IFS=$'|\r' read -r entry _ _ _ _ _ _; do
        case "$entry" in ''|\#*) continue ;; esac
        if [ "$entry" = "$name" ]; then return 0; fi
    done < "$DEPLOY_SOURCE/deployment/installer-tools.tsv"
    return 1
}

# The Atuin version is the storage contract of one history release. The
# importer reads it from the applied profile, so a device override would leave
# the importer and the installed command describing different releases.
override_rejects_atuin() {
    if [ "$1" = atuin ]; then
        fail "the Atuin version stays with the repository pin: the history importer verifies one storage schema"
    fi
}

validate_version_overrides() {
    local file=$DEPLOY_OVERRIDE_FILE line kind name version rest fields seen=''
    [ -e "$file" ] || return 0
    [ -f "$file" ] || fail "the version override file is not a regular file: $file"
    [ ! -L "$file" ] || fail "the version override file is a symlink: $file"
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        fields=$(printf '%s\n' "$line" | awk -F'|' '{ print NF }')
        if [ "$fields" != 3 ]; then
            fail "invalid version override (expected kind|name|version): $line"
        fi
        kind=${line%%|*}
        rest=${line#*|}
        name=${rest%%|*}
        version=${rest#*|}
        case "$name" in
            ''|*[!0-9A-Za-z._-]*) fail "invalid version override name: $name" ;;
        esac
        case "$version" in
            ''|*[!0-9A-Za-z.+_~-]*) fail "invalid version override version: $version" ;;
        esac
        case ",$seen," in
            *",$kind|$name,"*) fail "duplicate version override for $kind $name" ;;
        esac
        seen="$seen$kind|$name,"
        case "$kind" in
            agent)
                if ! override_agent_known "$name"; then
                    fail "unknown agent in version override: $name"
                fi
                ;;
            tool)
                if ! override_tool_known "$name"; then
                    fail "unknown tool in version override: $name"
                fi
                override_rejects_atuin "$name"
                ;;
            cli)
                if ! override_cli_known "$name"; then
                    fail "unknown installer tool in version override: $name"
                fi
                override_rejects_atuin "$name"
                if ! installer_version_at_least "$version" "$version"; then
                    fail "invalid minimum version for $name: $version"
                fi
                ;;
            *)
                fail "unknown version override kind: $kind (use agent, tool, or cli)"
                ;;
        esac
    done < "$file"
}

# The catalog default of one component, so a plan can show both the declared
# override and the version it replaces.
override_default_version() {
    local kind=$1 name=$2 entry
    case "$kind" in
        agent)
            [ -f "$DEPLOY_SOURCE/deployment/agents/catalog.tsv" ] || return 0
            while IFS=$'|\r' read -r entry _ version _ _ _; do
                case "$entry" in ''|\#*) continue ;; esac
                if [ "$entry" = "$name" ]; then printf '%s' "$version"; return 0; fi
            done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
            [ -f "$DEPLOY_SOURCE/deployment/agents/native.tsv" ] || return 0
            while IFS=$'|\r' read -r entry version _ _ _; do
                case "$entry" in ''|\#*) continue ;; esac
                if [ "$entry" = "$name" ]; then printf '%s' "$version"; return 0; fi
            done < "$DEPLOY_SOURCE/deployment/agents/native.tsv"
            ;;
        tool)
            [ -f "$DEPLOY_SOURCE/deployment/common-tools.tsv" ] || return 0
            while IFS=$'|\r' read -r _ specifications _ _; do
                case "${specifications:-}" in ''|\#*) continue ;; esac
                for specification in $(printf '%s' "$specifications" | tr ',' ' '); do
                    if [ "${specification%%==*}" = "$name" ]; then
                        printf '%s' "${specification#*==}"
                        return 0
                    fi
                done
            done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
            [ -f "$DEPLOY_SOURCE/deployment/bundle-tools.tsv" ] || return 0
            while IFS=$'|\r' read -r _ _ specifications _ _ _; do
                case "${specifications:-}" in ''|\#*) continue ;; esac
                for specification in $(printf '%s' "$specifications" | tr ',' ' '); do
                    if [ "${specification%%==*}" = "$name" ]; then
                        printf '%s' "${specification#*==}"
                        return 0
                    fi
                done
            done < "$DEPLOY_SOURCE/deployment/bundle-tools.tsv"
            ;;
        cli)
            [ -f "$DEPLOY_SOURCE/deployment/installer-tools.tsv" ] || return 0
            while IFS=$'|\r' read -r entry _ _ _ minimum _ _; do
                case "$entry" in ''|\#*) continue ;; esac
                if [ "$entry" = "$name" ]; then printf '%s' "$minimum"; return 0; fi
            done < "$DEPLOY_SOURCE/deployment/installer-tools.tsv"
            ;;
    esac
    return 0
}

print_version_overrides() {
    # The effective device overrides, as plan metadata.
    local file=$DEPLOY_OVERRIDE_FILE line kind name version rest separator=''
    printf '['
    [ -f "$file" ] || { printf ']'; return 0; }
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        kind=${line%%|*}
        rest=${line#*|}
        name=${rest%%|*}
        version=${rest#*|}
        printf '%s{"kind":' "$separator"; json_string "$kind"
        printf ',"name":'; json_string "$name"
        printf ',"version":'; json_string "$version"
        printf ',"default":'; json_string "$(override_default_version "$kind" "$name")"
        printf '}'; separator=,
    done < "$file"
    printf ']'
}

# The normalized snapshot is the shared input of the registry merge. It is
# derived from the validated override file and written to device state.
deploy_version_overrides() {
    local state_dir="$XDG_STATE_HOME/dotfiles"
    local file=$DEPLOY_OVERRIDE_FILE line kind name version rest temporary
    local separator=''
    mkdir -p "$state_dir"
    [ ! -L "$state_dir" ] || fail 'the deployment state directory is a symlink'
    temporary=$(mktemp "$state_dir/.version-overrides.XXXXXX")
    {
        printf '{'
        for kind in agent tool cli; do
            case "$kind" in
                agent) printf '"agents":{' ;;
                tool) printf '"tools":{' ;;
                cli) printf '"clis":{' ;;
            esac
            separator=''
            if [ -f "$file" ]; then
                while IFS= read -r line || [ -n "$line" ]; do
                    line=${line%$'\r'}
                    case "$line" in ''|\#*) continue ;; esac
                    [ "${line%%|*}" = "$kind" ] || continue
                    rest=${line#*|}
                    name=${rest%%|*}
                    version=${rest#*|}
                    printf '%s"' "$separator"; printf '%s' "$name"
                    printf '":"%s"' "$version"; separator=,
                done < "$file"
            fi
            printf '}'
            [ "$kind" = cli ] || printf ','
        done
        printf '}\n'
    } > "$temporary"
    mv -f "$temporary" "$state_dir/version-overrides.json"
}
