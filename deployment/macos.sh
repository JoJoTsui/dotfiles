# Native discovery copies reuse rendered canonical settings, never a second
# set of defaults. No account, shell registration, or system changes.
validate_macos_config() {
    [ "$DEPLOY_PLATFORM" = macos ] || return 0
    local source target optional value parent
    while IFS='|' read -r source target optional; do
        case "$source" in ''|\#*) continue ;; esac
        for value in "$source" "$target"; do
            case "$value" in ''|/*|..|../*|*/../*|*/..) fail 'macOS discovery catalog path must be relative' ;; esac
            payload_safe_destination "$DEPLOY_HOME/$value"
            [ ! -e "$DEPLOY_HOME/$value" ] || [ -f "$DEPLOY_HOME/$value" ] || fail "macOS discovery path must be a regular file: $value"
            parent=$(dirname "$DEPLOY_HOME/$value")
            while [ "$parent" != "$DEPLOY_HOME" ]; do
                [ ! -e "$parent" ] || [ -d "$parent" ] || fail "macOS discovery parent must be a directory: $parent"
                parent=${parent%/*}
            done
        done
    done < "$DEPLOY_SOURCE/deployment/macos-targets.tsv"
}

deploy_macos_config() {
    [ "$DEPLOY_PLATFORM" = macos ] || return 0
    validate_macos_config
    local source target optional
    while IFS='|' read -r source target optional; do
        case "$source" in ''|\#*) continue ;; esac
        if [ "$optional" = optional ] && [ ! -e "$HOME/$source" ] && [ ! -L "$HOME/$source" ]; then continue; fi
        payload_validate_tree "$HOME/$source" "$HOME/$target"
        mkdir -p "$(dirname "$HOME/$target")"
        cp -p "$HOME/$source" "$HOME/$target"
    done < "$DEPLOY_SOURCE/deployment/macos-targets.tsv"
}
