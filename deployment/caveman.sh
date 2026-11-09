# Historical gateway lifecycle reference; bootstrap no longer sources or calls it.
#
# The gateway reads ~/.caveman/caveman.yaml once at startup and publishes the
# mounts it finds in its run state, so a changed configuration needs a gateway
# restart before coding agents route through it. Hosts without Caveman keep
# their state: every step here is a no-op when the gateway is not installed.
#
# A restart repeats the settings of the running gateway (mode, listener and
# recovery), because the published state is the only record of them.
#
# Bash 3.2-compatible.

caveman_home() {
    printf '%s' "$HOME/.caveman"
}

# The gateway run state holds the published mounts and the listener address.
caveman_run_state() {
    local state
    for state in "$(caveman_home)"/run/*.json; do
        [ -f "$state" ] || continue
        printf '%s' "$state"
        return 0
    done
    return 1
}

# Read one scalar field from the gateway run state.
caveman_run_state_value() {
    local state=$1 field=$2
    sed -n -E "s/.*\"$field\":[[:space:]]*(\"[^\"]*\"|[A-Za-z0-9._-]+).*/\1/p" "$state" | head -1 | tr -d '"'
}

# The Caveman CLI is installed outside the shared PATH.
caveman_cli() {
    local candidate prefix
    if command -v caveman >/dev/null 2>&1; then
        command -v caveman
        return 0
    fi
    for candidate in "$HOME/.pixi/envs/nodejs/bin/caveman" "${CAVEMAN_CLI:-}"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        printf '%s' "$candidate"
        return 0
    done
    if command -v npm >/dev/null 2>&1; then
        prefix=$(npm prefix -g 2>/dev/null) || prefix=''
        if [ -n "$prefix" ] && [ -x "$prefix/bin/caveman" ]; then
            printf '%s' "$prefix/bin/caveman"
            return 0
        fi
    fi
    return 1
}

# The gateway binary the installer placed in the Caveman home.
caveman_proxy_binary() {
    local candidate
    for candidate in "${CAVEMAN_PROXY_BIN:-}" "$HOME/.caveman/bin/caveman-proxy"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        printf '%s' "$candidate"
        return 0
    done
    return 1
}

# Mount names declared by the managed gateway configuration. The managed
# source keeps one provider per line under `compat:`.
caveman_managed_mounts() {
    local source="$DEPLOY_SOURCE/deployment/client-settings/caveman.yaml"
    [ -f "$source" ] || return 1
    awk '/^compat:[[:space:]]*$/ { inside = 1; next }
         /^[^[:space:]#]/ { inside = 0 }
         inside && /^  [A-Za-z0-9._-]+:[[:space:]]*$/ {
             name = $0
             sub(/^  /, "", name)
             sub(/:[[:space:]]*$/, "", name)
             print name
         }' "$source"
}

# A running gateway lists the mounts it serves in its run state.
caveman_publishes_mounts() {
    local state=$1 mount mounts
    mounts=$(caveman_managed_mounts) || return 1
    for mount in $mounts; do
        grep -q "\"$mount\"" "$state" || return 1
    done
    return 0
}

# Stop the running gateway, preferring the graceful shutdown of the CLI.
caveman_stop_gateway() {
    local state=$1 pid cli
    cli=$(caveman_cli) || cli=''
    [ -n "$cli" ] && "$cli" stop >/dev/null 2>&1 || true
    sleep 1
    [ -f "$state" ] || return 0
    pid=$(caveman_run_state_value "$state" pid)
    case "$pid" in
        ''|*[!0-9]*) return 0 ;;
    esac
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    return 0
}

# The managed proxy payload is a Linux build, so macOS runs the gateway with
# the environment it inherits instead of pointing it at a port nothing serves.
# The Codex launcher makes the same choice on macOS.
caveman_gateway_proxy() {
    case "${DEPLOY_PLATFORM:-}" in
        macos) return 0 ;;
    esac
    [ -x "$HOME/.local/bin/with-proxy" ] || return 0
    printf '%s' "$HOME/.local/bin/with-proxy"
}

# Start the gateway with the settings of the instance it replaces. The proxy
# is a long-lived process, so it is detached from the deployment shell.
caveman_start_gateway() {
    local binary=$1 listen=$2 mode=$3 recovery=$4 home=$5 proxy
    proxy=$(caveman_gateway_proxy)
    if command -v setsid >/dev/null 2>&1; then
        setsid nohup ${proxy:+"$proxy"} env CAVEMAN_MODE="$mode" CAVEMAN_LISTEN="$listen" \
            CAVEMAN_RECOVERY="$recovery" CAVEMAN_PROXY_OWNER=start "$binary" \
            >> "$home/run/supervisor.log" 2>&1 < /dev/null &
    else
        nohup ${proxy:+"$proxy"} env CAVEMAN_MODE="$mode" CAVEMAN_LISTEN="$listen" \
            CAVEMAN_RECOVERY="$recovery" CAVEMAN_PROXY_OWNER=start "$binary" \
            >> "$home/run/supervisor.log" 2>&1 < /dev/null &
    fi
}

# Wait for a gateway run state that is not the one the restart replaced.
caveman_wait_for_gateway() {
    local before=$1 attempt=0 state
    while [ "$attempt" -lt 30 ]; do
        state=$(caveman_run_state) || state=''
        if [ -n "$state" ] && [ "$(cksum < "$state")" != "$before" ]; then
            printf '%s' "$state"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 1
}

# Restart the gateway when the managed configuration changed, so the mounts it
# publishes match the configuration on disk.
refresh_caveman_proxy() {
    local home config state before binary listen mode recovery
    home=$(caveman_home)
    config="$home/caveman.yaml"
    [ -f "$config" ] || return 0
    state=$(caveman_run_state) || return 0
    [ "$config" -nt "$state" ] || return 0
    binary=$(caveman_proxy_binary) || {
        printf 'dotfiles: %s changed; restart the Caveman gateway to publish it\n' "$config" >&2
        return 0
    }
    listen=$(caveman_run_state_value "$state" listen)
    [ -n "$listen" ] || listen='127.0.0.1:8787'
    mode=$(caveman_run_state_value "$state" mode)
    [ -n "$mode" ] || mode='compress'
    recovery=$(caveman_run_state_value "$state" recovery_via_mcp)
    [ "$recovery" = 'true' ] && recovery='mcp' || recovery=''
    before=$(cksum < "$state")
    printf 'dotfiles: restarting the Caveman gateway to publish the managed mounts\n'
    caveman_stop_gateway "$state"
    caveman_start_gateway "$binary" "$listen" "$mode" "$recovery" "$home"
    if ! state=$(caveman_wait_for_gateway "$before"); then
        printf 'dotfiles: the Caveman gateway did not restart; run: %s\n' \
            "CAVEMAN_MODE=$mode CAVEMAN_LISTEN=$listen $binary" >&2
        return 0
    fi
    if ! caveman_publishes_mounts "$state"; then
        printf 'dotfiles: the Caveman gateway does not publish the managed mounts; check %s\n' "$config" >&2
    fi
}
