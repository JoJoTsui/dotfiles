# Declaration-only history extension: no activation or imports during bootstrap.
# shellcheck disable=SC2034 # Plan tools and stage markers belong to bootstrap.
DEPLOY_TOOLS+=(dotfiles-history dotfiles-history-prepare)
prepare_history() {
    DEPLOY_STEP=prepare-shell.history
    "$HOME/.local/bin/dotfiles-history-prepare"
    "$HOME/.local/bin/dotfiles-history" status
}
