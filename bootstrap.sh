#!/usr/bin/env bash
# Public deployment boundary. Bash 3.2-compatible for fresh macOS hosts.
set -euo pipefail

DEPLOY_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
DEPLOY_HOME="${HOME:?HOME must be set}"
DEPLOY_PLAN=false
DEPLOY_APPLY_ONLY=false
CLI_PLATFORM='' CLI_ROLE='' CLI_PROFILE='' CLI_CLASS='' CLI_ARCH=''

fail() {
    printf 'dotfiles: %s\n' "$*" >&2
    if [ -n "${DEPLOY_STEP:-}" ]; then
        printf 'dotfiles: step %s failed (exit 1)\n' "$DEPLOY_STEP" >&2
    fi
    exit 1
}
json_string() {
    local value="$1"
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\n'/\\n}
    value=${value//$'\r'/\\r}
    value=${value//$'\t'/\\t}
    printf '"%s"' "$value"
}
json_array() {
    local separator='' value
    printf '['
    for value in "$@"; do
        printf '%s' "$separator"; json_string "$value"; separator=,
    done
    printf ']'
}
report_failure() {
    local exit_status=$?
    printf 'dotfiles: step %s failed (exit %s)\n' "$DEPLOY_STEP" "$exit_status" >&2
    exit "$exit_status"
}
run_step() { DEPLOY_STEP=$1; shift; "$@"; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            cat <<'HELP'
Usage: bash bootstrap.sh [options]
  --plan                    Print JSON; do not create files or install tools
  --home PATH               Absolute target home (defaults to HOME)
  --source PATH             Working chezmoi source (defaults to this checkout)
  --platform NAME           linux, macos, wsl, windows; otherwise detected
  --role NAME               workstation (default), remote-compute
  --profile NAME            <platform>-<role> preset, or t9k
  --class NAME              Legacy alias: t9k, linux, win
  --arch NAME               x86_64, aarch64 (amd64/arm64 aliases accepted)
  --apply-only              Apply files with chezmoi; skip tool/agent installers

Environment selectors: DOTFILES_PLATFORM, DOTFILES_ROLE, DOTFILES_PROFILE,
DOTFILES_CLASS, DOTFILES_ARCH. Explicit flags override environment selectors.
Conflicting explicit preset/component flags are errors.
Every state root is scoped to the target home. This entry point does not change
system configuration, account login shells, auth, history imports, or indexes.
HELP
            exit 0 ;;
        --plan) DEPLOY_PLAN=true; shift ;;
        --apply-only) DEPLOY_APPLY_ONLY=true; shift ;;
        --home|--platform|--role|--profile|--class|--arch|--source)
            [ "$#" -ge 2 ] || fail "$1 requires a value"
            case "$1" in
                --home) DEPLOY_HOME="$2" ;;
                --platform) CLI_PLATFORM="$2" ;;
                --role) CLI_ROLE="$2" ;;
                --profile) CLI_PROFILE="$2" ;;
                --class) CLI_CLASS="$2" ;;
                --arch) CLI_ARCH="$2" ;;
                --source) DEPLOY_SOURCE="$2" ;;
            esac
            shift 2 ;;
        *) fail "unknown option: $1" ;;
    esac
done

