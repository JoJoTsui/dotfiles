# Bun project ownership and public plan metadata. Sourcing is read-only.
DEPLOY_AGENTS=()

agent_selected() {
    [ "$1" != codegraph ] || return 0
    local selected
    for selected in ${DEPLOY_AGENTS[@]+"${DEPLOY_AGENTS[@]}"}; do
        [ "$selected" != "$1" ] || return 0
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

resolve_agent_selection() {
    local selection="${DOTFILES_AGENTS:-all}" requested canonical item name package version commands minimum trusted platforms manifest
    local requested_agents=() normalized=()
    DEPLOY_AGENT_NAMES=()
    if "$CLI_AGENTS_SET"; then selection=$CLI_AGENTS; fi
    # Catalog order is the public installation and plan order.
    while IFS=$'|\r' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*|codegraph) continue ;; esac
        DEPLOY_AGENT_NAMES+=("$name")
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    while IFS=$'|\r' read -r name version commands platforms manifest; do
        case "$name" in ''|\#*) continue ;; esac
        DEPLOY_AGENT_NAMES+=("$name")
    done < "$DEPLOY_SOURCE/deployment/agents/native.tsv"
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
    while IFS=$'|\r' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*|codegraph) continue ;; esac
        for item in ${normalized[@]+"${normalized[@]}"}; do
            if [ "$item" = "$name" ]; then DEPLOY_AGENTS+=("$name"); break; fi
        done
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    while IFS=$'|\r' read -r name version commands platforms manifest; do
        case "$name" in ''|\#*) continue ;; esac
        for item in ${normalized[@]+"${normalized[@]}"}; do
            if [ "$item" = "$name" ]; then DEPLOY_AGENTS+=("$name"); break; fi
        done
    done < "$DEPLOY_SOURCE/deployment/agents/native.tsv"
    while IFS=$'|\r' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        IFS=, read -r -a requested_agents <<< "$commands"
        DEPLOY_TOOLS+=("${requested_agents[@]}")
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    while IFS=$'|\r' read -r name version commands platforms manifest; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        IFS=, read -r -a requested_agents <<< "$commands"
        DEPLOY_TOOLS+=("${requested_agents[@]}")
    done < "$DEPLOY_SOURCE/deployment/agents/native.tsv"
}
resolve_agent_selection

print_agent_packages() {
    local name package version commands minimum trusted platforms manifest separator='' command
    local exposed_commands=()
    printf '['
    while IFS=$'|\r' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        IFS=, read -r -a exposed_commands <<< "$commands"
        printf '%s{"name":' "$separator"; json_string "$name"
        printf ',"package":'; json_string "$package"
        printf ',"version":'; json_string "$version"
        printf ',"manager":"bun","commands":['
        local first=''
        for command in "${exposed_commands[@]}"; do
            printf '%s' "$first"; json_string "$command"; first=,
        done
        printf '],"minimumNode":'; json_string "$minimum"
        printf ',"lock":'; json_string "deployment/agents/$name/bun.lock"
        printf '}'; separator=,
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    while IFS=$'|\r' read -r name version commands platforms manifest; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        IFS=, read -r -a exposed_commands <<< "$commands"
        printf '%s{"name":' "$separator"; json_string "$name"
        printf ',"package":null'
        printf ',"version":'; json_string "$version"
        printf ',"manager":"native","commands":['
        local first=''
        for command in "${exposed_commands[@]}"; do
            printf '%s' "$first"; json_string "$command"; first=,
        done
        printf '],"manifest":'; json_string "$manifest"
        printf '}'; separator=,
    done < "$DEPLOY_SOURCE/deployment/agents/native.tsv"
    printf ']'
}

