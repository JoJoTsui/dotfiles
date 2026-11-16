# Agent provider catalog and public plan metadata. Sourcing is read-only.
# The device override reader is a dependency of the client versions below.
source "$DEPLOY_SOURCE/deployment/overrides.sh"

DEPLOY_AGENTS=()
DEPLOY_AGENT_NAMES=()
DEPLOY_AGENT_ROWS=()
DEPLOY_AGENT_ORDER=()
DEPLOY_HERDR_KINDS=()
AGENT_ROW=()

# The provider catalog is the only source of agent installation data. The
# native Windows adapter reads the same records.
AGENT_CATALOG_PATH="deployment/agents/providers.tsv"
AGENT_HERDR_KINDS_PATH="deployment/agents/herdr-kinds.tsv"
AGENT_CATALOG_FIELDS=15

# Catalog records are read once so every later lookup sees the same rows.
agent_catalog_load() {
    local file="$DEPLOY_SOURCE/$AGENT_CATALOG_PATH" line name seen=''
    DEPLOY_AGENT_ROWS=()
    DEPLOY_AGENT_ORDER=()
    [ -f "$file" ] || fail "the agent provider catalog is missing: $AGENT_CATALOG_PATH"
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        DEPLOY_AGENT_ROWS+=("$line")
        name=${line%%|*}
        case "$seen" in
            *"|$name|"*) ;;
            *) DEPLOY_AGENT_ORDER+=("$name"); seen="$seen|$name|" ;;
        esac
    done < "$file"
}

# The Herdr kinds the deployment recognizes. A catalog record may name a kind
# only when this list contains it.
agent_herdr_kinds_load() {
    local file="$DEPLOY_SOURCE/$AGENT_HERDR_KINDS_PATH" line
    DEPLOY_HERDR_KINDS=()
    [ -f "$file" ] || fail "the Herdr kind catalog is missing: $AGENT_HERDR_KINDS_PATH"
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case "$line" in ''|\#*) continue ;; esac
        DEPLOY_HERDR_KINDS+=("$line")
    done < "$file"
}

# Split one catalog record into its fields. The fields are positional because
# the record is the shared contract of both bootstrap adapters.
agent_row_split() {
    local -a fields
    IFS='|' read -r -a fields <<< "$1"
    AGENT_ROW=(${fields[@]+"${fields[@]}"})
    while [ "${#AGENT_ROW[@]}" -lt "$AGENT_CATALOG_FIELDS" ]; do
        AGENT_ROW+=("")
    done
}

agent_row_field_count() {
    printf '%s' "$1" | awk -F'|' '{ print NF }'
}

# The records of one agent that can serve the deployment platform, in the
# provider chain order the catalog declares. A device-owned agent version
# forces a deployment-owned install: an installer-owned provider cannot
# promise an exact version.
agent_viable_rows() {
    local name=$1 row rows=() index other left right swap override
    override=$(override_agent_version "$name")
    for row in "${DEPLOY_AGENT_ROWS[@]}"; do
        agent_row_split "$row"
        [ "${AGENT_ROW[0]}" = "$name" ] || continue
        agent_platform_matches "${AGENT_ROW[7]}" || continue
        case "${AGENT_ROW[1]}" in
            homebrew)
                if [ -n "$override" ]; then continue; fi ;;
        esac
        rows+=("$row")
    done
    for (( index=0; index<${#rows[@]}; index++ )); do
        for (( other=index+1; other<${#rows[@]}; other++ )); do
            agent_row_split "${rows[index]}"; left=${AGENT_ROW[8]}
            agent_row_split "${rows[other]}"; right=${AGENT_ROW[8]}
            if [ "$right" -lt "$left" ]; then
                swap=${rows[index]}
                rows[index]=${rows[other]}
                rows[other]=$swap
            fi
        done
    done
    for (( index=0; index<${#rows[@]}; index++ )); do
        printf '%s\n' "${rows[index]}"
    done
}

# The provider the plan selects first for one agent on this platform.
agent_resolved_row() {
    local name=$1 row
    while IFS= read -r row; do
        [ -n "$row" ] || continue
        printf '%s' "$row"
        return 0
    done <<< "$(agent_viable_rows "$name")"
    return 1
}

# The record of the provider the deployment owns and pins. It carries the
# package or release manifest, the lock, and the runtime floor.
agent_owned_row() {
    local name=$1 row
    for row in "${DEPLOY_AGENT_ROWS[@]}"; do
        agent_row_split "$row"
        [ "${AGENT_ROW[0]}" = "$name" ] || continue
        case "${AGENT_ROW[1]}" in
            bun|native) printf '%s' "$row"; return 0 ;;
        esac
    done
    return 1
}

# The selection mode of one agent. Every record of an agent declares it.
agent_owned_selection() {
    local name=$1 row
    for row in "${DEPLOY_AGENT_ROWS[@]}"; do
        agent_row_split "$row"
        [ "${AGENT_ROW[0]}" = "$name" ] || continue
        printf '%s' "${AGENT_ROW[9]}"
        return 0
    done
    return 1
}

agent_selected() {
    local name=$1 selection selected
    selection=$(agent_owned_selection "$name")
    [ "$selection" = always ] && return 0
    for selected in ${DEPLOY_AGENTS[@]+"${DEPLOY_AGENTS[@]}"}; do
        [ "$selected" != "$name" ] || return 0
    done
    return 1
}

# Short installation names remain stable when package names change.
agent_canonical_name() {
    case "$1" in
        kimi-code) printf 'kimi' ;;
        claude-code) printf 'claude' ;;
        minimax-code) printf 'minimax' ;;
        *) printf '%s' "$1" ;;
    esac
}

agent_known() {
    local name
    for name in ${DEPLOY_AGENT_NAMES[@]+"${DEPLOY_AGENT_NAMES[@]}"}; do
        [ "$name" != "$1" ] || return 0
    done
    return 1
}

agent_platform_matches() {
    case ",$1," in *,all,*) return 0 ;; esac
    case ",$1," in
        *,unix,*) [ "$DEPLOY_PLATFORM" != windows ] && return 0 ;;
    esac
    case ",$1," in *",$DEPLOY_PLATFORM,"*) return 0 ;; esac
    return 1
}

