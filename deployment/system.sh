# shellcheck shell=bash
# Explicit system/account actions. Sourcing this module only declares helpers;
# bootstrap invokes them only after explicit opt-in and real-account validation.

system_admin() {
    local uid sudo_bin
    uid="$(/usr/bin/id -u)"
    if [ "$uid" -eq 0 ]; then
        "$@"
    else
        for sudo_bin in /usr/bin/sudo /bin/sudo; do
            if [ -x "$sudo_bin" ]; then "$sudo_bin" "$@"; return; fi
        done
        fail 'sudo is required for this explicit system action'
    fi
}

system_bash_rc() {
    case "$DEPLOY_PLATFORM" in
        linux|wsl)
            if [ -f /etc/bash.bashrc ]; then printf '/etc/bash.bashrc'
            elif [ -f /etc/bashrc ]; then printf '/etc/bashrc'
            else fail 'system Bash rc is not available under /etc'
            fi ;;
        macos) printf '/etc/bashrc' ;;
        *) fail "system Bash configuration is unsupported on $DEPLOY_PLATFORM" ;;
    esac
}

native_account_value() {
    local value="$1" field attribute
    case "$DEPLOY_PLATFORM" in
        linux|wsl)
            case "$value" in
                home) field=6 ;;
                shell) field=7 ;;
                *) return 2 ;;
            esac
            /usr/bin/getent passwd "$(/usr/bin/id -u)" | /usr/bin/awk -F: -v field="$field" '{print $field}' ;;
        macos)
            case "$value" in
                home) attribute=NFSHomeDirectory ;;
                shell) attribute=UserShell ;;
                *) return 2 ;;
            esac
            /usr/bin/dscl . -read "/Users/$(/usr/bin/id -un)" "$attribute" | /usr/bin/awk '{print $2}' ;;
        *) fail "account lookup is unsupported on $DEPLOY_PLATFORM" ;;
    esac
}

assert_real_account_home() {
    local actual_platform account_home
    actual_platform="$(PATH=/usr/bin:/bin detect_platform)" || fail 'cannot detect the native platform'
    [ "$DEPLOY_PLATFORM" = "$actual_platform" ] || fail 'system and login-shell options require the detected native platform'
    account_home="$(native_account_value home)" || fail 'cannot resolve the current account home'
    [ -n "$account_home" ] && [ "$DEPLOY_HOME" = "$account_home" ] || fail 'system and login-shell options cannot target a simulated or different home'
}

replace_managed_bash_block() {
    local target="$1" source_file="$2" temporary="$3"
    awk '
        $0 == "# BEGIN DOTFILES SYSTEM CONFIG" { skip = 1; next }
        $0 == "# END DOTFILES SYSTEM CONFIG" { skip = 0; next }
        !skip { print }
    ' "$target" > "$temporary"
    {
        printf '\n# BEGIN DOTFILES SYSTEM CONFIG\n'
        cat "$source_file"
        printf '\n# END DOTFILES SYSTEM CONFIG\n'
    } >> "$temporary"
}

configure_system() {
    local target backup temporary source_file
    target="$(system_bash_rc)"
    backup="$target.dotfiles.bak"
    source_file="$DEPLOY_SOURCE/deployment/system/bashrc"
    [ -f "$source_file" ] || fail "managed system Bash config is missing: $source_file"
    [ -f "$target" ] || fail "system Bash config does not exist: $target"
    [ ! -L "$target" ] || fail "refusing symlinked system Bash config: $target"
    [ ! -L "$backup" ] || fail "refusing symlinked system backup: $backup"

    temporary="$(mktemp "$TMPDIR/dotfiles-bashrc.XXXXXX")" || fail 'cannot create system config staging file'
    replace_managed_bash_block "$target" "$source_file" "$temporary"
    if /usr/bin/cmp -s "$temporary" "$target"; then
        rm -f "$temporary"
        return 0
    fi
    if [ -e "$backup" ] && ! grep -Fqx '# BEGIN DOTFILES SYSTEM CONFIG' "$target"; then
        fail "backup already exists without a managed system block: $backup"
    fi
    if [ ! -e "$backup" ]; then system_admin /bin/cp -p "$target" "$backup"; fi
    system_admin /usr/bin/install -m 0644 "$temporary" "$target"
    rm -f "$temporary"
}

register_login_shell() {
    local shell_path=/etc/shells backup temporary
    [ -f "$shell_path" ] || fail 'system shell registry /etc/shells does not exist'
    [ ! -L "$shell_path" ] || fail 'refusing symlinked /etc/shells'
    if /usr/bin/grep -Fqx "$HOME/.local/bin/nu-login" "$shell_path"; then return 0; fi

    backup="$shell_path.dotfiles.bak"
    [ ! -L "$backup" ] || fail "refusing symlinked system backup: $backup"
    temporary="$(mktemp "$TMPDIR/dotfiles-shells.XXXXXX")" || fail 'cannot create /etc/shells staging file'
    cat "$shell_path" > "$temporary"
    printf '%s\n' "$HOME/.local/bin/nu-login" >> "$temporary"
    if [ -e "$backup" ]; then
        /usr/bin/cmp -s "$shell_path" "$backup" || fail "backup already exists with different content: $backup"
    else
        system_admin /bin/cp -p "$shell_path" "$backup"
    fi
    system_admin /usr/bin/install -m 0644 "$temporary" "$shell_path"
    rm -f "$temporary"
}

current_login_shell() {
    native_account_value shell
}

set_login_shell() {
    local shell_path="$HOME/.local/bin/nu-login" current_shell
    [ -x "$shell_path" ] || fail "managed login launcher is missing: $shell_path"
    case "$shell_path" in *[[:space:]]*) fail 'login-shell paths cannot contain whitespace' ;; esac
    local chsh_bin
    for chsh_bin in /usr/bin/chsh /bin/chsh; do
        if [ -x "$chsh_bin" ]; then break; fi
    done
    [ -x "$chsh_bin" ] || fail 'chsh is required to change the account login shell'
    register_login_shell
    current_shell="$(current_login_shell)" || fail 'cannot resolve the current account login shell'
    [ "$current_shell" = "$shell_path" ] && return 0
    "$chsh_bin" -s "$shell_path"
}
