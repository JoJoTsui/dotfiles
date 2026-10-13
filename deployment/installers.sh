# Declarations and installer functions only: sourcing this must never mutate
# files. Later tickets extend these adapters; bootstrap owns selection, state
# isolation, step failures, and working-tree source application.
# shellcheck disable=SC2034 # Plan arrays are consumed by the sourced caller.
source "$DEPLOY_SOURCE/deployment/common.sh"
source "$DEPLOY_SOURCE/deployment/managers.sh"
source "$DEPLOY_SOURCE/deployment/agents.sh"
source "$DEPLOY_SOURCE/deployment/shell.sh"
source "$DEPLOY_SOURCE/deployment/payload.sh"
DEPLOY_ACTIONS=(install-managers apply-source install-common install-agents prepare-shell)

install_managers() {
    if ! "$DEPLOY_APPLY_ONLY" && ! "$DEPLOY_AGENTS_ONLY"; then
        DEPLOY_STEP=install-managers.pixi
        install_pixi
    fi
    DEPLOY_STEP=install-managers.chezmoi
    install_chezmoi
}

# A pinned ephemeral Python runs the merge without first replacing or writing
# the device registry. Pixi owns installation and exposure after that merge.
install_common() {
    DEPLOY_STEP=install-common.merge-manifest
    "$DEPLOY_PIXI" exec --spec "$(common_python_spec)" python "$DEPLOY_SOURCE/deployment/merge_pixi.py" "$XDG_CONFIG_HOME/dotfiles/pixi-global.toml" "$PIXI_HOME/manifests/pixi-global.toml"
    DEPLOY_STEP=install-common.pixi-sync
    "$DEPLOY_PIXI" global sync
    DEPLOY_STEP=install-common.rustup
    install_rustup
    DEPLOY_STEP=install-common.verify-exposure
    local environment specifications mappings targets mapping saved_ifs
    while IFS='|' read -r environment specifications mappings targets; do
        case "$environment" in ''|\#*) continue ;; esac
        common_target_matches "$targets" || continue
        saved_ifs=$IFS; IFS=,
        for mapping in $mappings; do
            [ -x "$PIXI_HOME/bin/${mapping%%=*}" ] || fail "required command not exposed by Pixi: ${mapping%%=*}"
        done
        IFS=$saved_ifs
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
}
prepare_shell() { prepare_managed_shell; }