# An invalid catalog record stops the deployment before it creates any state
# or file, and the message names the offending record.
validate_agent_catalog() {
    local row fields name provider package package_kind version policy commands platforms order selection
    local herdr minimum trusted lock diagnostic platform kind kinds='' seen=''
    local agent herdr_mode selection_mode orders count owned
    for kind in ${DEPLOY_HERDR_KINDS[@]+"${DEPLOY_HERDR_KINDS[@]}"}; do
        kinds="$kinds|$kind|"
    done
    for row in "${DEPLOY_AGENT_ROWS[@]}"; do
        fields=$(agent_row_field_count "$row")
        [ "$fields" = "$AGENT_CATALOG_FIELDS" ] ||
            fail "invalid agent provider catalog record (expected $AGENT_CATALOG_FIELDS fields, found $fields): $row"
        agent_row_split "$row"
        name=${AGENT_ROW[0]}; provider=${AGENT_ROW[1]}; package=${AGENT_ROW[2]}
        package_kind=${AGENT_ROW[3]}; version=${AGENT_ROW[4]}; policy=${AGENT_ROW[5]}
        commands=${AGENT_ROW[6]}; platforms=${AGENT_ROW[7]}; order=${AGENT_ROW[8]}
        selection=${AGENT_ROW[9]}; herdr=${AGENT_ROW[10]}; minimum=${AGENT_ROW[11]}
        trusted=${AGENT_ROW[12]}; lock=${AGENT_ROW[13]}; diagnostic=${AGENT_ROW[14]}
        case "$name" in
            ''|*[!A-Za-z0-9._-]*) fail "invalid agent provider catalog record (agent name): $row" ;;
        esac
        case "$provider" in
            bun|native|homebrew) ;;
            *) fail "invalid agent provider catalog record (unknown provider '$provider'): $row" ;;
        esac
        case "$policy" in
            exact|floor) ;;
            *) fail "invalid agent provider catalog record (unknown version policy '$policy'): $row" ;;
        esac
        case "$platforms" in
            ''|,*|*,|*[!A-Za-z0-9,]*)
                fail "invalid agent provider catalog record (platforms): $row" ;;
        esac
        for platform in ${platforms//,/ }; do
            case "$platform" in
                all|unix|windows|linux|macos|wsl) ;;
                *) fail "invalid agent provider catalog record (unsupported platform '$platform'): $row" ;;
            esac
        done
        case "$order" in
            ''|*[!0-9]*) fail "invalid agent provider catalog record (order): $row" ;;
        esac
        [ "$order" -ge 1 ] || fail "invalid agent provider catalog record (order starts at 1): $row"
        case "$selection" in
            selectable|always) ;;
            *) fail "invalid agent provider catalog record (unknown selection '$selection'): $row" ;;
        esac
        case "$commands" in
            ''|,*|*,|*[!A-Za-z0-9,._-]*)
                fail "invalid agent provider catalog record (commands): $row" ;;
        esac
        case "$version" in
            ''|*[!0-9A-Za-z.+-]*) fail "invalid agent provider catalog record (version): $row" ;;
        esac
        if [ "$herdr" != '-' ]; then
            case "$kinds" in
                *"|$herdr|"*) ;;
                *) fail "invalid agent provider catalog record (unknown Herdr kind '$herdr'): $row" ;;
            esac
        fi
        case "$seen" in
            *"|$name|$provider|"*) fail "duplicate agent provider catalog record ($name/$provider): $row" ;;
        esac
        seen="$seen|$name|$provider|"
        case "$provider" in
            bun)
                [ -n "$package" ] || fail "invalid agent provider catalog record (missing package): $row"
                [ "$package_kind" = '-' ] ||
                    fail "invalid agent provider catalog record (a Bun record has no package kind): $row"
                [ "$policy" = exact ] ||
                    fail "invalid agent provider catalog record (a deployment-owned provider keeps an exact pin): $row"
                [ -f "$DEPLOY_SOURCE/$lock" ] || fail "missing supported Bun lock for $name: $lock"
                case "$minimum" in
                    ''|*[!0-9.]*) fail "invalid agent provider catalog record (minimum Node): $row" ;;
                esac
                [ "$diagnostic" = '-' ] ||
                    fail "invalid agent provider catalog record (a Bun record accepts a containing diagnostic): $row"
                ;;
            native)
                [ -n "$package" ] || fail "invalid agent provider catalog record (missing native release): $row"
                [ "$package_kind" = '-' ] ||
                    fail "invalid agent provider catalog record (a native record has no package kind): $row"
                [ "$policy" = exact ] ||
                    fail "invalid agent provider catalog record (a deployment-owned provider keeps an exact pin): $row"
                case "$lock" in
                    https://*) ;;
                    *) fail "invalid agent provider catalog record (native release manifest must use HTTPS): $row" ;;
                esac
                case "$diagnostic" in
                    *'{version}'*) ;;
                    *) fail "invalid agent provider catalog record (native diagnostic must report {version}): $row" ;;
                esac
                ;;
            homebrew)
                [ -n "$package" ] || fail "invalid agent provider catalog record (missing Homebrew package): $row"
                case "$package_kind" in
                    formula|cask) ;;
                    *) fail "invalid agent provider catalog record (unknown Homebrew package kind '$package_kind'): $row" ;;
                esac
                [ "$policy" = floor ] ||
                    fail "invalid agent provider catalog record (an installer-owned provider carries a floor): $row"
                ;;
        esac
    done
    # Every agent declares one Herdr kind and one selection mode, offers at
    # least one provider that can serve this platform, and owns exactly one
    # deployment-owned record.
    for name in "${DEPLOY_AGENT_ORDER[@]}"; do
        herdr_mode=''; selection_mode=''; orders=''; count=0; owned=0
        for row in "${DEPLOY_AGENT_ROWS[@]}"; do
            agent_row_split "$row"
            [ "${AGENT_ROW[0]}" = "$name" ] || continue
            if [ -z "$herdr_mode" ]; then
                herdr_mode=${AGENT_ROW[10]}; selection_mode=${AGENT_ROW[9]}
            fi
            case "${AGENT_ROW[1]}" in
                bun|native) owned=$((owned + 1)) ;;
            esac
            [ "${AGENT_ROW[10]}" = "$herdr_mode" ] ||
                fail "agent provider catalog records disagree on the Herdr kind of $name: $row"
            [ "${AGENT_ROW[9]}" = "$selection_mode" ] ||
                fail "agent provider catalog records disagree on the selection of $name: $row"
            agent_platform_matches "${AGENT_ROW[7]}" || continue
            count=$((count + 1))
            case "$orders" in
                *"|${AGENT_ROW[8]},"*) fail "agent provider catalog records share the order ${AGENT_ROW[8]} of $name: $row" ;;
            esac
            orders="$orders|${AGENT_ROW[8]},"
        done
        [ "$count" -gt 0 ] || fail "agent $name has no provider that can serve $DEPLOY_PLATFORM"
        [ "$owned" -eq 1 ] || fail "agent $name must declare exactly one deployment-owned provider"
    done
}

