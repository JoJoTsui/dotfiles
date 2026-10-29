#!/usr/bin/env bash
# Public deployment boundary. Bash 3.2-compatible for fresh macOS hosts.
set -euo pipefail

DEPLOY_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
DEPLOY_HOME="${HOME:?HOME must be set}"
DEPLOY_PLAN=false
DEPLOY_APPLY_ONLY=false
DEPLOY_AGENTS_ONLY=false
DEPLOY_SYSTEM_CONFIG=false
DEPLOY_LOGIN_SHELL=false
DEPLOY_PROXY=false
CLI_PLATFORM='' CLI_ROLE='' CLI_PROFILE='' CLI_CLASS='' CLI_ARCH=''
CLI_BUNDLES='' CLI_BUNDLES_SET=false
CLI_AGENTS='' CLI_AGENTS_SET=false

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
  --bundles LIST            none (default), or comma-separated bio,gpu,desktop,developer,developer-portable
  --agents SELECTION        all (default), none, or kimi,pi,opencode,claude,codex,minimax,qoder
  --system-config           Add managed Bash defaults to the system Bash rc
  --login-shell             Set this account's login shell to the managed Nu launcher
  --apply-only              Apply files with chezmoi; skip tool/agent installers
  --agents-only             Apply files and install agents with an existing toolchain
  --proxy                   Install Mihomo from the pinned release and refresh the profile

Environment selectors: DOTFILES_PLATFORM, DOTFILES_ROLE, DOTFILES_PROFILE,
DOTFILES_CLASS, DOTFILES_ARCH, DOTFILES_AGENTS, DOTFILES_BUNDLES, DOTFILES_PROXY,
DOTFILES_MIRROR (tuna or upstream).
Explicit flags override environment selectors.
Conflicting explicit preset/component flags are errors.
Every state root is scoped to the target home. System Bash configuration and
the account login shell change only with their explicit options; auth, history
imports, and project indexes remain separate actions.
HELP
            exit 0 ;;
        --plan) DEPLOY_PLAN=true; shift ;;
        --apply-only) DEPLOY_APPLY_ONLY=true; shift ;;
        --agents-only) DEPLOY_AGENTS_ONLY=true; shift ;;
        --system-config) DEPLOY_SYSTEM_CONFIG=true; shift ;;
        --proxy) DEPLOY_PROXY=true; shift ;;
        --login-shell) DEPLOY_LOGIN_SHELL=true; shift ;;
        --home|--platform|--role|--profile|--class|--arch|--source|--agents|--bundles)
            [ "$#" -ge 2 ] || fail "$1 requires a value"
            case "$1" in
                --home) DEPLOY_HOME="$2" ;;
                --platform) CLI_PLATFORM="$2" ;;
                --role) CLI_ROLE="$2" ;;
                --profile) CLI_PROFILE="$2" ;;
                --class) CLI_CLASS="$2" ;;
                --arch) CLI_ARCH="$2" ;;
                --source) DEPLOY_SOURCE="$2" ;;
                --bundles) CLI_BUNDLES="$2"; CLI_BUNDLES_SET=true ;;
                --agents) CLI_AGENTS="$2"; CLI_AGENTS_SET=true ;;
            esac
            shift 2 ;;
        *) fail "unknown option: $1" ;;
    esac
done
if [ "${DOTFILES_PROXY:-false}" = true ] && ! "$DEPLOY_PROXY"; then DEPLOY_PROXY=true; fi
if "$DEPLOY_APPLY_ONLY" && "$DEPLOY_AGENTS_ONLY"; then fail '--apply-only and --agents-only conflict'; fi
if "$DEPLOY_PROXY" && { "$DEPLOY_APPLY_ONLY" || "$DEPLOY_AGENTS_ONLY"; }; then
    fail '--proxy requires a full deployment with common tools'
fi
if "$DEPLOY_LOGIN_SHELL" && { "$DEPLOY_APPLY_ONLY" || "$DEPLOY_AGENTS_ONLY"; }; then
    fail '--login-shell requires a full deployment with shell preparation'
