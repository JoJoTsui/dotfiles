# Merge client defaults after source application. No agent/runtime dependency:
# the already-required Chezmoi performs format-aware parsing and serialization.
validate_client_settings() {
    local format source target policy value
    while IFS='|' read -r format source target policy; do
        case "$format" in ''|\#*) continue ;; json|jsonc|toml) ;; *) fail "unknown client settings format: $format" ;; esac
        for value in "$source" "$target" "$policy"; do
            case "$value" in ''|/*|..|../*|*/../*|*/..) fail "client settings catalog path must be relative: $value" ;; esac
        done
        payload_safe_destination "$DEPLOY_HOME/$target"
        payload_safe_destination "$DEPLOY_HOME/.local/state/dotfiles/client-settings/$policy.json"
        [ ! -e "$DEPLOY_HOME/$target" ] || [ -f "$DEPLOY_HOME/$target" ] || fail "client settings target must be a regular file: $target"
        [ ! -e "$DEPLOY_HOME/.local/state/dotfiles/client-settings/$policy.json" ] || [ -f "$DEPLOY_HOME/.local/state/dotfiles/client-settings/$policy.json" ] || fail "client settings baseline must be a regular file: $policy"
        [ -f "$DEPLOY_SOURCE/deployment/client-settings/$source" ] || fail "client settings source is missing: $source"
        [ ! -L "$DEPLOY_SOURCE/deployment/client-settings/$source" ] || fail "client settings source is a symlink: $source"
    done < "$DEPLOY_SOURCE/deployment/client-settings/targets.tsv"
}

deploy_client_settings() {
    local format source target policy stage
    validate_client_settings
    stage=$(mktemp -d "$TMPDIR/client-settings.XXXXXX")
    # Render the entire batch before changing a client's files. Invalid existing
    # JSONC/TOML propagates a named failure while all client settings stay intact.
    while IFS='|' read -r format source target policy; do
        case "$format" in ''|\#*) continue ;; esac
        export DOTFILES_SETTINGS_FORMAT="$format" DOTFILES_SETTINGS_POLICY="$policy"
        export DOTFILES_SETTINGS_SOURCE="$DEPLOY_SOURCE/deployment/client-settings/$source"
        export DOTFILES_SETTINGS_TARGET="$HOME/$target"
        export DOTFILES_SETTINGS_BASELINE="$XDG_STATE_HOME/dotfiles/client-settings/$policy.json"
        if ! DOTFILES_SETTINGS_OUTPUT=config "$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --no-tty execute-template --file "$DEPLOY_SOURCE/deployment/client-settings/merge.tmpl" > "$stage/$policy.config" 2> "$stage/parser.log"; then
            rm -rf "$stage"
            fail "cannot merge client config ($format): $target; check its syntax"
        fi
        if ! DOTFILES_SETTINGS_OUTPUT=baseline "$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --no-tty execute-template --file "$DEPLOY_SOURCE/deployment/client-settings/merge.tmpl" > "$stage/$policy.baseline" 2> "$stage/parser.log"; then
            rm -rf "$stage"
            fail "cannot prepare client config baseline ($format): $target"
        fi
    done < "$DEPLOY_SOURCE/deployment/client-settings/targets.tsv"
    while IFS='|' read -r format source target policy; do
        case "$format" in ''|\#*) continue ;; esac
        mkdir -p "$(dirname "$HOME/$target")" "$XDG_STATE_HOME/dotfiles/client-settings"
        chmod 600 "$stage/$policy.config" "$stage/$policy.baseline"
        mv "$stage/$policy.config" "$HOME/$target"
        mv "$stage/$policy.baseline" "$XDG_STATE_HOME/dotfiles/client-settings/$policy.json"
    done < "$DEPLOY_SOURCE/deployment/client-settings/targets.tsv"
    rm -rf "$stage"
    unset DOTFILES_SETTINGS_FORMAT DOTFILES_SETTINGS_POLICY DOTFILES_SETTINGS_SOURCE DOTFILES_SETTINGS_TARGET DOTFILES_SETTINGS_BASELINE
}