resolve_agent_selection() {
    local selection="${DOTFILES_AGENTS:-all}" requested canonical item name row
    local requested_agents=() normalized=()
    DEPLOY_AGENT_NAMES=()
    if "$CLI_AGENTS_SET"; then selection=$CLI_AGENTS; fi
    # Catalog order is the public installation and plan order.
    for name in "${DEPLOY_AGENT_ORDER[@]}"; do
        [ "$(agent_owned_selection "$name")" = selectable ] || continue
        DEPLOY_AGENT_NAMES+=("$name")
    done
    case "$selection" in
        all) normalized=(${DEPLOY_AGENT_NAMES[@]+"${DEPLOY_AGENT_NAMES[@]}"}) ;;
        none) ;;
        ''|,*|*,|*,,*) fail 'invalid agent selection: use all, none, or a comma-separated named list' ;;
        *)
            IFS=, read -r -a requested_agents <<< "$selection"
            for requested in "${requested_agents[@]}"; do
                canonical=$(agent_canonical_name "$requested")
                agent_known "$canonical" ||
                    fail "unknown agent: $requested (choose ${DEPLOY_AGENT_NAMES[*]})"
                normalized+=("$canonical")
            done ;;
    esac
    # Stable catalog ordering deduplicates aliases and repeated names.
    for name in "${DEPLOY_AGENT_NAMES[@]}"; do
        for item in ${normalized[@]+"${normalized[@]}"}; do
            if [ "$item" = "$name" ]; then DEPLOY_AGENTS+=("$name"); break; fi
        done
    done
    # The commands of every selected agent, taken from the provider the plan
    # selects on this platform.
    for name in "${DEPLOY_AGENT_ORDER[@]}"; do
        agent_selected "$name" || continue
        row=$(agent_resolved_row "$name")
        [ -n "$row" ] || continue
        agent_row_split "$row"
        IFS=, read -r -a requested_agents <<< "${AGENT_ROW[6]}"
        DEPLOY_TOOLS+=("${requested_agents[@]}")
    done
}

# The provider-specific fields of one catalog record. The record's provider
# decides which fields exist, so an installer-owned record never carries a
# deployment-owned lock and a deployment-owned record never carries a package
# kind. The caller names the provider, package, package kind, minimum Node,
# and lock or release manifest of the record.
print_agent_provider_fields() {
    local provider=$1 package=$2 kind=$3 minimum=$4 lock=$5
    case "$provider" in
        homebrew)
            printf ',"package":'; json_string "$package"
            printf ',"packageKind":'; json_string "$kind"
            printf ',"manager":"homebrew"' ;;
        bun)
            printf ',"package":'; json_string "$package"
            printf ',"manager":"bun"'
            printf ',"minimumNode":'; json_string "$minimum"
            printf ',"lock":'; json_string "$lock" ;;
        native)
            printf ',"package":null'
            printf ',"manager":"native"'
            printf ',"manifest":'; json_string "$lock" ;;
    esac
}

print_agent_packages() {
    local name row resolved owned provider policy version commands herdr separator='' command
    local exposed_commands=() first=''
    printf '['
    for name in "${DEPLOY_AGENT_ORDER[@]}"; do
        agent_selected "$name" || continue
        resolved=$(agent_resolved_row "$name")
        [ -n "$resolved" ] || continue
        agent_row_split "$resolved"
        provider=${AGENT_ROW[1]}
        policy=${AGENT_ROW[5]}
        commands=${AGENT_ROW[6]}
        herdr=${AGENT_ROW[10]}
        version=$(agent_effective_version "$name" "${AGENT_ROW[4]}")
        printf '%s{"name":' "$separator"; json_string "$name"
        printf ',"provider":'; json_string "$provider"
        printf ',"policy":'; json_string "$policy"
        printf ',"version":'; json_string "$version"
        printf ',"commands":['
        IFS=, read -r -a exposed_commands <<< "$commands"
        first=''
        for command in "${exposed_commands[@]}"; do
            printf '%s' "$first"; json_string "$command"; first=,
        done
        printf ']'
        printf ',"herdr":'
        if [ "$herdr" = '-' ]; then printf 'null'; else json_string "$herdr"; fi
        # The entry describes the provider the plan selects. Its own record
        # decides the fields: a Homebrew record names its package and kind, a
        # Bun record names its package, minimum Node, and lock, and a native
        # record names its release manifest.
        print_agent_provider_fields "$provider" "${AGENT_ROW[2]}" "${AGENT_ROW[3]}" \
            "${AGENT_ROW[11]}" "${AGENT_ROW[13]}"
        # The deployment-owned fallback of an installer-owned provider stays
        # in its own field; it never mixes into the selected provider.
        if [ "$provider" != bun ] && [ "$provider" != native ]; then
            owned=$(agent_owned_row "$name")
            agent_row_split "$owned"
            printf ',"fallback":{"provider":'; json_string "${AGENT_ROW[1]}"
            print_agent_provider_fields "${AGENT_ROW[1]}" "${AGENT_ROW[2]}" "${AGENT_ROW[3]}" \
                "${AGENT_ROW[11]}" "${AGENT_ROW[13]}"
            printf '}'
        fi
        printf '}'
        separator=,
    done
    printf ']'
}

# A device may own a different version of an agent than the catalog pins.
# The catalog stays the default; the override decides what this device runs.
agent_effective_version() {
    local name=$1 default=$2 override
    override=$(override_agent_version "$name")
    if [ -n "$override" ]; then printf '%s' "$override"; else printf '%s' "$default"; fi
}

agent_runtime_pin() {
    local environment specifications commands targets item override
    local runtime_specs=()
    while IFS=$'|\r' read -r environment specifications commands targets; do
        case "$environment" in ''|\#*) continue ;; esac
        IFS=, read -r -a runtime_specs <<< "$specifications"
        for item in "${runtime_specs[@]}"; do
            if [ "${item%%==*}" = "$1" ]; then
                override=$(override_tool_version "$1")
                if [ -n "$override" ]; then printf '%s' "$override"; else printf '%s' "${item#*==}"; fi
                return
            fi
        done
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
    fail "common catalog must declare the $1 runtime pin"
}

agent_version_at_least() {
    local actual=$1 minimum=$2 actual_parts=() minimum_parts=() index
    IFS=. read -r -a actual_parts <<< "$actual"
    IFS=. read -r -a minimum_parts <<< "$minimum"
    for index in 0 1 2; do
        [ "${actual_parts[$index]:-0}" -ge "${minimum_parts[$index]:-0}" ] || return 1
        [ "${actual_parts[$index]:-0}" -le "${minimum_parts[$index]:-0}" ] || return 0
    done
}

agent_shell_quote() {
    local value=$1
    value=${value//\'/\'\\\'\'}
    printf "'%s'" "$value"
}

# The expected --version output of one provider. A catalog record that reports
# "-" accepts a diagnostic containing the version; every other record states
# the diagnostic with {version} replaced by the version. A deployment-owned
# provider must report exactly that diagnostic; an installer-owned provider
# owns its installed version, so it accepts a diagnostic that contains it.
agent_diagnostic_matches() {
    local version=$1 diagnostic=$2 template=$3 policy=${4:-exact} expected
    case "$template" in
        '-') case "$diagnostic" in *"$version"*) return 0 ;; esac; return 1 ;;
        *'{version}'*)
            expected=${template//\{version\}/$version}
            case "$policy" in
                floor) case "$diagnostic" in *"$expected"*) return 0 ;; esac; return 1 ;;
                *) [ "$diagnostic" = "$expected" ] ;;
            esac ;;
        *) return 1 ;;
    esac
}