fi

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
if "$DEPLOY_SYSTEM_CONFIG" || "$DEPLOY_LOGIN_SHELL"; then
    case "$DEPLOY_PLATFORM" in linux|wsl|macos) ;; *) fail 'system and login-shell options are unavailable on native Windows' ;; esac
fi
if "$DEPLOY_APPLY_ONLY"; then
    DEPLOY_ACTIONS=(apply-source)
elif "$DEPLOY_AGENTS_ONLY"; then
    DEPLOY_ACTIONS=(install-managers apply-source install-agents)
fi
if "$DEPLOY_PROXY"; then DEPLOY_ACTIONS+=(install-proxy); fi
if "$DEPLOY_SYSTEM_CONFIG"; then DEPLOY_ACTIONS+=(configure-system); fi
if "$DEPLOY_LOGIN_SHELL"; then DEPLOY_ACTIONS+=(set-login-shell); fi
if "$DEPLOY_PLAN"; then
    printf '{"platform":'; json_string "$DEPLOY_PLATFORM"
    printf ',"role":'; json_string "$DEPLOY_ROLE"
    printf ',"arch":'; json_string "$DEPLOY_ARCH"
    printf ',"profile":'; json_string "$DEPLOY_PROFILE"
    printf ',"mirror":'; json_string "$DEPLOY_MIRROR"
    printf ',"class":'; json_string "$DEPLOY_CLASS"
    printf ',"home":'; json_string "$DEPLOY_HOME"
    printf ',"source":'; json_string "$DEPLOY_SOURCE"
    printf ',"tools":'; json_array "${DEPLOY_TOOLS[@]}"
    printf ',"packages":'; if "$DEPLOY_AGENTS_ONLY"; then printf '[]'; else print_common_packages; fi
    printf ',"bundles":'; json_array ${DEPLOY_BUNDLES[@]+"${DEPLOY_BUNDLES[@]}"}
    printf ',"bundlePackages":'; if "$DEPLOY_AGENTS_ONLY"; then printf '[]'; else print_bundle_packages; fi
    printf ',"bundlePrerequisites":'; print_bundle_prerequisites
    printf ',"agents":'; json_array ${DEPLOY_AGENTS[@]+"${DEPLOY_AGENTS[@]}"}
    printf ',"agentPackages":'; print_agent_packages
    printf ',"managers":{"pixi":'; json_string "$PIXI_VERSION"
    printf ',"chezmoi":'; json_string "$CHEZMOI_VERSION"
    printf ',"rustup":'; json_string "$RUSTUP_VERSION"; printf '}'
    printf ',"proxy":'; if "$DEPLOY_PROXY"; then printf 'true'; else printf 'false'; fi
    printf ',"actions":'; json_array "${DEPLOY_ACTIONS[@]}"
    printf ',"roots":{"config":'; json_string "$DEPLOY_HOME/.config"
    printf ',"data":'; json_string "$DEPLOY_HOME/.local/share"
    printf ',"state":'; json_string "$DEPLOY_HOME/.local/state"
    printf ',"cache":'; json_string "$DEPLOY_HOME/.cache"
    printf ',"pixi":'; json_string "$DEPLOY_HOME/.pixi"
    printf ',"bun":'; json_string "$DEPLOY_HOME/.bun"
    printf '},"settings":{"mode":"copy","primaryShell":"nu","systemChanges":'
    if "$DEPLOY_SYSTEM_CONFIG" || "$DEPLOY_LOGIN_SHELL"; then printf 'true'; else printf 'false'; fi
    printf ',"loginShellChanges":'
    if "$DEPLOY_LOGIN_SHELL"; then printf 'true'; else printf 'false'; fi
    printf '}}\n'
    exit 0
fi

# Account and system actions are unavailable to simulated-home applies, even
# when their explicit switches are present. Resolve the passwd home separately
# from HOME so an isolated test environment cannot impersonate the real account.
if "$DEPLOY_SYSTEM_CONFIG" || "$DEPLOY_LOGIN_SHELL"; then
    assert_real_account_home
fi

