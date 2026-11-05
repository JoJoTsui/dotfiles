# Proxy provisioning for headless hosts. Mihomo is installed from a pinned
# release, the profile comes from the host's subscription secret, and the
# managed scripts under ~/.local/share/dotfiles/proxy own routing and supervision.
# Bash 3.2-compatible.

proxy_root() {
    printf '%s' "$HOME/.local/share/mihomo"
}

proxy_script_root() {
    printf '%s' "$HOME/.local/share/dotfiles/proxy"
}

proxy_pin() {
    local target=$1 name=$2 version=$3 wanted=$4 url=$5 sha=$6
    [ "$target" = "$wanted" ] || return 1
    [ -n "$version" ] && [ -n "$url" ] && [ -n "$sha" ] || return 1
    printf '%s|%s|%s' "$version" "$url" "$sha"
}

# The platform and architecture the deployment runs on, as the catalog keys it.
proxy_target() {
    case "$(uname -m)" in
        x86_64|amd64) printf 'amd64' ;;
        aarch64|arm64) printf 'arm64' ;;
        *) fail "unsupported proxy architecture: $(uname -m)" ;;
    esac
}

validate_proxy_catalog() {
    local name version target url sha seen=' '
    local catalog="$DEPLOY_SOURCE/deployment/proxy/mihomo.tsv"
    [ -f "$catalog" ] || fail 'proxy catalog is missing'
    [ ! -L "$catalog" ] || fail 'proxy catalog is a symlink'
    while IFS=$'|\r' read -r name version target url sha; do
        case "$name" in ''|\#*) continue ;; esac
        [ "$name" = mihomo ] || fail "unknown proxy package: $name"
        case "$version" in ''|*[!0-9.]*) fail "invalid proxy version: $version" ;; esac
        case "$target" in
            linux-amd64|linux-arm64|darwin-amd64|darwin-arm64) ;;
            *) fail "invalid proxy target: $target" ;;
        esac
        case " $seen " in *" $target "*) fail "duplicate proxy target: $target" ;; esac
        seen="$seen$target "
        case "$url" in https://*) ;; *) fail "proxy URL must use HTTPS: $target" ;; esac
        case "$sha" in *[!0-9a-f]*|'') fail "proxy digest must be lowercase SHA-256: $target" ;; esac
        [ "${#sha}" -eq 64 ] || fail "proxy digest must be 64 hex characters: $target"
    done < "$catalog"
}

proxy_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

install_proxy_binary() {
    local machine arch target pin version url sha root cache archive binary
    local catalog="$DEPLOY_SOURCE/deployment/proxy/mihomo.tsv"
    machine=$(uname -m)
    case "$machine" in
        x86_64|amd64) arch=amd64 ;;
        aarch64|arm64) arch=arm64 ;;
        *) fail "unsupported proxy architecture: $machine" ;;
    esac
    target="$DEPLOY_PLATFORM-$arch"
    # Bash 3.2 cannot parse a `case` inside a command substitution, so the
    # catalog row is selected with `if`.
    pin=$(while IFS=$'|\r' read -r _ version row_target url sha; do
        if [ "$row_target" = "$target" ]; then
            printf '%s|%s|%s' "$version" "$url" "$sha"
            break
        fi
    done < "$catalog")
    [ -n "$pin" ] || fail "proxy catalog has no row for $target"
    version=${pin%%|*}
    pin=${pin#*|}
    url=${pin%%|*}
    sha=${pin#*|}
    root=$(proxy_root)
    cache="$XDG_CACHE_HOME/dotfiles/mihomo"
    archive="$cache/mihomo-$version-$target.gz"
    binary="$root/bin/mihomo"
    if [ -x "$binary" ] && "$binary" -v 2>/dev/null | grep -q "v$version"; then
        return 0
    fi
    mkdir -p "$cache" "$root/bin" "$root/profiles"
    chmod 750 "$root" "$root/bin" "$root/profiles" 2>/dev/null || true
    if [ ! -s "$archive" ] || [ "$(proxy_sha256 "$archive")" != "$sha" ]; then
        rm -f "$archive.part"
        command -v curl >/dev/null 2>&1 || fail 'proxy installation requires curl'
        curl -fsSL --retry 2 --connect-timeout 10 --max-time 300 -o "$archive.part" "$url" ||
            fail "cannot download mihomo $version ($arch)"
        [ "$(proxy_sha256 "$archive.part")" = "$sha" ] || fail "mihomo digest mismatch: $arch"
        mv "$archive.part" "$archive"
    fi
    gzip -dc "$archive" > "$binary.part" || fail 'cannot decompress mihomo'
    chmod 750 "$binary.part"
    mv "$binary.part" "$binary"
    "$binary" -v || fail 'installed mihomo does not run'
}

refresh_proxy_profile() {
    local root secret script
    root=$(proxy_root)
    secret="$root/subscription-url"
    script="$(proxy_script_root)/scripts/refresh-profile.sh"
    [ -x "$script" ] || fail "proxy refresh script is missing: $script"
    [ -r "$secret" ] || fail "proxy subscription URL is missing: $secret (set MIHOMO_SUBSCRIPTION_URL at init)"
    case "$(head -c 32 "$secret" 2>/dev/null)" in
        REPLACE_ME*) fail "proxy subscription URL is still REPLACE_ME: $secret" ;;
    esac
    INSTALL_ROOT="$root" "$script"
}

