# Declarations and installer functions only: sourcing this must never mutate
# files. Later tickets extend these adapters; bootstrap owns selection, state
# isolation, step failures, and working-tree source application.
# shellcheck disable=SC2034 # Plan arrays are consumed by the sourced caller.
DEPLOY_TOOLS=(chezmoi)
DEPLOY_ACTIONS=(install-managers apply-source install-common install-agents prepare-shell)

install_managers() {
    if [ -n "${DOTFILES_CHEZMOI_BIN:-}" ]; then
        [ -x "$DOTFILES_CHEZMOI_BIN" ] || fail 'DOTFILES_CHEZMOI_BIN is not executable'
        DEPLOY_CHEZMOI=$DOTFILES_CHEZMOI_BIN
        return
    fi
    DEPLOY_CHEZMOI="$HOME/.local/bin/chezmoi"
    [ ! -x "$DEPLOY_CHEZMOI" ] || return 0
    local version=2.72.2 asset_os asset_arch scratch
    case "$DEPLOY_PLATFORM" in
        linux|wsl) asset_os=linux ;;
        macos) asset_os=darwin ;;
        *) fail 'native Windows provisioning requires the PowerShell adapter' ;;
    esac
    case "$DEPLOY_ARCH" in x86_64) asset_arch=amd64 ;; aarch64) asset_arch=arm64 ;; esac
    scratch=$(mktemp -d "$TMPDIR/chezmoi.XXXXXX")
    curl -fsSL --retry 2 "https://github.com/twpayne/chezmoi/releases/download/v$version/chezmoi_${version}_${asset_os}_${asset_arch}.tar.gz" -o "$scratch/chezmoi.tar.gz"
    tar -xzf "$scratch/chezmoi.tar.gz" -C "$scratch" chezmoi
    cp "$scratch/chezmoi" "$DEPLOY_CHEZMOI"
    chmod 755 "$DEPLOY_CHEZMOI"
    rm -rf "$scratch"
}

# Fail rather than represent not-yet-implemented installation as success.
# Tickets 02 and 04 replace these adapters before complete bootstrap release.
install_common() { fail 'common-tool installation awaits ticket 02; use --apply-only for configuration validation'; }
install_agents() { fail 'agent installation awaits ticket 04'; }
prepare_shell() { :; }