# The upstream native release carries OS/CPU feature selection. Reuse its
# published manifest and verify the archive digest before executing the
# extracted installer binary; the remote install script itself is not executed.
native_release_platform_key() {
    local os arch
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m)
    if [ "$os" = darwin ] && [ "$arch" = x86_64 ] &&
        [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then
        arch=arm64
    fi
    [ "$arch" = aarch64 ] && arch=arm64
    [ "$arch" = x86_64 ] && arch=amd64
    # The upstream Linux x64 build needs the same flags as its published
    # baseline archive.
    if [ "$os" = linux ] && [ "$arch" = amd64 ] && ! native_release_cpu_has_flags; then
        arch=amd64-baseline
    fi
    printf '%s %s' "$os" "$arch"
}

native_release_cpu_has_flags() {
    local cpuinfo="${QODERCLI_CPUINFO_PATH:-/proc/cpuinfo}" flags flag
    [ -r "$cpuinfo" ] || return 1
    flags=$(grep -m1 -E '^flags[[:space:]]*:' "$cpuinfo" 2>/dev/null || true)
    [ -n "$flags" ] || return 1
    for flag in sse4_2 popcnt avx avx2 bmi1 bmi2 fma; do
        printf '%s\n' "$flags" |
            grep -Eq "(^|[[:space:]])${flag}($|[[:space:]])" || return 1
    done
}

manifest_string() {
    printf '%s' "$1" |
        sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n1
}

agent_launcher() {
    local launcher=$1 target=$2
    [ ! -L "$launcher" ] || rm "$launcher"
    {
        printf '#!/bin/sh\n# Managed by dotfiles; the native client owns its state root.\n'
        printf 'exec '; agent_shell_quote "$target"; printf ' "$@"\n'
    } > "$launcher"
    chmod 755 "$launcher"
}

# The verified native release of one agent. The catalog record names the
# release binary, the manifest base, and the expected diagnostic.
install_native_release() {
    local name=$1 version=$2 commands=$3 binary=$4 manifest_base=$5 template=$6
    local root cli entry manifest manifest_json archive scratch url checksum os arch command diagnostic
    local exposed_commands=()
    root="$HOME/.$name"
    cli="$root/bin/$binary/$binary-$version"
    if [ ! -x "$cli" ] || ! diagnostic=$("$cli" --version 2>/dev/null) ||
        ! agent_diagnostic_matches "$version" "$diagnostic" "$template"; then
        set -- $(native_release_platform_key)
        os=$1 arch=$2
        case "$os" in
            linux|darwin) ;;
            *) fail "The $name native installation is unavailable on $os" ;;
        esac
        scratch=$(mktemp -d "$TMPDIR/$name.XXXXXX")
        manifest="$scratch/manifest.json"
        DEPLOY_STEP="install-agents.$name.manifest"
        curl -fsSL --retry 2 --connect-timeout 30 --max-time 300 \
            "$manifest_base/$version/manifest.json" -o "$manifest" ||
            fail "cannot download the pinned $name $version manifest"
        manifest_json=$(cat "$manifest")
        [ "$(manifest_string "$manifest_json" latest)" = "$version" ] ||
            fail "$name manifest does not advertise the pinned version $version"
        entry=$(printf '%s' "$manifest_json" | tr -d '\n\r\t ' |
            sed 's/},{/}\n{/g' | grep -F "\"os\":\"$os\"" |
            grep -F "\"arch\":\"$arch\"" | head -n1)
        [ -n "$entry" ] || fail "$name $version has no native binary for $os/$arch"
        url=$(manifest_string "$entry" url)
        checksum=$(manifest_string "$entry" sha256)
        case "$url" in https://*) ;; *) fail "$name archive must use HTTPS" ;; esac
        [ "${#checksum}" -eq 64 ] || fail "$name manifest is missing a valid SHA-256 for $os/$arch"
        case "$checksum" in *[!0-9a-f]*) fail "$name manifest has an invalid SHA-256 for $os/$arch" ;; esac
        archive="$scratch/${url##*/}"
        DEPLOY_STEP="install-agents.$name.download"
        download_verified "$url" "$archive" "$checksum"
        DEPLOY_STEP="install-agents.$name.extract"
        tar -xzf "$archive" -C "$scratch" || fail "cannot extract the $name archive"
        [ -f "$scratch/$binary" ] || fail "$name archive did not contain $binary"
        chmod 755 "$scratch/$binary"
        DEPLOY_STEP="install-agents.$name.verify"
        diagnostic=$("$scratch/$binary" --version) ||
            fail "downloaded $name did not report pinned version $version"
        agent_diagnostic_matches "$version" "$diagnostic" "$template" ||
            fail "downloaded $name did not report pinned version $version"
        DEPLOY_STEP="install-agents.$name.install"
        # The verified archive is the installed binary. Upstream's own
        # installer resolves its latest release and would place an unpinned
        # binary, so the deployment places the pinned one itself.
        mkdir -p "$root/bin/$binary"
        cp "$scratch/$binary" "$cli"
        chmod 755 "$cli"
        rm -rf "$scratch"
    fi
    mkdir -p "$HOME/.local/bin"
    # A vendor dispatcher may select another installed release. Both managed
    # commands use the verified pin while the device-owned dispatcher survives.
    IFS=, read -r -a exposed_commands <<< "$commands"
    for command in "${exposed_commands[@]}"; do
        agent_launcher "$HOME/.local/bin/$command" "$cli"
    done
    DEPLOY_STEP="install-agents.$name.diagnostic"
    for command in "${exposed_commands[@]}"; do
        diagnostic=$("$HOME/.local/bin/$command" --version)
        printf '%s\n' "$diagnostic"
        agent_diagnostic_matches "$version" "$diagnostic" "$template" ||
            fail "$command diagnostic did not report pinned version $version"
    done
}

# One attempt of a command that reaches the network can fail on its own.
agent_retry() {
    local attempts=3 attempt=1 status=1
    while [ "$attempt" -le "$attempts" ]; do
        # The call is guarded: a bare failing command would be ended by the
        # errexit the bootstrap runs with, before the status is captured and
        # the attempt can be retried.
        if "$@"; then
            status=0
        else
            status=$?
        fi
        [ "$status" -eq 0 ] && return 0
        attempt=$((attempt + 1))
        [ "$attempt" -le "$attempts" ] && sleep 3
    done
    return "$status"
}