agent_runtime_pin() {
    local environment specifications commands targets item
    local runtime_specs=()
    while IFS=$'|\r' read -r environment specifications commands targets; do
        case "$environment" in ''|\#*) continue ;; esac
        IFS=, read -r -a runtime_specs <<< "$specifications"
        for item in "${runtime_specs[@]}"; do
            if [ "${item%%==*}" = "$1" ]; then printf '%s' "${item#*==}"; return; fi
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

# The upstream Qoder launcher carries OS/CPU feature selection. Reuse its
# published manifest and verify the archive digest before executing the
# extracted installer binary; the remote install script itself is not executed.
qoder_platform_key() {
    local os arch
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m)
    if [ "$os" = darwin ] && [ "$arch" = x86_64 ] &&
        [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then
        arch=arm64
    fi
    [ "$arch" = aarch64 ] && arch=arm64
    [ "$arch" = x86_64 ] && arch=amd64
    # Bun's optimized Linux x64 build needs the same flags as upstream.
    if [ "$os" = linux ] && [ "$arch" = amd64 ] && ! qoder_cpu_has_flags; then
        arch=amd64-baseline
    fi
    printf '%s %s' "$os" "$arch"
}

qoder_cpu_has_flags() {
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

install_qoder() {
    local version=$1 manifest_base=$2 root cli entry manifest archive scratch url checksum os arch
    local manifest_json=''
    root="$HOME/.qoder"
    cli="$root/bin/qodercli/qodercli-$version"
    if [ ! -x "$cli" ] || [ "$("$cli" --version 2>/dev/null || true)" != "$version" ]; then
        set -- $(qoder_platform_key)
        os=$1 arch=$2
        case "$os" in
            linux|darwin) ;;
            *) fail "Qoder native installation is unavailable on $os" ;;
        esac
        scratch=$(mktemp -d "$TMPDIR/qoder.XXXXXX")
        manifest="$scratch/manifest.json"
        DEPLOY_STEP='install-agents.qoder.manifest'
        curl -fsSL --retry 2 --connect-timeout 30 --max-time 300 \
            "$manifest_base/$version/manifest.json" -o "$manifest" ||
            fail "cannot download the pinned Qoder $version manifest"
        manifest_json=$(cat "$manifest")
        [ "$(manifest_string "$manifest_json" latest)" = "$version" ] ||
            fail "Qoder manifest does not advertise the pinned version $version"
        entry=$(printf '%s' "$manifest_json" | tr -d '\n\r\t ' |
            sed 's/},{/}\n{/g' | grep -F "\"os\":\"$os\"" |
            grep -F "\"arch\":\"$arch\"" | head -n1)
        [ -n "$entry" ] || fail "Qoder $version has no native binary for $os/$arch"
        url=$(manifest_string "$entry" url)
        checksum=$(manifest_string "$entry" sha256)
        case "$url" in https://*) ;; *) fail 'Qoder archive must use HTTPS' ;; esac
        [ "${#checksum}" -eq 64 ] || fail "Qoder manifest is missing a valid SHA-256 for $os/$arch"
        case "$checksum" in *[!0-9a-f]*) fail "Qoder manifest has an invalid SHA-256 for $os/$arch" ;; esac
        archive="$scratch/${url##*/}"
        DEPLOY_STEP='install-agents.qoder.download'
        download_verified "$url" "$archive" "$checksum"
        DEPLOY_STEP='install-agents.qoder.extract'
        tar -xzf "$archive" -C "$scratch" || fail 'cannot extract the Qoder archive'
        [ -f "$scratch/qodercli" ] || fail 'Qoder archive did not contain qodercli'
        chmod 755 "$scratch/qodercli"
        DEPLOY_STEP='install-agents.qoder.install'
        # The binary's own installer owns versioned placement and entry-point
        # creation; PATH changes stay with the managed deployment.
        "$scratch/qodercli" install --force --skip-path
        [ -x "$cli" ] || fail "Qoder installation did not place $cli"
        rm -rf "$scratch"
    fi
    mkdir -p "$HOME/.local/bin"
    agent_launcher "$HOME/.local/bin/qodercli" "$cli"
    if [ -x "$root/entry/qoder" ]; then
        agent_launcher "$HOME/.local/bin/qoder" "$root/entry/qoder"
    else
        agent_launcher "$HOME/.local/bin/qoder" "$cli"
    fi
    DEPLOY_STEP='install-agents.qoder.diagnostic'
    diagnostic=$("$HOME/.local/bin/qodercli" --version)
    printf '%s\n' "$diagnostic"
    case "$diagnostic" in
        *"$version"*) ;;
        *) fail "qoder diagnostic did not report pinned version $version" ;;
    esac
}