# The deployment proxy is a process, not a service. It serves the downloads
# this run needs and stops when the run ends; the long-standing Mihomo
# service and any proxy client the user already runs are left alone.
DEPLOY_PROXY_URL=""
DEPLOY_PROXY_PID=""
DEPLOY_PROXY_PORT=""
DEPLOY_PROXY_PORTS="${DEPLOY_PROXY_PORTS:-7890 7891 7892 7893 7894}"
DEPLOY_PROXY_CONTROLLER_PORTS="${DEPLOY_PROXY_CONTROLLER_PORTS:-9091 9092 9093 9094 9095}"

# Whether a deployment section reaches the internet through the proxy. The
# rules live in deployment/proxy-policy.tsv so the choice is reviewed.
deploy_step_uses_proxy() {
    local section=$1 name proxy reason
    local policy="$DEPLOY_SOURCE/deployment/proxy-policy.tsv"
    [ -f "$policy" ] || return 1
    while IFS=$'|\r' read -r name proxy reason; do
        case "$name" in ''|\#*) continue ;; esac
        [ "$name" = "$section" ] || continue
        [ "$proxy" = yes ] && return 0
        return 1
    done < "$policy"
    return 1
}

# The policy must cover every step the bootstrap runs, so a new step cannot
# silently inherit or lose the proxy.
deploy_proxy_policy_complete() {
    local policy="$DEPLOY_SOURCE/deployment/proxy-policy.tsv" name proxy reason
    local missing=''
    [ -f "$policy" ] || fail 'proxy policy is missing'
    while IFS=$'|\r' read -r name proxy reason; do
        case "$name" in ''|\#*) continue ;; esac
        case "$proxy" in yes|no) ;; *) fail "invalid proxy policy for $name: $proxy" ;; esac
    done < "$policy"
    for name in $(grep -o 'run_step [a-z0-9.-]*' "$DEPLOY_SOURCE/bootstrap.sh" | awk '{print $2}' | sort -u); do
        grep -q "^$name|" "$policy" || missing="$missing $name"
    done
    [ -z "$missing" ] || fail "proxy policy does not cover: $missing"
}