# Refuse pre-existing state directory symlinks before mkdir or installers can
# follow them. This check covers every parent used during state preparation.
[ ! -L "$DEPLOY_HOME" ] || fail "target home is a symlink: $DEPLOY_HOME"
for relative in .local .local/bin .local/bin/chezmoi .local/run .local/share .local/state .config .config/chezmoi .config/dotfiles .config/opencode .cache .cache/tmp .pixi .pixi/bin .pixi/bin/pixi .pixi/manifests .pixi/manifests/pixi-global.toml .bun .bun/bin .bun/managed .bun/install .bun/install/global .cargo .cargo/bin .rustup .codex .claude .kimi-code .pi .pi/agent .qoder .minimax .minimax-code .minimax-code-install-logs; do
    [ ! -L "$DEPLOY_HOME/$relative" ] || fail "target state root is a symlink: $DEPLOY_HOME/$relative"
done
DEPLOY_STEP=apply-source.skills
validate_skill_catalog
DEPLOY_STEP=apply-source.agent-payload
validate_agent_payload
DEPLOY_STEP=apply-source.client-settings
validate_client_settings
DEPLOY_STEP=apply-source.macos-discovery
validate_macos_config

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
export npm_config_userconfig="$NPM_CONFIG_USERCONFIG" npm_config_cache="$NPM_CONFIG_CACHE" npm_config_prefix="$HOME/.local"
export ATUIN_CONFIG_DIR="$HOME/.config/atuin" ATUIN_DATA_DIR="$HOME/.local/share/atuin"
export CODEX_HOME="$HOME/.codex"
# Claude's override also relocates its user .claude.json into that directory.
# Normal HOME discovery keeps settings in .claude and user MCP/auth at .claude.json.
unset CLAUDE_CONFIG_DIR
export KIMI_CODE_HOME="$HOME/.kimi-code" PI_CODING_AGENT_DIR="$HOME/.pi/agent"
export OPENCODE_CONFIG_DIR="$HOME/.config/opencode" OPENCODE_CONFIG="$HOME/.config/opencode/opencode.jsonc"
unset OPENCODE_CONFIG_CONTENT OPENCODE_CLI_CONFIG_CONTENT
export MINIMAX_DATA_DIR="$HOME/.minimax" QODER_CONFIG_DIR="$HOME/.qoder"
unset MAVIS_DATA_DIR QODER_HOME QODER_USER_CONFIG_DIR
export HISTFILE="$HOME/.bash_history" TMPDIR="$HOME/.cache/tmp"
export PATH="$HOME/.local/bin:$HOME/.pixi/bin:$HOME/.bun/bin:$CARGO_HOME/bin:$PATH"
export DOTFILES_PLATFORM="$DEPLOY_PLATFORM" DOTFILES_ROLE="$DEPLOY_ROLE" DOTFILES_ARCH="$DEPLOY_ARCH"
export DOTFILES_BUNDLES="$DEPLOY_BUNDLES_CSV"
export DOTFILES_MIRROR="$DEPLOY_MIRROR"
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
run_step apply-source.skills prepare_skill_library
trap 'cleanup_skill_library' EXIT
run_step apply-source.agent-payload deploy_agent_payload
cleanup_skill_library
run_step apply-source.client-settings deploy_client_settings
run_step apply-source.macos-discovery deploy_macos_config
if "$DEPLOY_AGENTS_ONLY"; then
    run_step install-agents install_agents
elif ! "$DEPLOY_APPLY_ONLY"; then
    run_step install-common install_common
    run_step install-agents install_agents
    if "$DEPLOY_PROXY"; then run_step install-proxy install_proxy; fi
    run_step prepare-shell prepare_shell
fi
if "$DEPLOY_SYSTEM_CONFIG"; then run_step configure-system configure_system; fi
if "$DEPLOY_LOGIN_SHELL"; then run_step set-login-shell set_login_shell; fi
if "$DEPLOY_AGENTS_ONLY"; then
    printf 'dotfiles: applied agent files and selected packages for %s to %s (copy mode)\n' "$DEPLOY_PROFILE" "$HOME"
else
    printf 'dotfiles: applied %s to %s (copy mode)\n' "$DEPLOY_PROFILE" "$HOME"
fi
