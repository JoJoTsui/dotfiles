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
    local arch=$1 name=$2 version=$3 arch_name=$4 url=$5 sha=$6
    [ "$arch" = "$arch_name" ] || return 1
    [ -n "$version" ] && [ -n "$url" ] && [ -n "$sha" ] || return 1
    printf '%s|%s|%s' "$version" "$url" "$sha"
}

validate_proxy_catalog() {
    local name version arch url sha seen=' '
    local catalog="$DEPLOY_SOURCE/deployment/proxy/mihomo.tsv"
    [ -f "$catalog" ] || fail 'proxy catalog is missing'
    [ ! -L "$catalog" ] || fail 'proxy catalog is a symlink'
    while IFS=$'|\r' read -r name version arch url sha; do
        case "$name" in ''|\#*) continue ;; esac
        [ "$name" = mihomo ] || fail "unknown proxy package: $name"
        case "$version" in ''|*[!0-9.]*) fail "invalid proxy version: $version" ;; esac
        case "$arch" in amd64|arm64) ;; *) fail "invalid proxy arch: $arch" ;; esac
        case " $seen " in *" $arch "*) fail "duplicate proxy arch: $arch" ;; esac
        seen="$seen$arch "
        case "$url" in https://*) ;; *) fail "proxy URL must use HTTPS: $arch" ;; esac
        case "$sha" in *[!0-9a-f]*|'') fail "proxy digest must be lowercase SHA-256: $arch" ;; esac
        [ "${#sha}" -eq 64 ] || fail "proxy digest must be 64 hex characters: $arch"
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
    local machine arch pin version url sha root cache archive binary
    local catalog="$DEPLOY_SOURCE/deployment/proxy/mihomo.tsv"
    machine=$(uname -m)
    case "$machine" in
        x86_64|amd64) arch=amd64 ;;
        aarch64|arm64) arch=arm64 ;;
        *) fail "unsupported proxy architecture: $machine" ;;
    esac
    pin=$(while IFS=$'|\r' read -r _ version row_arch url sha; do
        case "$row_arch" in "$arch") printf '%s|%s|%s' "$version" "$url" "$sha"; break ;; esac
    done < "$catalog")
    [ -n "$pin" ] || fail "proxy catalog has no row for $arch"
    version=${pin%%|*}
    pin=${pin#*|}
    url=${pin%%|*}
    sha=${pin#*|}
    root=$(proxy_root)
    cache="$XDG_CACHE_HOME/dotfiles/mihomo"
    archive="$cache/mihomo-$version-$arch.gz"
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

install_proxy() {
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