case "$DEPLOY_HOME" in /*) ;; *) fail "--home must be an absolute path" ;; esac
[ "$DEPLOY_HOME" != / ] || fail '--home cannot be the filesystem root'
DEPLOY_HOME=${DEPLOY_HOME%/}
DEPLOY_SOURCE="$(cd "$DEPLOY_SOURCE" 2>/dev/null && pwd -P)" || fail '--source must be an existing source directory'
[ -f "$DEPLOY_SOURCE/.chezmoi.toml.tmpl" ] || fail '--source must contain the chezmoi source template'
[ "$DEPLOY_HOME" != "$DEPLOY_SOURCE" ] || fail '--home cannot equal --source'
# shellcheck source=deployment/profile.sh
source "$DEPLOY_SOURCE/deployment/profile.sh"
resolve_profile
# shellcheck source=deployment/installers.sh
source "$DEPLOY_SOURCE/deployment/installers.sh"
if "$DEPLOY_APPLY_ONLY"; then
    DEPLOY_ACTIONS=(apply-source)
fi
if "$DEPLOY_PLAN"; then
    printf '{"platform":'; json_string "$DEPLOY_PLATFORM"
    printf ',"role":'; json_string "$DEPLOY_ROLE"
    printf ',"arch":'; json_string "$DEPLOY_ARCH"
    printf ',"profile":'; json_string "$DEPLOY_PROFILE"
    printf ',"class":'; json_string "$DEPLOY_CLASS"
    printf ',"home":'; json_string "$DEPLOY_HOME"
    printf ',"source":'; json_string "$DEPLOY_SOURCE"
    printf ',"tools":'; json_array "${DEPLOY_TOOLS[@]}"
    printf ',"packages":'; print_common_packages
    printf ',"managers":{"pixi":'; json_string "$PIXI_VERSION"
    printf ',"chezmoi":'; json_string "$CHEZMOI_VERSION"
    printf ',"rustup":'; json_string "$RUSTUP_VERSION"; printf '}'
    printf ',"actions":'; json_array "${DEPLOY_ACTIONS[@]}"
    printf ',"roots":{"config":'; json_string "$DEPLOY_HOME/.config"
    printf ',"data":'; json_string "$DEPLOY_HOME/.local/share"
    printf ',"state":'; json_string "$DEPLOY_HOME/.local/state"
    printf ',"cache":'; json_string "$DEPLOY_HOME/.cache"
    printf ',"pixi":'; json_string "$DEPLOY_HOME/.pixi"
    printf ',"bun":'; json_string "$DEPLOY_HOME/.bun"
    printf '},"settings":{"mode":"copy","primaryShell":"nu","systemChanges":false,"loginShellChanges":false}}\n'
    exit 0
fi

# Refuse pre-existing state directory symlinks before mkdir or installers can
# follow them. This check covers every parent used during state preparation.
[ ! -L "$DEPLOY_HOME" ] || fail "target home is a symlink: $DEPLOY_HOME"
for relative in .local .local/bin .local/bin/chezmoi .local/run .local/share .local/state .config .config/chezmoi .config/dotfiles .cache .cache/tmp .pixi .pixi/bin .pixi/bin/pixi .pixi/manifests .pixi/manifests/pixi-global.toml .bun .bun/install .bun/install/global .cargo .cargo/bin .rustup .codex .claude; do
    [ ! -L "$DEPLOY_HOME/$relative" ] || fail "target state root is a symlink: $DEPLOY_HOME/$relative"
done

# History databases and credentials remain within the selected device root.
for relative in .config/atuin .config/atuin/config.toml .local/share/atuin .local/share/atuin/meta.db .local/share/atuin/history.db .local/share/atuin/records.db .local/share/atuin/key .local/share/atuin/session; do
    [ ! -L "$DEPLOY_HOME/$relative" ] || fail "target history state path is a symlink: $DEPLOY_HOME/$relative"
done
# A designated home also designates every package-manager and XDG state root.
# Inherited roots cannot route a simulated deployment into the actual host.
export HOME="$DEPLOY_HOME"
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state" XDG_CACHE_HOME="$HOME/.cache"
export XDG_RUNTIME_DIR="$HOME/.local/run"
export PIXI_HOME="$HOME/.pixi" PIXI_CACHE_DIR="$HOME/.cache/pixi"
export BUN_INSTALL="$HOME/.bun" BUN_INSTALL_CACHE_DIR="$HOME/.cache/bun/install"
export CARGO_HOME="$HOME/.cargo" RUSTUP_HOME="$HOME/.rustup"
export UV_CACHE_DIR="$HOME/.cache/uv" UV_TOOL_DIR="$HOME/.local/share/uv/tools" UV_TOOL_BIN_DIR="$HOME/.local/bin"
export PIP_CACHE_DIR="$HOME/.cache/pip"
export NPM_CONFIG_USERCONFIG="$HOME/.npmrc" NPM_CONFIG_CACHE="$HOME/.cache/npm"
export ATUIN_CONFIG_DIR="$HOME/.config/atuin" ATUIN_DATA_DIR="$HOME/.local/share/atuin"
export CODEX_HOME="$HOME/.codex" CLAUDE_CONFIG_DIR="$HOME/.claude"
export HISTFILE="$HOME/.bash_history" TMPDIR="$HOME/.cache/tmp"
export PATH="$HOME/.local/bin:$HOME/.pixi/bin:$HOME/.bun/bin:$CARGO_HOME/bin:$PATH"
export DOTFILES_PLATFORM="$DEPLOY_PLATFORM" DOTFILES_ROLE="$DEPLOY_ROLE" DOTFILES_ARCH="$DEPLOY_ARCH"
unset DOTFILES_CLASS DOTFILES_PROFILE

DEPLOY_STEP=prepare-state
trap report_failure ERR
set -E
mkdir -p "$HOME/.local/bin" "$XDG_CONFIG_HOME/chezmoi" "$TMPDIR" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
run_step install-managers install_managers
DEPLOY_STEP=apply-source
"$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --cache "$XDG_CACHE_HOME/chezmoi" --persistent-state "$XDG_CONFIG_HOME/chezmoi/chezmoistate.boltdb" --no-tty --force init --data=false
"$DEPLOY_CHEZMOI" --source "$DEPLOY_SOURCE" --destination "$HOME" --config "$XDG_CONFIG_HOME/chezmoi/chezmoi.toml" --cache "$XDG_CACHE_HOME/chezmoi" --persistent-state "$XDG_CONFIG_HOME/chezmoi/chezmoistate.boltdb" --no-tty --force apply
if ! "$DEPLOY_APPLY_ONLY"; then
    run_step install-common install_common
    run_step install-agents install_agents
    run_step prepare-shell prepare_shell
fi
printf 'dotfiles: applied %s to %s (copy mode)\n' "$DEPLOY_PROFILE" "$HOME"
