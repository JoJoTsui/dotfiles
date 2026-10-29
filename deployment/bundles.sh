# Optional whole-bundle selection; declarations only until an installer runs.
# shellcheck shell=bash
# shellcheck disable=SC2034 # Public bootstrap adapter data.
DEPLOY_BUNDLES=()
DEPLOY_BUNDLES_CSV=''
bundle_selection=${DOTFILES_BUNDLES:-none}
if "$CLI_BUNDLES_SET"; then bundle_selection=$CLI_BUNDLES; fi
if [ "$bundle_selection" != none ]; then
    case "$bundle_selection" in ''|,*|*,|*,,*) fail 'bundle list contains an empty name' ;; esac
    bundle_saved_ifs=$IFS; IFS=,
    for bundle_name in $bundle_selection; do
        case "$bundle_name" in bio|gpu|desktop|developer|developer-portable) ;; *) fail "invalid bundle '$bundle_name'; use none or bio,gpu,desktop,developer,developer-portable" ;; esac
        case ",$DEPLOY_BUNDLES_CSV," in *",$bundle_name,"*) continue ;; esac
        DEPLOY_BUNDLES+=("$bundle_name")
        DEPLOY_BUNDLES_CSV=${DEPLOY_BUNDLES_CSV:+$DEPLOY_BUNDLES_CSV,}$bundle_name
    done
    IFS=$bundle_saved_ifs
fi

bundle_selected() {
    case ",$DEPLOY_BUNDLES_CSV," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}

bundle_tool_matches() {
    [ "$1" = all ] || { case ",$1," in *",$DEPLOY_PLATFORM,"*) return 0 ;; *) return 1 ;; esac; }
}

while IFS=$'|\r' read -r bundle_name bundle_targets bundle_prerequisites; do
    case "$bundle_name" in ''|\#*) continue ;; esac
    bundle_selected "$bundle_name" || continue
    case ",$bundle_targets," in
        *",$DEPLOY_PLATFORM-$DEPLOY_ARCH,"*) ;;
        *) fail "unsupported bundle '$bundle_name' for $DEPLOY_PLATFORM-$DEPLOY_ARCH; supported: $bundle_targets" ;;
    esac
done < "$DEPLOY_SOURCE/deployment/bundles.tsv"

while IFS=$'|\r' read -r bundle_name bundle_environment bundle_specs bundle_exposed bundle_channels tool_platforms; do
    case "$bundle_name" in ''|\#*) continue ;; esac
    bundle_selected "$bundle_name" || continue
    bundle_tool_matches "$tool_platforms" || continue
    bundle_saved_ifs=$IFS; IFS=,
    for bundle_mapping in $bundle_exposed; do
        DEPLOY_TOOLS+=("${bundle_mapping%%=*}")
    done
    IFS=$bundle_saved_ifs
done < "$DEPLOY_SOURCE/deployment/bundle-tools.tsv"
if bundle_selected bio; then DEPLOY_TOOLS+=(fetchChromSizes); fi
unset bundle_selection bundle_name bundle_environment bundle_specs bundle_exposed bundle_channels bundle_mapping bundle_saved_ifs bundle_targets bundle_prerequisites tool_platforms

verify_bundle_exposure() {
    local name environment specifications mappings channels mapping saved_ifs platforms
    while IFS=$'|\r' read -r name environment specifications mappings channels platforms; do
        case "$name" in ''|\#*) continue ;; esac
        bundle_selected "$name" || continue
        bundle_tool_matches "$platforms" || continue
        saved_ifs=$IFS; IFS=,
        for mapping in $mappings; do
            [ -x "$PIXI_HOME/bin/${mapping%%=*}" ] || fail "required bundle command not exposed by Pixi: ${mapping%%=*} ($name)"
        done
        IFS=$saved_ifs
    done < "$DEPLOY_SOURCE/deployment/bundle-tools.tsv"
}

print_bundle_packages() {
    local name environment specifications mappings channels item separator='' inner_separator saved_ifs platforms
    printf '['
    while IFS=$'|\r' read -r name environment specifications mappings channels platforms; do
        case "$name" in ''|\#*) continue ;; esac
        bundle_selected "$name" || continue
        bundle_tool_matches "$platforms" || continue
        printf '%s{"bundle":' "$separator"; json_string "$name"
        printf ',"environment":'; json_string "$environment"
        printf ',"dependencies":{'; inner_separator=''; saved_ifs=$IFS; IFS=,
        for item in $specifications; do
            printf '%s' "$inner_separator"; json_string "${item%%==*}"
            printf ':'; json_string "==${item#*==}"; inner_separator=,
        done
        printf '},"exposed":{'; inner_separator=''
        for item in $mappings; do
            printf '%s' "$inner_separator"; json_string "${item%%=*}"
            printf ':'; json_string "${item#*=}"; inner_separator=,
        done
        printf '},"channels":['; inner_separator=''
        for item in $channels; do
            printf '%s' "$inner_separator"; json_string "$item"; inner_separator=,
        done
        IFS=$saved_ifs
        printf ']}'; separator=,
    done < "$DEPLOY_SOURCE/deployment/bundle-tools.tsv"
    printf ']'
}

print_bundle_prerequisites() {
    local name targets prerequisites separator=''
    printf '{'
    while IFS=$'|\r' read -r name targets prerequisites; do
        case "$name" in ''|\#*) continue ;; esac
        bundle_selected "$name" || continue
        printf '%s' "$separator"; json_string "$name"
        printf ':'; json_string "$prerequisites"; separator=,
    done < "$DEPLOY_SOURCE/deployment/bundles.tsv"
    printf '}'
}