# A port is free when nothing answers on it.
deploy_proxy_port_free() {
    ! (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

# A proxy client the user already runs (Clash Verge, a Mihomo core) owns the
# usual port. The deployment takes another one instead of fighting for it.
deploy_proxy_client_running() {
    pgrep -f 'Clash Verge' >/dev/null 2>&1 && return 0
    pgrep -x 'verge-mihomo' >/dev/null 2>&1 && return 0
    pgrep -x 'mihomo' >/dev/null 2>&1 && return 0
    return 1
}

# The first free port of a list.
deploy_proxy_first_free() {
    local port
    for port in "$@"; do
        if deploy_proxy_port_free "$port"; then
            printf '%s' "$port"
            return 0
        fi
    done
    return 1
}

# The deployment instance takes a port of its own. A proxy client that is
# running may claim the usual port at any moment, so the deployment leaves
# that one alone and takes the next free port.
deploy_proxy_choose_port() {
    local port first=true
    for port in $DEPLOY_PROXY_PORTS; do
        if $first && deploy_proxy_client_running; then
            first=false
            continue
        fi
        first=false
        if deploy_proxy_port_free "$port"; then
            printf '%s' "$port"
            return 0
        fi
    done
    return 1
}

# The instance configures itself through its own controller port, so it never
# talks to a proxy client or the long-standing service.
deploy_proxy_choose_controller() {
    deploy_proxy_first_free $DEPLOY_PROXY_CONTROLLER_PORTS
}

# The decision is reported once: the proxy is consulted by several steps.
deploy_proxy_report() {
    [ -z "${DEPLOY_PROXY_REPORTED:-}" ] || return 0
    DEPLOY_PROXY_REPORTED=1
    printf 'dotfiles: %s\n' "$*"
}

# The subscription is template data, never a file in git. It is materialised
# with the mode the source application gives it.
deploy_proxy_subscription() {
    local root secret
    root=$(proxy_root)
    secret="$root/subscription-url"
    if [ ! -s "$secret" ] && [ -n "${MIHOMO_SUBSCRIPTION_URL:-}" ]; then
        mkdir -p "$root"
        chmod 750 "$root" 2>/dev/null || true
        printf '%s' "$MIHOMO_SUBSCRIPTION_URL" > "$secret"
        chmod 600 "$secret"
    fi
    [ -s "$secret" ] || return 1
    case "$(head -c 32 "$secret" 2>/dev/null)" in
        REPLACE_ME*) return 1 ;;
    esac
    printf '%s' "$secret"
}

# The scripts that own the profile: the managed copy when the source is
# applied, the repository copy before that.
deploy_proxy_scripts() {
    local managed="$HOME/.local/share/dotfiles/proxy/scripts"
    local repo="$DEPLOY_SOURCE/dot_local/share/dotfiles/proxy/scripts"
    if [ -x "$managed/refresh-profile.sh" ]; then
        printf '%s' "$managed"
    elif [ -x "$repo/refresh-profile.sh" ]; then
        printf '%s' "$repo"
    else
        return 1
    fi
}

# The profile the deployment instance runs with. It is its own profile: the
# long-standing service keeps its own. The groups are narrowed to US leaves
# and the routing policy is applied, so the instance leaves the country the
# service chooses, and it listens on the ports this run owns.
deploy_proxy_profile() {
    local root scripts source target subscription
    root=$(proxy_root)
    scripts=$(deploy_proxy_scripts) || return 1
    source="$root/profiles/config.yaml"
    target="$root/profiles/deployment-config.yaml"
    subscription="$root/subscription-url"
    [ -s "$subscription" ] || return 1
    command -v python3 >/dev/null 2>&1 || return 1
    [ -x "$scripts/restrict-proxy-groups.py" ] || return 1
    [ -x "$scripts/apply-us-routing-policy.py" ] || return 1
    # Build the deployment profile in its own root, so the service profile is
    # left exactly as it is.
    mkdir -p "$root/deployment/profiles"
    INSTALL_ROOT="$root/deployment" SUBSCRIPTION_URL_FILE="$subscription" \
        "$scripts/refresh-profile.sh" >/dev/null 2>&1 || return 1
    source="$root/deployment/profiles/config.yaml"
    [ -s "$source" ] || return 1
    {
        printf 'external-controller: 127.0.0.1:%s\n' "$DEPLOY_PROXY_CONTROLLER_PORT"
        printf 'secret: ""\n'
        sed -e '/^external-controller:/d' -e '/^secret:/d' \
            -e "s/^mixed-port:.*/mixed-port: $DEPLOY_PROXY_PORT/" \
            -e "s/^port:.*/port: 0/" \
            -e "s/^socks-port:.*/socks-port: 0/" \
            "$source"
    } > "$target" || return 1
    chmod 600 "$target" 2>/dev/null || true
    printf '%s' "$target"
}

# Pin the GLOBAL group to a US leaf, the way the long-standing supervisor
# does, so the deployment proxy leaves the country the service chooses.
deploy_proxy_select_us_node() {
    local scripts=$1
    MIHOMO_CONTROLLER="http://127.0.0.1:$DEPLOY_PROXY_CONTROLLER_PORT" \
    MIHOMO_MODE=rule MIHOMO_PREFER_REGION=us MIHOMO_PREFER_SELECTOR=GLOBAL \
        python3 "$scripts/configure-mihomo.py" >/dev/null 2>&1
}

# Start the deployment instance, or reuse the one that is already running.
deploy_proxy_ensure() {
    local root binary profile port attempt secret
    [ -n "$DEPLOY_PROXY_URL" ] && return 0
    root=$(proxy_root)
    # An existing proxy answers on the first candidate port. Reusing it keeps
    # the deployment off the port a proxy client already owns.
    for port in $DEPLOY_PROXY_PORTS; do
        if ! deploy_proxy_port_free "$port"; then
            DEPLOY_PROXY_PORT="$port"
            DEPLOY_PROXY_URL="http://127.0.0.1:$port"
            if deploy_proxy_client_running; then
                deploy_proxy_report "a proxy client is already running on 127.0.0.1:$port; the deployment uses it"
            else
                deploy_proxy_report "a proxy is already running on 127.0.0.1:$port; the deployment uses it"
            fi
            return 0
        fi
    done
    secret=$(deploy_proxy_subscription) || {
        deploy_proxy_report 'no proxy subscription; the deployment downloads directly'
        return 0
    }
    DEPLOY_PROXY_PORT=$(deploy_proxy_choose_port) || {
        deploy_proxy_report 'no free proxy port; the deployment downloads directly'
        return 0
    }
    DEPLOY_PROXY_CONTROLLER_PORT=$(deploy_proxy_choose_controller) || {
        deploy_proxy_report 'no free controller port; the deployment downloads directly'
        return 0
    }
    if deploy_proxy_client_running; then
        deploy_proxy_report "a proxy client is running; the deployment proxy uses 127.0.0.1:$DEPLOY_PROXY_PORT"
    fi
    install_proxy_binary
    binary="$root/bin/mihomo"
    scripts=$(deploy_proxy_scripts) || {
        deploy_proxy_report 'the proxy scripts are missing; the deployment downloads directly'
        return 0
    }
    profile=$(deploy_proxy_profile) || {
        deploy_proxy_report 'cannot build a deployment profile; the deployment downloads directly'
        return 0
    }
    mkdir -p "$root/run"
    "$binary" -d "$root" -f "$profile" > "$root/run/deployment.log" 2>&1 &
    DEPLOY_PROXY_PID=$!
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        if ! deploy_proxy_port_free "$DEPLOY_PROXY_PORT"; then
            DEPLOY_PROXY_URL="http://127.0.0.1:$DEPLOY_PROXY_PORT"
            deploy_proxy_report "the deployment proxy is running on 127.0.0.1:$DEPLOY_PROXY_PORT"
            # The instance routes through US leaves, the same policy the
            # long-standing service uses.
            if deploy_proxy_select_us_node "$scripts"; then
                deploy_proxy_report 'the deployment proxy is pinned to a US node'
            else
                deploy_proxy_report 'the deployment proxy could not pin a US node'
            fi
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    stop_deployment_proxy
    deploy_proxy_report 'the deployment proxy did not start; the deployment downloads directly'
}

# The deployment proxy is a process: it stops with the deployment.
stop_deployment_proxy() {
    [ -n "$DEPLOY_PROXY_PID" ] || return 0
    kill "$DEPLOY_PROXY_PID" 2>/dev/null || true
    wait "$DEPLOY_PROXY_PID" 2>/dev/null || true
    DEPLOY_PROXY_PID=""
    DEPLOY_PROXY_URL=""
}

# The proxy environment for a section that needs one. Loopback never goes
# through it, so the local agent daemons stay reachable.
deploy_proxy_env_on() {
    [ -n "$DEPLOY_PROXY_URL" ] || return 0
    export http_proxy="$DEPLOY_PROXY_URL" https_proxy="$DEPLOY_PROXY_URL"
    export HTTP_PROXY="$DEPLOY_PROXY_URL" HTTPS_PROXY="$DEPLOY_PROXY_URL"
    export no_proxy="localhost,127.0.0.1,::1" NO_PROXY="localhost,127.0.0.1,::1"
}

deploy_proxy_env_off() {
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY
}

install_proxy() {
    case "$DEPLOY_PLATFORM" in
        linux|wsl) ;;
        *)
            fail 'the pinned Mihomo release is a Linux build; the proxy is not provisioned on this platform' ;;
    esac
    validate_proxy_catalog
    install_proxy_binary
    refresh_proxy_profile
    case "$DEPLOY_PLATFORM" in
        linux|wsl)
            printf 'dotfiles: proxy installed; start it with %s\n' \
                "$(proxy_script_root)/scripts/run-mihomo-supervised.sh"
            if command -v systemctl >/dev/null 2>&1 && systemctl --user is-system-running >/dev/null 2>&1; then
                printf 'dotfiles: user systemd is available; enable %s\n' 'systemctl --user enable --now mihomo.service'
            fi
            ;;
        *)
            printf 'dotfiles: proxy installed; run %s under a supervisor\n' \
                "$(proxy_script_root)/scripts/run-mihomo-supervised.sh"
            ;;
    esac
}
