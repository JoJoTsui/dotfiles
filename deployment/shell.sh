# Declaration-only extension; bootstrap owns the selected home and stage order.
# shellcheck disable=SC2034 # Bootstrap consumes the plan tools and stage marker.
DEPLOY_TOOLS+=(nu-login dotfiles-shell-prepare)
prepare_managed_shell() {
    DEPLOY_STEP=prepare-shell.startup
    "$HOME/.local/bin/dotfiles-shell-prepare"
}
