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

resolve_agent_selection() {
    local selection="${DOTFILES_AGENTS:-all}" requested canonical found item name package version commands minimum trusted
    local requested_agents=() normalized=()
    if "$CLI_AGENTS_SET"; then selection=$CLI_AGENTS; fi
    case "$selection" in
        all) normalized=(kimi pi opencode claude codex) ;;
        none) ;;
        ''|,*|*,|*,,*) fail 'invalid agent selection: use all, none, or a comma-separated named list' ;;
        *)
            IFS=, read -r -a requested_agents <<< "$selection"
            for requested in "${requested_agents[@]}"; do
                case "$requested" in
                    kimi|kimi-code) canonical=kimi ;;
                    pi|opencode|codex) canonical=$requested ;;
                    claude|claude-code) canonical=claude ;;
                    *) fail "unknown agent: $requested (choose kimi, pi, opencode, claude, codex)" ;;
                esac
                normalized+=("$canonical")
            done ;;
    esac
    # Stable catalog ordering deduplicates aliases and repeated names.
    while IFS='|' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*|codegraph) continue ;; esac
        for item in ${normalized[@]+"${normalized[@]}"}; do
            if [ "$item" = "$name" ]; then DEPLOY_AGENTS+=("$name"); break; fi
        done
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    while IFS='|' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        IFS=, read -r -a requested_agents <<< "$commands"
        DEPLOY_TOOLS+=("${requested_agents[@]}")
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
}
resolve_agent_selection

print_agent_packages() {
    local name package version commands minimum trusted separator=''
    printf '['
    while IFS='|' read -r name package version commands minimum trusted; do
        case "$name" in ''|\#*) continue ;; esac
        agent_selected "$name" || continue
        printf '%s{"name":' "$separator"; json_string "$name"
        printf ',"package":'; json_string "$package"
        printf ',"version":'; json_string "$version"
        printf ',"manager":"bun","minimumNode":'; json_string "$minimum"
        printf ',"lock":'; json_string "deployment/agents/$name/bun.lock"
        printf '}'; separator=,
    done < "$DEPLOY_SOURCE/deployment/agents/catalog.tsv"
    printf ']'
}

agent_runtime_pin() {
    local environment specifications commands targets item
    local runtime_specs=()
    while IFS='|' read -r environment specifications commands targets; do
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
    while IFS='|' read -r name package version commands minimum trusted; do
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
}
