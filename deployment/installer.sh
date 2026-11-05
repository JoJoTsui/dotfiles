# Installer-owned candidates include Homebrew formulas and casks.
# Homebrew is adopted from the device; this
# deployment never installs it, and a device without it falls through to the
# next installer in the order.
# shellcheck shell=bash
# shellcheck disable=SC2034 # Public bootstrap adapter data.

INSTALLER_CATALOG="$DEPLOY_SOURCE/deployment/installer-tools.tsv"
DEPLOY_INSTALLER_TOOLS=()

installer_selected() {
    [ "$1" = common ] || bundle_selected "$1"
}

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
    awk -v have="$1" -v want="$2" 'BEGIN {
        sub(/_[0-9]+$/, "", have)
        sub(/_[0-9]+$/, "", want)
        if (have !~ /^[0-9]+(\.[0-9]+)*$/ || want !~ /^[0-9]+(\.[0-9]+)*$/) exit 1
        split(have, h, "."); split(want, w, ".")
        for (i = 1; i <= 3; i++) {
            if (h[i] + 0 > w[i] + 0) exit 0
            if (h[i] + 0 < w[i] + 0) exit 1
        }
        exit 0
    }'
}

installer_tool_version() {
    local brew=$1 kind=$2 package=$3 listing version newest=''
    case "$kind" in
        cask) listing=$("$brew" list --cask --versions "$package" 2>/dev/null) ;;
        formula) listing=$("$brew" list --versions "$package" 2>/dev/null) ;;
        *) return 1 ;;
    esac
    [ -n "$listing" ] || return 1
    for version in ${listing#* }; do
        if [ -z "$newest" ] || installer_version_at_least "$version" "$newest"; then newest=$version; fi
    done
    [ -n "$newest" ] || return 1
    printf '%s' "$newest"
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
        installer_version_at_least "$minimum" "$minimum" || fail "invalid minimum version for $name: $minimum"
        case "$bundle" in ''|\#*) fail "installer catalog entry needs a bundle: $name" ;; esac
        case "$platforms" in ''|*[!a-z0-9,]*) fail "invalid installer platforms for $name: $platforms" ;; esac
        if [ "$bundle" = common ]; then
            [ "$kind" = formula ] || fail "common installer needs a formula: $name"
            installer_common_mappings "$name" >/dev/null || fail "unknown common installer environment: $name"
        fi
    done < "$catalog"
}

