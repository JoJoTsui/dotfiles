# Declarations and installer functions only: sourcing this must never mutate
# files. Later tickets extend these adapters; bootstrap owns selection, state
# isolation, step failures, and working-tree source application.
# shellcheck disable=SC2034 # Plan arrays are consumed by the sourced caller.
source "$DEPLOY_SOURCE/deployment/overrides.sh"
source "$DEPLOY_SOURCE/deployment/common.sh"
source "$DEPLOY_SOURCE/deployment/bundles.sh"
source "$DEPLOY_SOURCE/deployment/installer.sh"
source "$DEPLOY_SOURCE/deployment/managers.sh"
source "$DEPLOY_SOURCE/deployment/agents.sh"
source "$DEPLOY_SOURCE/deployment/proxy.sh"
source "$DEPLOY_SOURCE/deployment/shell.sh"
source "$DEPLOY_SOURCE/deployment/history.sh"
source "$DEPLOY_SOURCE/deployment/skills.sh"
source "$DEPLOY_SOURCE/deployment/payload.sh"
source "$DEPLOY_SOURCE/deployment/client-settings.sh"
source "$DEPLOY_SOURCE/deployment/macos.sh"
source "$DEPLOY_SOURCE/deployment/system.sh"
source "$DEPLOY_SOURCE/deployment/magpie.sh"
DEPLOY_ACTIONS=(install-managers apply-source install-installer-tools install-common install-agents prepare-shell)

install_managers() {
    if ! "$DEPLOY_APPLY_ONLY" && ! "$DEPLOY_AGENTS_ONLY"; then
        DEPLOY_STEP=install-managers.pixi
        install_pixi
    fi
    DEPLOY_STEP=install-managers.chezmoi
    install_chezmoi
}

# Pixi defaults to 50 concurrent downloads and one solve per CPU. The fresh
# native macOS gate supplies a positive bound through DOTFILES_PIXI_CONCURRENCY; ordinary
# deployments leave it unset and keep Pixi's own defaults. Validate once, before
# either Pixi operation, and reuse the documented flags for both of them.
DEPLOY_PIXI_CONCURRENCY_ARGS=()
prepare_pixi_concurrency() {
    local value=${DOTFILES_PIXI_CONCURRENCY-}
    [ -n "$value" ] || return 0
    case $value in
        *[!0-9]*) fail "DOTFILES_PIXI_CONCURRENCY must be a positive integer: $value" ;;
    esac
    [ "$value" -gt 0 ] 2>/dev/null || fail "DOTFILES_PIXI_CONCURRENCY must be a positive integer: $value"
    DEPLOY_PIXI_CONCURRENCY_ARGS=(--concurrent-solves "$value" --concurrent-downloads "$value")
}

# A pinned ephemeral Python runs the merge without first replacing or writing
# the device registry. Pixi owns installation and exposure after that merge.
install_common() {
    DEPLOY_STEP=install-common.merge-manifest
    local provider_arguments=() override_arguments=()
    prepare_pixi_concurrency
    if [ "$DEPLOY_PLATFORM" = macos ]; then provider_arguments=(--providers "$XDG_STATE_HOME/dotfiles/installer-tools.lock.tsv"); fi
    # The device override snapshot is the only version input the merge takes
    # besides the rendered desired manifests.
    DEPLOY_STEP=install-common.version-overrides
    deploy_version_overrides
    override_arguments=(--overrides "$XDG_STATE_HOME/dotfiles/version-overrides.json")
    "$DEPLOY_PIXI" exec ${DEPLOY_PIXI_CONCURRENCY_ARGS[@]+"${DEPLOY_PIXI_CONCURRENCY_ARGS[@]}"} --spec "$(common_python_spec)" python "$DEPLOY_SOURCE/deployment/merge_pixi.py" ${provider_arguments[@]+"${provider_arguments[@]}"} ${override_arguments[@]+"${override_arguments[@]}"} "$XDG_CONFIG_HOME/dotfiles/pixi-global.toml" "$XDG_CONFIG_HOME/dotfiles/pixi-bundles.toml" "$PIXI_HOME/manifests/pixi-global.toml"
    DEPLOY_STEP=install-common.pixi-sync
    "$DEPLOY_PIXI" global sync ${DEPLOY_PIXI_CONCURRENCY_ARGS[@]+"${DEPLOY_PIXI_CONCURRENCY_ARGS[@]}"}
    installer_expose_common
    DEPLOY_STEP=install-common.rustup
    install_rustup
    DEPLOY_STEP=install-common.verify-exposure
    local environment specifications mappings targets mapping saved_ifs
    while IFS=$'|\r' read -r environment specifications mappings targets; do
        case "$environment" in ''|\#*) continue ;; esac
        common_target_matches "$targets" || continue
        saved_ifs=$IFS; IFS=,
        for mapping in $mappings; do
            [ -x "$DOTFILES_COMMON_BIN/${mapping%%=*}" ] || fail "required common command missing: ${mapping%%=*}"
        done
        IFS=$saved_ifs
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
    DEPLOY_STEP=install-common.verify-bundle-exposure
    verify_bundle_exposure
}
prepare_shell() {
    prepare_managed_shell
    prepare_history
    DEPLOY_STEP=prepare-shell.macos-discovery
    deploy_macos_config
}