# The Herdr integration kind of one agent. The provider catalog is the only
# source; an agent Herdr does not integrate has no kind at all.
agent_herdr_kind() {
    local name=$1 row kind=''
    for row in "${DEPLOY_AGENT_ROWS[@]}"; do
        agent_row_split "$row"
        [ "${AGENT_ROW[0]}" = "$name" ] || continue
        kind=${AGENT_ROW[10]}
        break
    done
    if [ "$kind" = '-' ]; then kind=''; fi
    printf '%s' "$kind"
    return 0
}

# The Herdr integration state of the selected agents, the generated skill, and
# the state files that record both. Herdr owns the integration bytes; the
# deployment only triggers its installer and verifies the result.
HERDR_KINDS=()
HERDR_AGENTS=()
HERDR_STATE_ROWS=()
HERDR_GENERATED_SKILLS=()

# The managed resume hook. Herdr rewrites the hook file when it reinstalls its
# codex integration, so the managed entry is registered again and placed last.
codex_herdr_register() {
    local hook="$HOME/.local/bin/dotfiles-codex-herdr"
    if [ ! -x "$hook" ]; then
        hook=$(command -v dotfiles-codex-herdr 2>/dev/null || true)
    fi
    [ -n "$hook" ] || fail 'the managed Codex resume hook installer is missing: dotfiles-codex-herdr'
    "$hook" install >/dev/null || fail 'cannot register the managed Codex resume hook'
}

