# Merge client defaults after source application. No agent/runtime dependency:
# the already-required Chezmoi performs format-aware parsing and serialization.

# The client settings policies the gateway migration owns: Claude Code's
# settings and Pi's settings. The Magpie step merges these two files alone,
# so the gateway step never rewrites another client's configuration.
CLIENT_SETTINGS_MAGPIE_POLICIES='claude-settings pi-settings'

# Whether a policy is part of a merge. An empty list selects every policy in
# the catalog; a named list selects only those, so a step can merge the files
# it owns.
client_settings_policy_selected() {
    local policy=$1 policies=$2
    [ -n "$policies" ] || return 0
    case " $policies " in
        *" $policy "*) return 0 ;;
    esac
    return 1
}

client_claude_uses_plain_opus() {
    local result
    # Source application already validated and normalized this target. Read it
    # with the same JSONC parser; diagnostics must not expose credential values.
    result=$(DOTFILES_SETTINGS_CLAUDE_TARGET="$HOME/.claude/settings.json" "$DEPLOY_CHEZMOI" \
        --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" \
        --no-tty execute-template '{{- $settings := include (env "DOTFILES_SETTINGS_CLAUDE_TARGET") | fromJsonc -}}{{- if and (kindIs "map" $settings) (kindIs "string" (get $settings "model")) (eq (get $settings "model") "opus") -}}true{{- else -}}false{{- end -}}' 2>/dev/null) ||
        fail 'cannot inspect the declared Claude model: .claude/settings.json'
    [ "$result" = true ]
}

validate_client_settings() {
    local format source target policy value
    while IFS=$'|\r' read -r format source target policy; do
        case "$format" in ''|\#*) continue ;; json|jsonc|toml|yaml) ;; *) fail "unknown client settings format: $format" ;; esac
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
    local format source target policy stage key trace_policy keep_plain_opus=${1:-0} magpie_wiring=${2:-0} policies=${3:-}
    case "$keep_plain_opus" in 0|1) ;; *) fail 'invalid internal Claude model preservation request' ;; esac
    case "$magpie_wiring" in 0|1) ;; *) fail 'invalid internal Magpie client wiring request' ;; esac
    # Only the selected client installer can request the model restoration,
    # and only the magpie step can request the gateway wiring. Ordinary merges
    # do not inherit either request from the caller's environment.
    export DOTFILES_SETTINGS_KEEP_PLAIN_OPUS="$keep_plain_opus"
    if [ "$magpie_wiring" = 1 ]; then
        export DOTFILES_SETTINGS_MAGPIE=true
    else
        export DOTFILES_SETTINGS_MAGPIE=false
    fi
    validate_client_settings
    stage=$(mktemp -d "$TMPDIR/client-settings.XXXXXX")
    # Render the entire batch before changing a client's files. Invalid existing
    # JSONC/TOML propagates a named failure while all client settings stay intact.
    while IFS=$'|\r' read -r format source target policy; do
        case "$format" in ''|\#*) continue ;; esac
        client_settings_policy_selected "$policy" "$policies" || continue
        # One policy may own several targets; the staged file key follows the
        # target so a shared policy cannot overwrite an earlier render.
        key=$(printf '%s' "$target" | tr '/.' '__')
        export DOTFILES_SETTINGS_FORMAT="$format" DOTFILES_SETTINGS_POLICY="$policy"
        export DOTFILES_SETTINGS_SOURCE="$DEPLOY_SOURCE/deployment/client-settings/$source"
        export DOTFILES_SETTINGS_TARGET="$HOME/$target"
        export DOTFILES_SETTINGS_BASELINE="$XDG_STATE_HOME/dotfiles/client-settings/$policy.json"
        if ! DOTFILES_SETTINGS_OUTPUT=config "$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --no-tty execute-template --file "$DEPLOY_SOURCE/deployment/client-settings/merge.tmpl" > "$stage/$key.config" 2> "$stage/parser.log"; then
            if [ "${DOTFILES_TEST_TRACE_CLIENT_SETTINGS:-}" = 1 ]; then
                printf 'dotfiles: client settings shell policy (test-only): <%s>\n' "${DOTFILES_SETTINGS_POLICY-<unset>}" >&2
                printf '%s\n' '{{ env "DOTFILES_SETTINGS_POLICY" }}' > "$stage/policy.tmpl"
                if trace_policy=$("$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --no-tty execute-template --file "$stage/policy.tmpl" 2> "$stage/policy-query.log"); then
                    printf 'dotfiles: client settings template policy (test-only): <%s>\n' "$trace_policy" >&2
                else
                    printf 'dotfiles: client settings template policy query failed (test-only):\n' >&2
                    cat "$stage/policy-query.log" >&2
                fi
                printf 'dotfiles: client settings parser detail (test-only):\n' >&2
                cat "$stage/parser.log" >&2
            fi
            rm -rf "$stage"
            fail "cannot merge client config ($format): $target; check its syntax"
        fi
        if ! DOTFILES_SETTINGS_OUTPUT=baseline "$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --no-tty execute-template --file "$DEPLOY_SOURCE/deployment/client-settings/merge.tmpl" > "$stage/$key.baseline" 2> "$stage/parser.log"; then
            rm -rf "$stage"
            fail "cannot prepare client config baseline ($format): $target"
        fi
    done < "$DEPLOY_SOURCE/deployment/client-settings/targets.tsv"
    while IFS=$'|\r' read -r format source target policy; do
        case "$format" in ''|\#*) continue ;; esac
        client_settings_policy_selected "$policy" "$policies" || continue
        key=$(printf '%s' "$target" | tr '/.' '__')
        mkdir -p "$(dirname "$HOME/$target")" "$XDG_STATE_HOME/dotfiles/client-settings"
        chmod 600 "$stage/$key.config" "$stage/$key.baseline"
        # An unchanged configuration keeps its device file untouched, so file
        # times stay meaningful for the services that read them.
        if [ ! -f "$HOME/$target" ] || ! cmp -s "$stage/$key.config" "$HOME/$target"; then
            mv "$stage/$key.config" "$HOME/$target"
        fi
        mv "$stage/$key.baseline" "$XDG_STATE_HOME/dotfiles/client-settings/$policy.json"
    done < "$DEPLOY_SOURCE/deployment/client-settings/targets.tsv"
    rm -rf "$stage"
    unset DOTFILES_SETTINGS_FORMAT DOTFILES_SETTINGS_POLICY DOTFILES_SETTINGS_SOURCE DOTFILES_SETTINGS_TARGET DOTFILES_SETTINGS_BASELINE DOTFILES_SETTINGS_KEEP_PLAIN_OPUS DOTFILES_SETTINGS_MAGPIE
}

