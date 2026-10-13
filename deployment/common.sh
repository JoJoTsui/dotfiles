# Canonical desired-tool inventory shared by planning and source rendering.
# shellcheck disable=SC2034 # Sourced adapter contract.
PIXI_VERSION=0.81.0
RUSTUP_VERSION=1.29.1
DEPLOY_TOOLS=(pixi chezmoi rustup)
if [ "$DEPLOY_PLATFORM" = windows ]; then
    # Required bootstrap exceptions; installed by the native adapter.
    DEPLOY_TOOLS+=(bun bunx atuin hx jq)
fi

common_target_matches() {
    [ "$1" = all ] || { [ "$1" = unix ] && [ "$DEPLOY_PLATFORM" != windows ]; }
}

while IFS=$'|\r' read -r common_env common_specs common_exposed common_targets; do
    case "$common_env" in ''|\#*) continue ;; esac
    if common_target_matches "$common_targets"; then
        saved_ifs=$IFS; IFS=,
        for common_mapping in $common_exposed; do
            common_command=${common_mapping%%=*}
            DEPLOY_TOOLS+=("$common_command")
        done
        IFS=$saved_ifs
    fi
done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
unset common_env common_specs common_exposed common_targets common_mapping common_command saved_ifs

common_python_spec() {
    local environment specifications mappings targets specification saved_ifs
    while IFS=$'|\r' read -r environment specifications mappings targets; do
        case "$environment" in ''|\#*) continue ;; esac
        saved_ifs=$IFS; IFS=,
        for specification in $specifications; do
            if [ "${specification%%==*}" = python ]; then
                printf '%s' "$specification"
                IFS=$saved_ifs
                return
            fi
        done
        IFS=$saved_ifs
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
    fail 'common tool catalog must declare the Python bootstrap pin'
}

print_common_packages() {
    local environment specifications mappings targets separator='' item inner_separator saved_ifs
    printf '['
    while IFS=$'|\r' read -r environment specifications mappings targets; do
        case "$environment" in ''|\#*) continue ;; esac
        common_target_matches "$targets" || continue
        printf '%s{"environment":' "$separator"; json_string "$environment"
        printf ',"dependencies":{'
        inner_separator=''; saved_ifs=$IFS; IFS=,
        for item in $specifications; do
            printf '%s' "$inner_separator"; json_string "${item%%==*}"
            printf ':'; json_string "==${item#*==}"; inner_separator=,
        done
        printf '},"exposed":{'; inner_separator=''
        for item in $mappings; do
            printf '%s' "$inner_separator"; json_string "${item%%=*}"
            printf ':'; json_string "${item#*=}"; inner_separator=,
        done
        IFS=$saved_ifs
        printf '}}'; separator=,
    done < "$DEPLOY_SOURCE/deployment/common-tools.tsv"
    printf ']'
}
