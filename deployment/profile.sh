# Profile selection; no filesystem mutation, package installation, or auth.
# Sourced by bootstrap.sh; keep compatible with the system Bash 3.2 on macOS.
# shellcheck disable=SC2034 # Variables are the sourced bootstrap adapter contract.

parse_profile() {
    case "$1" in
        t9k) PROFILE_PLATFORM=linux; PROFILE_ROLE=remote-compute ;;
        linux-workstation|linux-remote-compute|macos-workstation|macos-remote-compute|wsl-workstation|wsl-remote-compute|windows-workstation|windows-remote-compute)
            PROFILE_PLATFORM=${1%%-*}; PROFILE_ROLE=${1#*-} ;;
        *) fail "invalid profile '$1'; use <linux|macos|wsl|windows>-<workstation|remote-compute> or t9k" ;;
    esac
}

parse_class() {
    case "$1" in
        t9k) parse_profile t9k ;;
        linux) parse_profile linux-workstation ;;
        win) parse_profile windows-workstation ;;
        *) fail "invalid legacy class '$1'; use t9k, linux, or win" ;;
    esac
}

detect_platform() {
    case "$(uname -s)" in
        Linux)
            if [ -n "${WSL_DISTRO_NAME:-}${WSL_INTEROP:-}" ] || [[ "$(uname -r)" = *[Mm]icrosoft* ]]; then
                printf 'wsl'
            else
                printf 'linux'
            fi ;;
        Darwin) printf 'macos' ;;
        MINGW*|MSYS*|CYGWIN*) printf 'windows' ;;
        *) fail 'cannot detect platform; select --platform explicitly' ;;
    esac
}

resolve_profile() {
    DEPLOY_PLATFORM=''
    DEPLOY_ROLE=workstation
    if [ -n "${DOTFILES_CLASS:-}" ]; then
        parse_class "$DOTFILES_CLASS"
        DEPLOY_PLATFORM=$PROFILE_PLATFORM; DEPLOY_ROLE=$PROFILE_ROLE
    fi
    if [ -n "${DOTFILES_PROFILE:-}" ]; then
        parse_profile "$DOTFILES_PROFILE"
        if [ -n "${DOTFILES_CLASS:-}" ] && [ "$DEPLOY_PLATFORM-$DEPLOY_ROLE" != "$PROFILE_PLATFORM-$PROFILE_ROLE" ]; then
            fail 'conflicting DOTFILES_PROFILE and DOTFILES_CLASS'
        fi
        DEPLOY_PLATFORM=$PROFILE_PLATFORM; DEPLOY_ROLE=$PROFILE_ROLE
    fi
    DEPLOY_PLATFORM="${DOTFILES_PLATFORM:-$DEPLOY_PLATFORM}"
    DEPLOY_ROLE="${DOTFILES_ROLE:-$DEPLOY_ROLE}"
    if [ -n "$CLI_CLASS" ]; then
        parse_class "$CLI_CLASS"
        DEPLOY_PLATFORM=$PROFILE_PLATFORM; DEPLOY_ROLE=$PROFILE_ROLE
    fi
    if [ -n "$CLI_PROFILE" ]; then
        parse_profile "$CLI_PROFILE"
        if [ -n "$CLI_CLASS" ] && [ "$DEPLOY_PLATFORM-$DEPLOY_ROLE" != "$PROFILE_PLATFORM-$PROFILE_ROLE" ]; then
            fail 'conflicting --profile and --class'
        fi
        DEPLOY_PLATFORM=$PROFILE_PLATFORM; DEPLOY_ROLE=$PROFILE_ROLE
    fi
    if [ -n "$CLI_CLASS$CLI_PROFILE" ]; then
        [ -z "$CLI_PLATFORM" ] || [ "$CLI_PLATFORM" = "$DEPLOY_PLATFORM" ] || fail 'conflicting platform and profile/class selections'
        [ -z "$CLI_ROLE" ] || [ "$CLI_ROLE" = "$DEPLOY_ROLE" ] || fail 'conflicting role and profile/class selections'
    fi
    DEPLOY_PLATFORM="${CLI_PLATFORM:-$DEPLOY_PLATFORM}"
    DEPLOY_ROLE="${CLI_ROLE:-$DEPLOY_ROLE}"
    if [ -z "$DEPLOY_PLATFORM" ]; then DEPLOY_PLATFORM="$(detect_platform)"; fi
    case "$DEPLOY_PLATFORM" in linux|macos|wsl|windows) ;; *) fail "invalid platform '$DEPLOY_PLATFORM'" ;; esac
    case "$DEPLOY_ROLE" in workstation|remote-compute) ;; *) fail "invalid role '$DEPLOY_ROLE'" ;; esac
    DEPLOY_ARCH="${CLI_ARCH:-${DOTFILES_ARCH:-$(uname -m)}}"
    case "$DEPLOY_ARCH" in
        x86_64|amd64) DEPLOY_ARCH=x86_64 ;;
        arm64|aarch64) DEPLOY_ARCH=aarch64 ;;
        *) fail "unsupported architecture '$DEPLOY_ARCH'" ;;
    esac
    [ "$DEPLOY_PLATFORM-$DEPLOY_ARCH" != windows-aarch64 ] || fail 'Windows ARM is outside the supported architecture matrix'
    DEPLOY_PROFILE="$DEPLOY_PLATFORM-$DEPLOY_ROLE"
    DEPLOY_MIRROR=${DOTFILES_MIRROR:-tuna}
    case "$DEPLOY_MIRROR" in tuna|upstream) ;; *) fail 'invalid DOTFILES_MIRROR; use tuna or upstream' ;; esac
    case "$DEPLOY_PROFILE" in
        linux-remote-compute) DEPLOY_CLASS=t9k ;;
        windows-*) DEPLOY_CLASS=win ;;
        *) DEPLOY_CLASS=linux ;;
    esac
}