install_native_agents() {
    local name version commands platforms manifest_base
    while IFS=$'|\r' read -r name version commands platforms manifest_base; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        agent_platform_matches "$platforms" || continue
        case "$name" in
            qoder) install_qoder "$version" "$manifest_base" ;;
            *) fail "unsupported native agent: $name" ;;
        esac
    done < "$DEPLOY_SOURCE/deployment/agents/native.tsv"
}

install_agents() {
    local bun="${DOTFILES_BUN_BIN:-$PIXI_HOME/bin/bun}" node="${DOTFILES_NODE_BIN:-$PIXI_HOME/bin/node}"
    local bun_pin node_pin name package version commands minimum trusted project command launcher diagnostic
    local exposed_commands=()
    DEPLOY_STEP=install-agents.runtime
    case "$bun" in /*) ;; *) fail 'Bun binary override must be absolute' ;; esac
    case "$node" in /*) ;; *) fail 'Node binary override must be absolute' ;; esac
    bun_pin=$(agent_runtime_pin bun); node_pin=$(agent_runtime_pin nodejs)
    [ -x "$bun" ] || fail 'agent installation requires managed Bun; use common bootstrap first or DOTFILES_BUN_BIN'
    [ -x "$node" ] || fail 'agent installation requires managed Node; use common bootstrap first or DOTFILES_NODE_BIN'
    [ "$("$bun" --version)" = "$bun_pin" ] || fail "Bun must match the common runtime pin $bun_pin"
    [ "$("$node" --version)" = "v$node_pin" ] || fail "Node must match the common runtime pin $node_pin"
    # JS package shebangs and lifecycle scripts run with the compatible Node.
    export PATH="$(dirname "$node"):$(dirname "$bun"):$PATH"
    while IFS=$'|\r' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        agent_version_at_least "$node_pin" "$minimum" || fail "Node $node_pin does not satisfy $name >=$minimum"
        project="$BUN_INSTALL/managed/$name"
        for command in "$project" "$project/node_modules" "$project/package.json" "$project/bun.lock"; do
            [ ! -L "$command" ] || fail "managed Bun project is a symlink: $command"
        done
        [ -f "$DEPLOY_SOURCE/deployment/agents/$name/bun.lock" ] || fail "missing supported Bun lock for $name"
        mkdir -p "$project" "$BUN_INSTALL/bin"
        cp "$DEPLOY_SOURCE/deployment/agents/$name/package.json" "$project/package.json"
        cp "$DEPLOY_SOURCE/deployment/agents/$name/bun.lock" "$project/bun.lock"
        DEPLOY_STEP="install-agents.$name.install"
        npm_config_global=false pnpm_config_global=false npm_config_location=project "$bun" install --cwd "$project" --frozen-lockfile
        IFS=, read -r -a exposed_commands <<< "$commands"
        for command in "${exposed_commands[@]}"; do
            launcher="$BUN_INSTALL/bin/$command"
            [ -x "$project/node_modules/.bin/$command" ] || fail "$name did not expose $command"
            [ ! -L "$launcher" ] || rm "$launcher"
            {
                printf '#!/bin/sh\n# Managed by dotfiles; Bun installs the frozen project.\n'
                printf 'PATH='; agent_shell_quote "$(dirname "$node"):$(dirname "$bun")"; printf ':"$PATH"\nexport PATH\n'
                printf 'exec '; agent_shell_quote "$project/node_modules/.bin/$command"; printf ' "$@"\n'
            } > "$launcher"
            chmod 755 "$launcher"
            # The same Bun-owned project is available to older shell PATHs.
            # Omitted agents never reach this loop and retain their launchers.
            [ ! -L "$HOME/.local/bin/$command" ] || rm "$HOME/.local/bin/$command"
            cp "$launcher" "$HOME/.local/bin/$command"
            chmod 755 "$HOME/.local/bin/$command"
            DEPLOY_STEP="install-agents.$name.diagnostic"
            diagnostic=$("$launcher" --version)
            printf '%s\n' "$diagnostic"
            case "$diagnostic" in *"$version"*) ;; *) fail "$name diagnostic did not report pinned version $version" ;; esac
        done
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    install_native_agents
}