print_installer_tools() {
    local name installer kind package minimum bundle platforms separator=''
    if [ "${DEPLOY_APPLY_ONLY:-false}" = true ] || [ "${DEPLOY_AGENTS_ONLY:-false}" = true ]; then
        printf '[]'
        return
    fi
    printf '['
    while IFS=$'|\r' read -r name installer kind package minimum bundle platforms; do
        case "$name" in ''|\#*) continue ;; esac
        installer_selected "$bundle" || continue
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

# Device commands may be reused only for native execution. Foreign rendering
# and cross-architecture deployments keep their own Pixi environments.
installer_native_target() {
    [ "$DEPLOY_PLATFORM" = "$(PATH=/usr/bin:/bin detect_platform)" ] || return 1
    local arch
    arch=$(uname -m)
    [ "$arch" != arm64 ] || arch=aarch64
    [ -z "${DEPLOY_ARCH:-}" ] || [ "$DEPLOY_ARCH" = "$arch" ]
}

installer_common_mappings() {
    local environment specifications mappings targets
    while IFS=$'|\r' read -r environment specifications mappings targets; do
        [ "$environment" != "$1" ] || { printf '%s' "$mappings"; return 0; }
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
    return 1
}

installer_common_minimum() {
    local name installer kind package minimum bundle platforms
    while IFS=$'|\r' read -r name installer kind package minimum bundle platforms; do
        if [ "$name" = "$1" ] && [ "$bundle" = common ]; then
            printf '%s' "$minimum"
            return 0
        fi
    done < "$INSTALLER_CATALOG"
    fail "missing common installer floor: $1"
}

installer_command_version() {
    local diagnostic
    diagnostic=$("$1" --version 2>/dev/null) || return 1
    printf '%s\n' "$diagnostic" | sed -nE 's/^[^0-9]*([0-9]+(\.[0-9]+)*).*/\1/p' | head -n 1
}

# Atuin's history importer is verified against one storage schema. Its exact
# version remains owned by the common catalog; other providers keep floors.
installer_common_version_compatible() {
    local name=$1 version=$2 minimum=$3 command=$4 diagnostic pin
    if [ "$name" = atuin ]; then
        pin=$(common_package_pin atuin)
        [ "$version" = "$pin" ] || return 1
        # The generic parser drops suffixes. Check the actual diagnostic too,
        # using the same `atuin <pin>` fields required by the importer.
        diagnostic=$("$command" --version 2>/dev/null) || return 1
        printf '%s\n' "$diagnostic" | awk -v pin="$pin" 'NF { exit !($1 == "atuin" && $2 == pin) }'
    else
        installer_version_at_least "$version" "$minimum"
    fi
}

installer_owned_launcher() {
    LC_ALL=C head -c 80 "$1" 2>/dev/null | LC_ALL=C grep -Fq '# Managed by dotfiles common installer.'
}

# Resolve every exposure together. Formula libexec/bin contains Python's
# unversioned commands and may also contain npm/npx.
installer_common_paths() {
    local mappings=$1 prefix=$2 mapping command target primary='' pip_version
    local saved_ifs=$IFS
    INSTALLER_COMMANDS=()
    INSTALLER_PATHS=()
    IFS=,
    for mapping in $mappings; do
        command=${mapping%%=*}
        if [ -n "$prefix" ]; then
            target="$prefix/bin/${mapping#*=}"
            [ -x "$target" ] || target="$prefix/libexec/bin/${mapping#*=}"
        else
            target=$(command -v "${mapping#*=}" 2>/dev/null) || { IFS=$saved_ifs; return 1; }
            # Prior managed launchers must be re-resolved, otherwise reapply
            # can produce a launcher which executes itself.
            case "$target" in "$PIXI_HOME/bin/"*) IFS=$saved_ifs; return 1 ;; esac
            if installer_owned_launcher "$target"; then
                IFS=$saved_ifs; return 1
            fi
            if [ -n "$primary" ] && [ "$(dirname "$target")" != "$(dirname "$primary")" ]; then
                IFS=$saved_ifs; return 1
            fi
        fi
        case "$target" in /*) ;; *) IFS=$saved_ifs; return 1 ;; esac
        [ -x "$target" ] || { IFS=$saved_ifs; return 1; }
        INSTALLER_COMMANDS+=("$command")
        INSTALLER_PATHS+=("$target")
        [ -n "$primary" ] || primary=$target
        # Python's group includes a separately pinned pip dependency.
        if [ "$command" = pip ]; then
            pip_version=$(installer_command_version "$target") || { IFS=$saved_ifs; return 1; }
            installer_version_at_least "$pip_version" "$(common_package_pin pip)" || { IFS=$saved_ifs; return 1; }
        fi
    done
    IFS=$saved_ifs
    INSTALLER_VERSION=$(installer_command_version "$primary")
    [ -n "$INSTALLER_VERSION" ]
}

installer_common_launcher() {
    local command=$1 target=$2 destination="$HOME/.local/bin/$1" temporary quoted
    [ "$destination" != "$target" ] || return 0
    [ ! -L "$destination" ] || fail "common launcher is a symlink: $destination"
    if [ -e "$destination" ] && ! installer_owned_launcher "$destination"; then
        fail "common launcher would replace a device file: $destination"
    fi
    quoted=${target//\'/\'\\\'\'}
    temporary=$(mktemp "$HOME/.local/bin/.common.XXXXXX")
    if ! { printf '#!/bin/sh\n# Managed by dotfiles common installer.\nexec '\''%s'\'' "$@"\n' "$quoted" > "$temporary" &&
        chmod 755 "$temporary" && mv -f "$temporary" "$destination"; }; then
        rm -f "$temporary"
        fail "cannot expose common command: $command"
    fi
}

installer_resolve_common() {
    local name=$1 package=$2 minimum=$3 brew prefix mappings index
    installer_native_target || return 1
    mappings=$(installer_common_mappings "$name") || return 1
    INSTALLER_PROVIDER=adopted
    if ! installer_common_paths "$mappings" '' ||
        ! installer_common_version_compatible "$name" "$INSTALLER_VERSION" "$minimum" "${INSTALLER_PATHS[0]}"; then
        brew=$(installer_homebrew) || return 1
        INSTALLER_PROVIDER=homebrew
        if ! installer_tool_version "$brew" formula "$package" >/dev/null; then
            installer_real_account_home || return 1
            installer_install "$brew" formula "$package" || return 1
        fi
        prefix=$("$brew" --prefix "$package") || return 1
        installer_common_paths "$mappings" "$prefix" || return 1
        installer_common_version_compatible "$name" "$INSTALLER_VERSION" "$minimum" "${INSTALLER_PATHS[0]}" || return 1
    fi
    for ((index=0; index<${#INSTALLER_COMMANDS[@]}; index++)); do
        installer_common_launcher "${INSTALLER_COMMANDS[$index]}" "${INSTALLER_PATHS[$index]}"
    done
}

# Fallback commands use the same macOS launcher paths as adopted commands.
# Existing Pixi registry entries remain available for rollback and device aliases.
installer_expose_common() {
    [ "$DEPLOY_PLATFORM" = macos ] || return 0
    local environment specifications mappings targets mapping saved_ifs ready temporary
    while IFS=$'|\r' read -r environment specifications mappings targets; do
        case "$environment" in ''|\#*) continue ;; esac
        common_target_matches "$targets" || continue
        if awk -F '|' -v name="$environment" '$1 == name { found=1 } END { exit !found }' "$XDG_STATE_HOME/dotfiles/installer-tools.lock.tsv"; then continue; fi
        saved_ifs=$IFS; IFS=,
        for mapping in $mappings; do
            [ -x "$PIXI_HOME/bin/${mapping%%=*}" ] || fail "required command not exposed by Pixi: ${mapping%%=*}"
            installer_common_launcher "${mapping%%=*}" "$PIXI_HOME/bin/${mapping%%=*}"
        done
        IFS=$saved_ifs
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
    ready="$XDG_STATE_HOME/dotfiles/common-tools.ready"
    [ ! -L "$ready" ] || fail 'common readiness marker is a symlink'
    temporary=$(mktemp "$ready.XXXXXX")
    printf '1\n' > "$temporary"
    mv -f "$temporary" "$ready"
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
    local name installer kind package minimum bundle platforms brew version state staged
    [ "$DEPLOY_PLATFORM" = macos ] || return 0
    state="$XDG_STATE_HOME/dotfiles/installer-tools.lock.tsv"
    [ ! -L "$XDG_STATE_HOME/dotfiles" ] || fail 'installer state directory is a symlink'
    mkdir -p "$(dirname "$state")"
    [ ! -L "$state" ] || fail 'installer state is a symlink'
    staged=$(mktemp "$state.XXXXXX")
    while IFS=$'|\r' read -r name installer kind package minimum bundle platforms; do
        case "$name" in ''|\#*) continue ;; esac
        installer_selected "$bundle" || continue
        installer_tool_matches "$platforms" || continue
        if [ "$bundle" = common ]; then
            DEPLOY_STEP="install-installer-tools.$name"
            if installer_resolve_common "$name" "$package" "$minimum"; then
                printf '%s|%s|%s|%s\n' "$name" "$INSTALLER_PROVIDER" "$INSTALLER_VERSION" "$minimum" >> "$staged"
            else
                printf 'dotfiles: %s: using the pinned Pixi fallback\n' "$name"
            fi
            continue
        fi
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
        printf '%s|%s|%s|%s\n' "$name" "$installer" "$version" "$minimum" >> "$staged"
    done < "$INSTALLER_CATALOG"
    mv -f "$staged" "$state"
}

validate_installer_catalog "$INSTALLER_CATALOG"