# Herdr ships its own skill for the agents it drives. The deployment
# generates it into the shared tree and refreshes it when the installed
# binary changed; unchanged bytes are never rewritten.
herdr_generate_skill() {
    local herdr=$1 target="$HOME/.agents/skills/herdr/SKILL.md" directory temporary=''
    directory=${target%/*}
    if [ -n "$herdr" ]; then
        if temporary=$(mktemp "${TMPDIR:-/tmp}/herdr-skill.XXXXXX" 2>/dev/null) &&
            "$herdr" --skill > "$temporary" 2>/dev/null && [ -s "$temporary" ]; then
            # The generated skill belongs to the managed tree. A symlink at
            # the skill directory or at the file itself would carry the
            # write outside it, so the step refuses the path by name
            # instead of following the link.
            [ ! -L "$directory" ] || fail "the Herdr skill directory is a symlink: $directory"
            [ ! -L "$target" ] || fail "the Herdr skill file is a symlink: $target"
            if [ ! -f "$target" ] || ! cmp -s "$temporary" "$target"; then
                mkdir -p "$directory" || fail "cannot create the Herdr skill directory: $directory"
                cp "$temporary" "$target" || fail "cannot write the Herdr skill: $target"
                chmod 644 "$target" || fail "cannot set the permissions of the Herdr skill: $target"
            fi
        else
            printf 'dotfiles: Herdr did not produce a skill; skipped\n' >&2
        fi
        [ -z "$temporary" ] || rm -f "$temporary"
    fi
    # A generated skill belongs to no catalog row, so the pruning step reads
    # this record instead of the catalog to leave it alone.
    if [ -f "$target" ]; then
        HERDR_GENERATED_SKILLS+=("herdr|.agents/skills|herdr --skill")
    fi
    return 0
}

# The observed Herdr state of every selected agent that has a kind.
herdr_state_record() {
    local states=$1 kind state index name
    HERDR_STATE_ROWS=()
    while IFS='|' read -r kind state; do
        [ -n "$kind" ] || continue
        name=''
        for index in "${!HERDR_KINDS[@]}"; do
            if [ "${HERDR_KINDS[$index]}" = "$kind" ]; then
                name=${HERDR_AGENTS[$index]}
                break
            fi
        done
        [ -n "$name" ] || continue
        HERDR_STATE_ROWS+=("$name|$kind|$state")
    done <<< "$states"
}

# The Herdr state of the selected agents, recorded for the drift report.
herdr_state_write() {
    local state="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/herdr.tsv" staged row
    [ ! -L "${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles" ] || fail 'the agent state directory is a symlink'
    mkdir -p "$(dirname "$state")"
    [ ! -L "$state" ] || fail 'the Herdr state file is a symlink'
    staged=$(mktemp "$state.XXXXXX")
    {
        printf '# agent|kind|state\n'
        for row in ${HERDR_STATE_ROWS[@]+"${HERDR_STATE_ROWS[@]}"}; do
            printf '%s\n' "$row"
        done
    } > "$staged"
    mv -f "$staged" "$state"
}

# The generated skills the deployment owns. A generated skill comes from a
# tool installed on the device, not from the catalog, so the pruning step
# leaves it alone.
herdr_generated_skills_write() {
    local state="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/generated-skills.tsv" staged row
    [ ! -L "${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles" ] || fail 'the agent state directory is a symlink'
    mkdir -p "$(dirname "$state")"
    [ ! -L "$state" ] || fail 'the generated skill state file is a symlink'
    staged=$(mktemp "$state.XXXXXX")
    {
        printf '# name|root|generator\n'
        for row in ${HERDR_GENERATED_SKILLS[@]+"${HERDR_GENERATED_SKILLS[@]}"}; do
            printf '%s\n' "$row"
        done
    } > "$staged"
    mv -f "$staged" "$state"
}

# Install and repair Herdr's own integrations for the selected managed agents.
# The deployment never writes integration bytes and never touches an agent the
# selection does not own. Herdr absent leaves nothing to do. The generated
# skill belongs to no catalog row, so the agent selection does not gate it.
install_herdr_integrations() {
    local herdr helper name kind state installed=''
    local states=''
    herdr=$(command -v herdr 2>/dev/null || true)
    # The helper is the managed command the status report and the health
    # check read. The source tree holds the same bytes, so the deployment
    # runs it from there.
    helper="$DEPLOY_SOURCE/dot_local/bin/executable_dotfiles-herdr-status"
    if [ ! -f "$helper" ]; then
        helper="$HOME/.local/bin/dotfiles-herdr-status"
    fi
    [ -f "$helper" ] || fail 'the Herdr status helper is missing: dotfiles-herdr-status'
    HERDR_KINDS=()
    HERDR_AGENTS=()
    for name in "${DEPLOY_AGENT_ORDER[@]}"; do
        agent_selected "$name" || continue
        kind=$(agent_herdr_kind "$name")
        [ -n "$kind" ] || continue
        HERDR_KINDS+=("$kind")
        HERDR_AGENTS+=("$name")
    done
    if [ "${#HERDR_KINDS[@]}" -eq 0 ]; then
        printf 'dotfiles: no selected agent has a Herdr integration\n'
    else
        states=$(bash "$helper" "${HERDR_KINDS[@]}")
        while IFS='|' read -r kind state; do
            [ -n "$kind" ] || continue
            case "$state" in
                current) continue ;;
                unavailable) continue ;;
                unsupported)
                    printf 'dotfiles: Herdr does not support the %s integration; skipped\n' "$kind" >&2
                    continue ;;
            esac
            [ -n "$herdr" ] || continue
            DEPLOY_STEP="install-agents.herdr.$kind"
            "$herdr" integration install "$kind" || fail "cannot install the Herdr $kind integration"
            installed="$installed $kind"
        done <<< "$states"
        # The recorded state is the one the deployment left behind, so a
        # repaired integration is never reported as drift.
        if [ -n "$installed" ]; then
            states=$(bash "$helper" "${HERDR_KINDS[@]}")
        fi
        herdr_state_record "$states"
    fi
    # Every codex install or reinstall is followed by the managed resume-hook
    # registration, so the custom SessionStart entry stays last.
    case " $installed " in
        *' codex '*)
            DEPLOY_STEP=install-agents.herdr.codex-hook
            codex_herdr_register
            ;;
    esac
    # The generated skill belongs to the shared tree, not to the catalog, so
    # it is recorded even when Herdr is no longer installed.
    DEPLOY_STEP=install-agents.herdr.skill
    herdr_generate_skill "$herdr"
    # The state records the live drift, so the status report and the health
    # check read the same facts the deployment saw.
    DEPLOY_STEP=install-agents.herdr.state
    herdr_state_write
    herdr_generated_skills_write
}

# Worktrunk's client plugins report which worktree an agent is using. The
# plugin files are client state; the CLI owns their content, so they are
# installed through it instead of being written from this source.
install_worktrunk_plugins() {
    local wt="${DOTFILES_COMMON_BIN:-$PIXI_HOME/bin}/wt" client
    [ -x "$wt" ] || wt="$PIXI_HOME/bin/wt"
    [ -x "$wt" ] || return 0
    for client in claude codex opencode pi; do
        agent_selected "$client" || continue
        DEPLOY_STEP="install-agents.worktrunk.$client"
        agent_retry env PATH="$HOME/.local/bin:$PATH" "$wt" config plugins "$client" install --yes ||
            fail "cannot install the worktrunk plugin for $client"
    done
}

# Resolve the physical executable so an installer symlink remains separate
# from the two launchers we replace. Bound symlink traversal, including device
# loops.
agent_physical_path() {
    local candidate=$1 directory target hops=0
    while [ "$hops" -lt 40 ]; do
        directory=$(CDPATH= cd -P -- "$(dirname "$candidate")" 2>/dev/null && pwd -P) || return 1
        candidate="$directory/${candidate##*/}"
        if [ ! -L "$candidate" ]; then
            [ -f "$candidate" ] && [ -x "$candidate" ] || return 1
            printf '%s' "$candidate"
            return 0
        fi
        target=$(readlink "$candidate") || return 1
        case "$target" in /*) candidate=$target ;; *) candidate="$directory/$target" ;; esac
        hops=$((hops + 1))
    done
    return 1
}

# The device's own command for one name, outside the managed launchers, whose
# diagnostic reports the installer's version. The installer symlink is resolved
# so the launchers point at the executable the device provides.
agent_installer_command() {
    local command=$1 version=$2 template=$3
    local directory candidate diagnostic physical_home physical_bun
    local search_paths=()
    installer_native_target || return 1
    physical_home=$(CDPATH= cd -P -- "$HOME" && pwd -P) || return 1
    if [ -d "$BUN_INSTALL" ]; then
        physical_bun=$(CDPATH= cd -P -- "$BUN_INSTALL" && pwd -P) || return 1
    else
        physical_bun=$(CDPATH= cd -P -- "$(dirname "$BUN_INSTALL")" && pwd -P) || return 1
        physical_bun="$physical_bun/${BUN_INSTALL##*/}"
    fi
    IFS=: read -r -a search_paths <<< "$PATH"
    for directory in "${search_paths[@]}"; do
        case "$directory" in /*) ;; *) continue ;; esac
        candidate=$(agent_physical_path "$directory/$command") || continue
        case "$candidate" in
            "$physical_home/.local/bin/$command"|"$physical_bun/bin/$command"|"$physical_bun/managed/"*) continue ;;
        esac
        if LC_ALL=C head -c 160 "$candidate" 2>/dev/null | LC_ALL=C grep -Fq '# Managed by dotfiles'; then continue; fi
        diagnostic=$("$candidate" --version 2>/dev/null) || continue
        agent_diagnostic_matches "$version" "$diagnostic" "$template" floor || continue
        printf '%s' "$candidate"
        return 0
    done
    return 1
}

# The Homebrew command of one agent record. The device must already provide
# the package at or above the catalog floor, and the command must report the
# version the package carries. The deployment adopts that command; it never
# installs or upgrades a Homebrew package. A missing, below-floor, or removed
# package leaves the record unresolved so the chain falls through.
AGENT_HOME_BREW_COMMAND=''
AGENT_HOME_BREW_VERSION=''
agent_homebrew_command() {
    local floor=$1 kind=$2 package=$3 commands=$4 template=$5
    local brew version command candidate
    local exposed_commands=()
    IFS=, read -r -a exposed_commands <<< "$commands"
    command=${exposed_commands[0]}
    brew=$(installer_homebrew) || return 1
    version=$(installer_tool_version "$brew" "$kind" "$package") || return 1
    # A package revision is not part of the version the command reports.
    version=${version%%_*}
    installer_version_at_least "$version" "$floor" || return 1
    candidate=$(agent_installer_command "$command" "$version" "$template") || return 1
    AGENT_HOME_BREW_COMMAND=$candidate
    AGENT_HOME_BREW_VERSION=$version
    return 0
}

# The version of one dependency in a package manifest, read with the managed
# Node runtime. Prints nothing when the manifest is absent or unreadable.
agent_manifest_version() {
    local node=$1 manifest=$2 package=$3
    [ -f "$manifest" ] || return 0
    "$node" -e '
const fs = require("fs");
const [manifest, packageName] = process.argv.slice(1);
try {
    const parsed = JSON.parse(fs.readFileSync(manifest, "utf8"));
    const version = (parsed.dependencies || {})[packageName];
    if (typeof version === "string") { process.stdout.write(version); }
} catch (error) { }
' "$manifest" "$package"
}

# One package manifest with the device-owned version of its agent package.
agent_manifest_pin() {
    local node=$1 source=$2 destination=$3 package=$4 version=$5
    "$node" -e '
const fs = require("fs");
const [source, destination, packageName, version] = process.argv.slice(1);
const manifest = JSON.parse(fs.readFileSync(source, "utf8"));
const dependencies = manifest.dependencies || {};
if (!(packageName in dependencies)) { throw new Error("unknown package " + packageName); }
dependencies[packageName] = version;
manifest.dependencies = dependencies;
fs.writeFileSync(destination, JSON.stringify(manifest, null, 2) + "\n");
' "$source" "$destination" "$package" "$version"
}

# The device-owned project material of one overridden agent: its manifest and
# the lock that resolves it. The lock is generated once and reused, so every
# later install of that version stays frozen and identical.
agent_override_material() {
    local name=$1 package=$2 version=$3 bun=$4 node=$5
    local state_dir="$XDG_STATE_HOME/dotfiles/agents/$name"
    local scratch temporary declared
    mkdir -p "$state_dir"
    [ ! -L "$state_dir" ] || fail "the agent override state is a symlink: $state_dir"
    declared=$(agent_manifest_version "$node" "$state_dir/package.json" "$package")
    if [ "$declared" = "$version" ] && [ -f "$state_dir/bun.lock" ]; then
        return 0
    fi
    scratch=$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-agent-override.XXXXXX")
    if ! agent_manifest_pin "$node" "$DEPLOY_SOURCE/deployment/agents/$name/package.json" \
        "$scratch/package.json" "$package" "$version"; then
        rm -rf "$scratch"
        fail "cannot prepare the overridden manifest for $package"
    fi
    DEPLOY_STEP="install-agents.$name.override-lock"
    if ! agent_retry env npm_config_global=false pnpm_config_global=false npm_config_location=project \
        "$bun" install --cwd "$scratch" --lockfile-only --ignore-scripts; then
        rm -rf "$scratch"
        fail "cannot resolve the device-owned $name version $version"
    fi
    if [ ! -f "$scratch/bun.lock" ]; then
        rm -rf "$scratch"
        fail "Bun did not write the lock for the overridden $name"
    fi
    temporary=$(mktemp "$state_dir/.package.json.XXXXXX")
    cp "$scratch/package.json" "$temporary"
    mv -f "$temporary" "$state_dir/package.json"
    temporary=$(mktemp "$state_dir/.bun.lock.XXXXXX")
    cp "$scratch/bun.lock" "$temporary"
    mv -f "$temporary" "$state_dir/bun.lock"
    rm -rf "$scratch"
}

# Bun's global registry can keep a copy of a managed client, for example after
# an unsuccessful `bun add -g`. The managed launcher owns the command, so such
# a copy never runs; it only drifts from the pin. Report the leftover with the
# command that removes it instead of deleting a device-owned package.
agent_global_copy_warning() {
    local package=$1 node=$2 command=$3 manifest details version bins extra
    manifest="$BUN_INSTALL/install/global/node_modules/$package/package.json"
    [ -f "$manifest" ] || return 0
    details=$("$node" -e 'const fs=require("fs");try{const m=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));const b=m.bin||{};const names=typeof b==="string"?[require("path").basename(b)]:Object.keys(b);process.stdout.write(String(m.version||"")+"\t"+names.join(" "))}catch(e){}' "$manifest" 2>/dev/null) || details=''
    version=${details%%$'\t'*}
    bins=${details#*$'\t'}
    printf 'dotfiles: %s@%s is also installed in the Bun global registry; the managed launcher owns %s\n' \
        "$package" "${version:-unknown}" "$command"
    extra=''
    for bin in $bins; do
        [ "$bin" = "$command" ] && continue
        extra="$extra $bin"
    done
    if [ -n "$extra" ]; then
        printf 'dotfiles: the global copy also provides%s, which no managed launcher owns\n' "$extra"
    fi
    printf 'dotfiles: remove the leftover copy with: bun remove -g %s\n' "$package"
}

# The two managed launchers of one provider. The same selected executable is
# available to older shell PATHs.
agent_install_launchers() {
    local name=$1 version=$2 commands=$3 entrypoint_dir=$4 entrypoint_file=$5
    local comment=$6 node=$7 bun=$8 template=$9 policy=${10:-exact}
    local command launcher diagnostic entrypoint exposed_commands=()
    mkdir -p "$BUN_INSTALL/bin" "$HOME/.local/bin"
    IFS=, read -r -a exposed_commands <<< "$commands"
    for command in "${exposed_commands[@]}"; do
        launcher="$BUN_INSTALL/bin/$command"
        if [ -n "$entrypoint_file" ]; then
            entrypoint=$entrypoint_file
        else
            entrypoint="$entrypoint_dir/$command"
        fi
        [ -x "$entrypoint" ] || fail "$name did not expose $command"
        [ ! -L "$launcher" ] || rm "$launcher"
        {
            printf '#!/bin/sh\n# Managed by dotfiles; %s.\n' "$comment"
            printf 'PATH='; agent_shell_quote "$(dirname "$node"):$(dirname "$bun")"; printf ':"$PATH"\nexport PATH\n'
            printf 'exec '; agent_shell_quote "$entrypoint"; printf ' "$@"\n'
        } > "$launcher"
        chmod 755 "$launcher"
        # Omitted agents never reach this loop and retain their launchers.
        [ ! -L "$HOME/.local/bin/$command" ] || rm "$HOME/.local/bin/$command"
        cp "$launcher" "$HOME/.local/bin/$command"
        chmod 755 "$HOME/.local/bin/$command"
        DEPLOY_STEP="install-agents.$name.diagnostic"
        diagnostic=$("$launcher" --version)
        printf '%s\n' "$diagnostic"
        agent_diagnostic_matches "$version" "$diagnostic" "$template" "$policy" ||
            fail "$name diagnostic did not report version $version"
    done
}

# The frozen Bun project of one agent. The catalog record names the package,
# the lock, and the runtime floor.
install_bun_agent() {
    local name=$1 version=$2 catalog_version=$3 minimum=$4 package=$5 commands=$6
    local bun=$7 node=$8 node_version=$9
    local project command exposed_commands=()
    agent_version_at_least "${node_version#v}" "$minimum" ||
        fail "Node $node_version does not satisfy $name >=$minimum"
    project="$BUN_INSTALL/managed/$name"
    for command in "$project" "$project/node_modules" "$project/package.json" "$project/bun.lock"; do
        [ ! -L "$command" ] || fail "managed Bun project is a symlink: $command"
    done
    [ -f "$DEPLOY_SOURCE/deployment/agents/$name/bun.lock" ] || fail "missing supported Bun lock for $name"
    mkdir -p "$project" "$BUN_INSTALL/bin"
    if [ "$version" = "$catalog_version" ]; then
        cp "$DEPLOY_SOURCE/deployment/agents/$name/package.json" "$project/package.json"
        cp "$DEPLOY_SOURCE/deployment/agents/$name/bun.lock" "$project/bun.lock"
    else
        # The device owns this agent's version. Its manifest and lock are
        # generated once into device state, then installed frozen.
        agent_override_material "$name" "$package" "$version" "$bun" "$node"
        cp "$XDG_STATE_HOME/dotfiles/agents/$name/package.json" "$project/package.json"
        cp "$XDG_STATE_HOME/dotfiles/agents/$name/bun.lock" "$project/bun.lock"
    fi
    DEPLOY_STEP="install-agents.$name.install"
    # A registry hiccup should not abort the deployment; the lock file keeps
    # the result the same on every attempt.
    agent_retry env npm_config_global=false pnpm_config_global=false \
        npm_config_location=project "$bun" install --cwd "$project" --frozen-lockfile
    agent_install_launchers "$name" "$version" "$commands" "$project/node_modules/.bin" '' \
        "Bun installs the frozen project" "$node" "$bun" "-" exact
    IFS=, read -r -a exposed_commands <<< "$commands"
    agent_global_copy_warning "$package" "$node" "${exposed_commands[0]}"
}

# The observed provider and version of every selected agent. The state names
# what the device runs; the catalog stays the source of the plan. The floor is
# the lowest version the deployment accepts, so a deployment-owned provider
# records its exact pin there.
AGENT_STATE_ROWS=()
agent_state_record() {
    local name=$1 provider=$2 version=$3 floor=$4
    AGENT_STATE_ROWS+=("$name|$provider|$version|$floor")
}

agent_state_write() {
    local state="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/agents.lock.tsv" staged row
    [ ! -L "${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles" ] ||
        fail 'the agent state directory is a symlink'
    mkdir -p "$(dirname "$state")"
    [ ! -L "$state" ] || fail 'the agent state file is a symlink'
    staged=$(mktemp "$state.XXXXXX")
    for row in ${AGENT_STATE_ROWS[@]+"${AGENT_STATE_ROWS[@]}"}; do
        printf '%s\n' "$row" >> "$staged"
    done
    mv -f "$staged" "$state"
}

install_agents() {
    local common_bin="${DOTFILES_COMMON_BIN:-$PIXI_HOME/bin}"
    local bun="${DOTFILES_BUN_BIN:-$common_bin/bun}" node="${DOTFILES_NODE_BIN:-$common_bin/node}"
    if [ -z "${DOTFILES_BUN_BIN:-}" ] && [ ! -x "$bun" ]; then bun="$PIXI_HOME/bin/bun"; fi
    if [ -z "${DOTFILES_NODE_BIN:-}" ] && [ ! -x "$node" ]; then node="$PIXI_HOME/bin/node"; fi
    local bun_pin node_pin node_version name row provider commands package version catalog_version
    local minimum template installed claude_keep_plain_opus=0 package_kind=''
    local observed=''
    DEPLOY_STEP=install-agents.runtime
    case "$bun" in /*) ;; *) fail 'Bun binary override must be absolute' ;; esac
    case "$node" in /*) ;; *) fail 'Node binary override must be absolute' ;; esac
    bun_pin=$(agent_runtime_pin bun); node_pin=$(agent_runtime_pin nodejs)
    [ -x "$bun" ] || fail 'agent installation requires managed Bun; use common bootstrap first or DOTFILES_BUN_BIN'
    [ -x "$node" ] || fail 'agent installation requires managed Node; use common bootstrap first or DOTFILES_NODE_BIN'
    node_version=$("$node" --version)
    if [ "$DEPLOY_PLATFORM" = macos ]; then
        bun_pin=$(installer_common_minimum bun)
        node_pin=$(installer_common_minimum nodejs)
        agent_version_at_least "$("$bun" --version)" "$bun_pin" || fail "Bun must satisfy the common runtime floor $bun_pin"
        agent_version_at_least "${node_version#v}" "$node_pin" || fail "Node must satisfy the common runtime floor $node_pin"
    else
        [ "$("$bun" --version)" = "$bun_pin" ] || fail "Bun must match the common runtime pin $bun_pin"
        [ "$node_version" = "v$node_pin" ] || fail "Node must match the common runtime pin $node_pin"
    fi
    # JS package shebangs and lifecycle scripts run with the compatible Node.
    export PATH="$(dirname "$node"):$(dirname "$bun"):$PATH"
    if agent_selected claude; then
        DEPLOY_STEP=install-agents.claude.model-snapshot
        if client_claude_uses_plain_opus; then claude_keep_plain_opus=1; fi
    fi
    for name in "${DEPLOY_AGENT_ORDER[@]}"; do
        agent_selected "$name" || continue
        installed=''
        while IFS= read -r row; do
            [ -n "$row" ] || continue
            agent_row_split "$row"
            provider=${AGENT_ROW[1]}
            commands=${AGENT_ROW[6]}
            package=${AGENT_ROW[2]}
            package_kind=${AGENT_ROW[3]}
            minimum=${AGENT_ROW[11]}
            template=${AGENT_ROW[14]}
            catalog_version=${AGENT_ROW[4]}
            version=$(agent_effective_version "$name" "$catalog_version")
            case "$provider" in
                bun)
                    install_bun_agent "$name" "$version" "$catalog_version" "$minimum" "$package" "$commands" \
                        "$bun" "$node" "$node_version"
                    observed=$version
                    installed=1 ;;
                native)
                    install_native_release "$name" "$version" "$commands" "$package" "${AGENT_ROW[13]}" "$template"
                    observed=$version
                    installed=1 ;;
                homebrew)
                    DEPLOY_STEP="install-agents.$name.adopt"
                    # The device's Homebrew owns the installed version. The
                    # deployment adopts a package at or above the floor and
                    # never installs or upgrades one.
                    if agent_homebrew_command "$version" "$package_kind" "$package" "$commands" "$template"; then
                        printf 'dotfiles: adopted %s %s from %s\n' "$name" "$AGENT_HOME_BREW_VERSION" "$AGENT_HOME_BREW_COMMAND"
                        agent_install_launchers "$name" "$AGENT_HOME_BREW_VERSION" "$commands" '' "$AGENT_HOME_BREW_COMMAND" \
                            "Homebrew provides the command" "$node" "$bun" "$template" floor
                        observed=$AGENT_HOME_BREW_VERSION
                        installed=1
                    fi ;;
            esac
            if [ -n "$installed" ]; then
                agent_state_record "$name" "$provider" "$observed" "$catalog_version"
                break
            fi
        done <<< "$(agent_viable_rows "$name")"
        [ -n "$installed" ] || fail "no provider could supply the agent $name"
    done
    agent_state_write
    install_worktrunk_plugins
    # Herdr owns its integration bytes. The deployment triggers them for the
    # selected agents before the final client-settings merge, so the merge
    # preserves the entries Herdr added.
    DEPLOY_STEP=install-agents.herdr
    install_herdr_integrations
    # Client installers can add plugin settings in their own formatting. Finish
    # through the existing merger so the first and later applies agree.
    DEPLOY_STEP=install-agents.client-settings
    deploy_client_settings "$claude_keep_plain_opus"
}

agent_catalog_load
agent_herdr_kinds_load
validate_agent_catalog
resolve_agent_selection
