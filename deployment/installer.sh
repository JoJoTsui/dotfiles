# Installer-owned commands. The tier provides what the package catalog cannot:
# Homebrew formulas and casks. Homebrew is adopted from the device; this
# deployment never installs it, and a device without it falls through to the
# next installer in the order.
# shellcheck shell=bash
# shellcheck disable=SC2034 # Public bootstrap adapter data.

INSTALLER_CATALOG="$DEPLOY_SOURCE/deployment/installer-tools.tsv"
DEPLOY_INSTALLER_TOOLS=()

installer_tool_matches() {
    [ "$1" = all ] || { case ",$1," in *",$DEPLOY_PLATFORM,"*) return 0 ;; *) return 1 ;; esac; }
}

# The Homebrew the device already has. The deployment adopts the Homebrew the
# device's PATH resolves; it never installs Homebrew itself.
installer_homebrew() {
    local candidate
    for candidate in "${DOTFILES_HOMEBREW_BIN:-}" "$(command -v brew 2>/dev/null || true)"; do
        [ -n "$candidate" ] || continue
        [ -x "$candidate" ] || continue
        printf '%s' "$candidate"
        return 0
    done
    return 1
}

# Version floors are compared numerically, major to minor to patch.
installer_version_at_least() {
    local have=$1 want=$2 have_major want_major have_minor want_minor have_patch want_patch
    have_major=${have%%.*}; want_major=${want%%.*}
    have_minor=${have#*.}; have_minor=${have_minor%%.*}
    want_minor=${want#*.}; want_minor=${want_minor%%.*}
    have_patch=${have##*.}; want_patch=${want##*.}
    case "$have_major$want_major$have_minor$want_minor$have_patch$want_patch" in
        *[!0-9]*) return 1 ;;
    esac
    [ "$have_major" -gt "$want_major" ] && return 0
    [ "$have_major" -lt "$want_major" ] && return 1
    [ "$have_minor" -gt "$want_minor" ] && return 0
    [ "$have_minor" -lt "$want_minor" ] && return 1
    [ "$have_patch" -ge "$want_patch" ]
}

installer_tool_version() {
    local brew=$1 kind=$2 package=$3 listing
    case "$kind" in
        cask) listing=$("$brew" list --cask --versions "$package" 2>/dev/null) ;;
        formula) listing=$("$brew" list --versions "$package" 2>/dev/null) ;;
        *) return 1 ;;
    esac
    [ -n "$listing" ] || return 1
    printf '%s' "${listing##* }"
}

validate_installer_catalog() {
    local catalog=$1 name installer kind package minimum bundle platforms seen=''
    [ -f "$catalog" ] || fail 'installer catalog is missing'
    [ ! -L "$catalog" ] || fail 'installer catalog is a symlink'
    while IFS=$'|\r' read -r name installer kind package minimum bundle platforms; do
        case "$name" in ''|\#*) continue ;; esac
        case ",$seen," in *",$name,"*) fail "duplicate installer catalog entry: $name" ;; esac
        seen="$seen$name,"
        case "$installer" in homebrew) ;; *) fail "unsupported installer for $name: $installer" ;; esac
        case "$kind" in formula|cask) ;; *) fail "unsupported installer package kind for $name: $kind" ;; esac
        case "$minimum" in ''|*[!0-9.]*) fail "invalid minimum version for $name: $minimum" ;; esac
        case "$bundle" in ''|\#*) fail "installer catalog entry needs a bundle: $name" ;; esac
        case "$platforms" in ''|*[!a-z0-9,]*) fail "invalid installer platforms for $name: $platforms" ;; esac
    done < "$catalog"
}

print_installer_tools() {
    local name installer kind package minimum bundle platforms separator=''
    printf '['
    while IFS=$'|\r' read -r name installer kind package minimum bundle platforms; do
        case "$name" in ''|\#*) continue ;; esac
        bundle_selected "$bundle" || continue
        installer_tool_matches "$platforms" || continue
        printf '%s{"name":' "$separator"; json_string "$name"
        printf ',"installer":'; json_string "$installer"
        printf ',"kind":'; json_string "$kind"
        printf ',"package":'; json_string "$package"
        printf ',"minimum":'; json_string "$minimum"
        printf ',"bundle":'; json_string "$bundle"
        printf '}'; separator=,
    done < "$INSTALLER_CATALOG"
    printf ']'
}

# A Homebrew install writes into the Homebrew prefix, and a cask writes an
# application bundle into /Applications. Both are outside the home, so the
# account check keeps them on a real device instead of a simulated one.
installer_real_account_home() {
    local actual_platform account_home
    actual_platform="$(PATH=/usr/bin:/bin detect_platform 2>/dev/null)" || return 1
    [ "$DEPLOY_PLATFORM" = "$actual_platform" ] || return 1
    account_home="$(native_account_value home 2>/dev/null)" || return 1
    [ -n "$account_home" ] && [ "$DEPLOY_HOME" = "$account_home" ]
}

# One attempt of a network install can fail on its own, so the install is
# attempted again a few times before the deployment gives up.
installer_install() {
    local brew=$1 kind=$2 package=$3 attempt=1 status=1
    while [ "$attempt" -le 3 ]; do
        case "$kind" in
            cask) if "$brew" install --cask "$package"; then status=0; else status=$?; fi ;;
            formula) if "$brew" install "$package"; then status=0; else status=$?; fi ;;
        esac
        [ "$status" -eq 0 ] && return 0
        attempt=$((attempt + 1))
        [ "$attempt" -le 3 ] && sleep 3
    done
    return "$status"
}

install_installer_tools() {
    local name installer kind package minimum bundle platforms brew version state
    [ "$DEPLOY_PLATFORM" = macos ] || return 0
    state="$XDG_STATE_HOME/dotfiles/installer-tools.lock.tsv"
    mkdir -p "$(dirname "$state")"
    : > "$state"
    while IFS=$'|\r' read -r name installer kind package minimum bundle platforms; do
        case "$name" in ''|\#*) continue ;; esac
        bundle_selected "$bundle" || continue
        installer_tool_matches "$platforms" || continue
        if ! brew=$(installer_homebrew); then
            printf 'dotfiles: %s: no Homebrew on this device; the installer tier is skipped\n' "$name"
            continue
        fi
        if ! version=$(installer_tool_version "$brew" "$kind" "$package"); then
            if ! installer_real_account_home; then
                printf 'dotfiles: %s: Homebrew installs need the real account home; skipped\n' "$name"
                continue
            fi
            DEPLOY_STEP="install-installer-tools.$name"
            installer_install "$brew" "$kind" "$package" ||
                fail "cannot install $name through Homebrew ($package)"
            version=$(installer_tool_version "$brew" "$kind" "$package") ||
                fail "cannot read the installed version of $name"
        fi
        installer_version_at_least "$version" "$minimum" ||
            fail "$name $version is below the catalog minimum $minimum"
        printf '%s|%s|%s|%s\n' "$name" "$installer" "$version" "$minimum" >> "$state"
    done < "$INSTALLER_CATALOG"
}

validate_installer_catalog "$INSTALLER_CATALOG"