# Whether the gateway migration would change a repo-owned client file. The
# magpie step asks after the gateway answers and before it backs up or changes
# anything, so a current device keeps its files and their modification times.
# The render uses the same merger and the same wiring request as the migration
# itself; it writes no target and no baseline. The comparison is by content:
# a client that rewrote its own file in another format is not a change.
# Returns success when a migration is pending.
client_settings_magpie_pending() {
    local format source target policy stage key pending=1
    stage=$(mktemp -d "$TMPDIR/client-settings-pending.XXXXXX")
    export DOTFILES_SETTINGS_MAGPIE=true DOTFILES_SETTINGS_KEEP_PLAIN_OPUS=0
    cat > "$stage/normalize.tmpl" <<'TEMPLATE'
{{- (include (env "DOTFILES_SETTINGS_TARGET") | fromJsonc) | toPrettyJson -}}
TEMPLATE
    while IFS=$'|\r' read -r format source target policy; do
        case "$format" in ''|\#*) continue ;; esac
        case " $CLIENT_SETTINGS_MAGPIE_POLICIES " in *" $policy "*) ;; *) continue ;; esac
        key=$(printf '%s' "$target" | tr '/.' '__')
        export DOTFILES_SETTINGS_FORMAT="$format" DOTFILES_SETTINGS_POLICY="$policy"
        export DOTFILES_SETTINGS_SOURCE="$DEPLOY_SOURCE/deployment/client-settings/$source"
        export DOTFILES_SETTINGS_TARGET="$HOME/$target"
        export DOTFILES_SETTINGS_BASELINE="$XDG_STATE_HOME/dotfiles/client-settings/$policy.json"
        if ! DOTFILES_SETTINGS_OUTPUT=config "$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --no-tty execute-template --file "$DEPLOY_SOURCE/deployment/client-settings/merge.tmpl" > "$stage/$key.config" 2> "$stage/parser.log"; then
            rm -rf "$stage"
            fail "cannot inspect the Magpie client migration ($format): $target; check its syntax"
        fi
        [ -f "$HOME/$target" ] || { pending=0; continue; }
        case "$format" in
            json|jsonc)
                # The live file is read with the same parser the merge uses,
                # so only a content change counts as a pending migration.
                if ! DOTFILES_SETTINGS_OUTPUT=normalized "$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --no-tty execute-template --file "$stage/normalize.tmpl" > "$stage/$key.live" 2> "$stage/parser.log"; then
                    rm -rf "$stage"
                    fail "cannot read the current client settings ($format): $target"
                fi
                cmp -s "$stage/$key.config" "$stage/$key.live" || pending=0
                ;;
            *)
                cmp -s "$stage/$key.config" "$HOME/$target" || pending=0
                ;;
        esac
    done < "$DEPLOY_SOURCE/deployment/client-settings/targets.tsv"
    rm -rf "$stage"
    unset DOTFILES_SETTINGS_FORMAT DOTFILES_SETTINGS_POLICY DOTFILES_SETTINGS_SOURCE DOTFILES_SETTINGS_TARGET DOTFILES_SETTINGS_BASELINE DOTFILES_SETTINGS_KEEP_PLAIN_OPUS DOTFILES_SETTINGS_MAGPIE
    return "$pending"
}
