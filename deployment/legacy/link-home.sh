#!/usr/bin/env bash
# Relink a legacy pre-chezmoi home directory to a live dotfiles tree.
#
# Ordinary deployments use chezmoi copy mode and never run this utility. This
# path is for hosts such as T9K whose home entries are symlinks into a live tree
# that contains this checkout. It is deliberately under deployment/ (ignored by
# .chezmoiignore) so bootstrap and source application cannot run it.
set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit 1
REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd -P) || exit 1
MANIFEST="$SCRIPT_DIR/home-links.tsv"
DEFAULT_SOURCE=$(dirname -- "$REPO_ROOT")

SOURCE=$DEFAULT_SOURCE
TARGET_HOME=${HOME:-}
GROUP_FILTER=
MODE='link'
DRY_RUN=false
STRICT=false
SYSTEM=false
RUN_STAMP=$(date +%Y%m%d-%H%M%S)

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != dumb ]; then
    C_RED=$'\033[0;31m'
    C_GREEN=$'\033[0;32m'
    C_YELLOW=$'\033[1;33m'
    C_BLUE=$'\033[0;34m'
    C_RESET=$'\033[0m'
else
    C_RED='' C_GREEN='' C_YELLOW='' C_BLUE='' C_RESET=''
fi

log_info() { printf '%s[INFO]%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
log_success() { printf '%s[OK]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
log_warn() { printf '%s[WARN]%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
log_error() { printf '%s[ERROR]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
die() { log_error "$*"; exit 1; }

usage() {
    cat <<EOF
Usage: ${0##*/} [options]

Relink a legacy pre-chezmoi home directory to a live dotfiles tree. The
manifest lists top-level home entries; each target becomes a symlink to the
same entry under --source. Existing targets are moved to a timestamped
.bak.YYYYmmdd-HHMMSS backup before they are replaced.

Options:
  --source DIR    legacy tree containing the dotfiles payload
                  (default: parent of this checkout, $DEFAULT_SOURCE)
  --home DIR      destination home directory (default: \$HOME)
  --groups LIST   link only these comma-separated manifest groups
                  (default: all; use --list to see group names)
  -n, --dry-run   print planned changes without modifying anything
  --check         report link state; exit 1 when selected links need changes
  --list          list selected manifest entries and exit
  --system        also relink /etc/bash.bashrc through sudo (legacy hosts)
  --strict        fail if any selected source path is missing
  -h, --help      show this help

Examples:
  ${0##*/} --check
  ${0##*/} --groups agents --dry-run
  ${0##*/} --source /srv/legacy --home /home/example

The utility is never run by bootstrap. On a chezmoi-managed host use
bootstrap.sh instead of converting the home directory to symlinks.
EOF
}

usage_error() {
    log_error "$*"
    usage >&2
    exit 2
}

physical_dir() {
    [ -d "$1" ] || return 1
    (CDPATH='' cd -- "$1" && pwd -P)
}

assert_mode() {
    if [ "$MODE" != link ] && [ "$MODE" != "$1" ]; then
        usage_error "--check and --list cannot be combined"
    fi
    MODE=$1
}

add_groups() {
    [ -n "$1" ] || usage_error "--groups requires a value"
    if [ -z "$GROUP_FILTER" ]; then
        GROUP_FILTER=$1
    else
        GROUP_FILTER="$GROUP_FILTER,$1"
    fi
}

while [ "$#" -gt 0 ]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -n|--dry-run)
            DRY_RUN=true
            ;;
        --check)
            assert_mode check
            ;;
        --list)
            assert_mode list
            ;;
        --strict)
            STRICT=true
            ;;
        --system)
            SYSTEM=true
            ;;
        --source)
            [ "$#" -ge 2 ] || usage_error "--source requires a directory"
            SOURCE=$2
            shift
            ;;
        --source=*)
            SOURCE=${1#*=}
            [ -n "$SOURCE" ] || usage_error "--source requires a directory"
            ;;
        --home)
            [ "$#" -ge 2 ] || usage_error "--home requires a directory"
            TARGET_HOME=$2
            shift
            ;;
        --home=*)
            TARGET_HOME=${1#*=}
            [ -n "$TARGET_HOME" ] || usage_error "--home requires a directory"
            ;;
        --groups)
            [ "$#" -ge 2 ] || usage_error "--groups requires a value"
            add_groups "$2"
            shift
            ;;
        --groups=*)
            add_groups "${1#*=}"
            ;;
        --)
            shift
            [ "$#" -eq 0 ] || usage_error "unexpected argument: $1"
            ;;
        -*)
            usage_error "unknown option: $1"
            ;;
        *)
            usage_error "unexpected argument: $1"
            ;;
    esac
    shift
done

[ -n "$TARGET_HOME" ] || usage_error "HOME is not set; pass --home"
[ -f "$MANIFEST" ] || die "manifest not found: $MANIFEST"

ENTRY_GROUPS=()
ENTRY_PATHS=()
KNOWN_GROUPS=
ENTRY_COUNT=0

while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in
        ''|'#'*) continue ;;
    esac
    IFS='|' read -r group path extra <<< "$line"
    [ -n "${group:-}" ] && [ -n "${path:-}" ] ||
        die "malformed manifest row: $line"
    [ -z "${extra:-}" ] ||
        die "manifest rows take exactly two pipe-separated fields: $line"
    case "$group" in
        *[!a-z0-9-]*) die "invalid manifest group '$group'" ;;
    esac
    case "$path" in
        */*) die "manifest paths must be top-level home entries: $path" ;;
    esac
    case "/$path/" in
        //*|*/../*|*/./*|*//*) die "unsafe manifest path: $path" ;;
    esac
    i=0
    while [ "$i" -lt "$ENTRY_COUNT" ]; do
        [ "${ENTRY_PATHS[$i]}" != "$path" ] ||
            die "duplicate manifest path: $path"
        i=$((i + 1))
    done
    ENTRY_GROUPS+=("$group")
    ENTRY_PATHS+=("$path")
    ENTRY_COUNT=$((ENTRY_COUNT + 1))
    case " $KNOWN_GROUPS " in
        *" $group "*) ;;
        *) KNOWN_GROUPS="$KNOWN_GROUPS $group" ;;
    esac
done < "$MANIFEST"

[ "$ENTRY_COUNT" -gt 0 ] || die "manifest is empty: $MANIFEST"

if [ -n "$GROUP_FILTER" ] && [ "$GROUP_FILTER" != all ]; then
    case ",$GROUP_FILTER," in
        *,all,*) usage_error "--groups all cannot be combined with other groups" ;;
    esac
    IFS=, read -r -a requested_groups <<< "$GROUP_FILTER"
    i=0
    while [ "$i" -lt "${#requested_groups[@]}" ]; do
        group=${requested_groups[$i]}
        [ -n "$group" ] || usage_error "empty group name in --groups"
        case " $KNOWN_GROUPS " in
            *" $group "*) ;;
            *) usage_error "unknown group '$group' (known:$KNOWN_GROUPS)" ;;
        esac
        i=$((i + 1))
    done
fi

group_selected() {
    if [ -z "$GROUP_FILTER" ] || [ "$GROUP_FILTER" = all ]; then
        return 0
    fi
    case ",$GROUP_FILTER," in
        *",$1,"*) return 0 ;;
    esac
    return 1
}

SELECTED_PATHS=()
i=0
while [ "$i" -lt "$ENTRY_COUNT" ]; do
    if group_selected "${ENTRY_GROUPS[$i]}"; then
        SELECTED_PATHS+=("${ENTRY_PATHS[$i]}")
    fi
    i=$((i + 1))
done

[ "${#SELECTED_PATHS[@]}" -gt 0 ] || die "no manifest entries selected"

if [ "$MODE" = list ]; then
    printf '%-10s %s\n' GROUP PATH
    i=0
    while [ "$i" -lt "$ENTRY_COUNT" ]; do
        if group_selected "${ENTRY_GROUPS[$i]}"; then
            printf '%-10s %s\n' "${ENTRY_GROUPS[$i]}" "${ENTRY_PATHS[$i]}"
        fi
        i=$((i + 1))
    done
    exit 0
fi

SOURCE=$(physical_dir "$SOURCE") ||
    die "source directory does not exist: $SOURCE"
TARGET_HOME=$(physical_dir "$TARGET_HOME") ||
    die "home directory does not exist: $TARGET_HOME"
[ "$SOURCE" != "$TARGET_HOME" ] ||
    die "source and home are the same; pass --source explicitly"

points_to() {
    local target=$1 expected=$2 destination resolved expected_resolved
    [ -L "$target" ] || return 1
    destination=$(readlink "$target") || return 1
    case "$destination" in
        /*) ;;
        *) destination=$(dirname -- "$target")/$destination ;;
    esac
    [ "$destination" = "$expected" ] && return 0
    if command -v realpath >/dev/null 2>&1; then
        resolved=$(realpath "$target" 2>/dev/null) || return 1
        expected_resolved=$(realpath "$expected" 2>/dev/null) || expected_resolved=$expected
        [ "$resolved" = "$expected_resolved" ] && return 0
    fi
    return 1
}

describe_target() {
    if [ -L "$1" ]; then
        printf 'symlink -> %s' "$(readlink "$1")"
    elif [ -d "$1" ]; then
        printf 'directory'
    elif [ -e "$1" ]; then
        printf 'file'
    else
        printf 'absent'
    fi
}

unique_backup() {
    local target=$1 candidate n=0
    candidate="${target}.bak.${RUN_STAMP}"
    while [ -e "$candidate" ] || [ -L "$candidate" ]; do
        n=$((n + 1))
        candidate="${target}.bak.${RUN_STAMP}-${n}"
    done
    printf '%s' "$candidate"
}

system_admin() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
        return
    fi
    command -v sudo >/dev/null 2>&1 ||
        die "sudo is required for --system"
    sudo "$@"
}

# Validate every selected entry before writing anything. This catches a wrong
# --source and recursive target/source combinations without half-applying a run.
FOUND_SOURCES=0
MISSING_SOURCES=0
i=0
while [ "$i" -lt "${#SELECTED_PATHS[@]}" ]; do
    path=${SELECTED_PATHS[$i]}
    source_path="$SOURCE/$path"
    target_path="$TARGET_HOME/$path"
    if [ -e "$source_path" ]; then
        FOUND_SOURCES=$((FOUND_SOURCES + 1))
    else
        MISSING_SOURCES=$((MISSING_SOURCES + 1))
        if [ "$STRICT" = true ]; then
            log_warn "missing source: $source_path"
        fi
    fi
    [ "$source_path" != "$target_path" ] ||
        die "refusing to link a path to itself: $target_path"
    if [ "${source_path#"$target_path"/}" != "$source_path" ]; then
        die "refusing to link $target_path: it would contain source $source_path"
    fi
    i=$((i + 1))
done

[ "$FOUND_SOURCES" -gt 0 ] ||
    die "none of the selected sources exist under $SOURCE; check --source"
if [ "$STRICT" = true ] && [ "$MISSING_SOURCES" -gt 0 ]; then
    die "$MISSING_SOURCES selected source path(s) missing under $SOURCE"
fi
if [ "$MODE" = link ] && [ "$DRY_RUN" = false ] && [ ! -w "$TARGET_HOME" ]; then
    die "home directory is not writable: $TARGET_HOME"
fi

if [ "$SYSTEM" = true ]; then
    SYSTEM_SOURCE="$SOURCE/bash.bashrc"
    SYSTEM_TARGET=/etc/bash.bashrc
    [ -e "$SYSTEM_SOURCE" ] ||
        die "--system requested but $SYSTEM_SOURCE is missing"
    if [ "$MODE" = link ] && [ "$DRY_RUN" = false ] &&
        { [ -e "$SYSTEM_TARGET" ] || [ -L "$SYSTEM_TARGET" ]; } &&
        ! points_to "$SYSTEM_TARGET" "$SYSTEM_SOURCE"; then
        if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
            die "sudo is required for --system"
        fi
    fi
fi

log_info "legacy source: $SOURCE"
log_info "target home: $TARGET_HOME"

OK_COUNT=0
LINK_COUNT=0
BACKUP_COUNT=0
PLAN_COUNT=0
WRONG_COUNT=0
MISSING_TARGETS=0

i=0
while [ "$i" -lt "${#SELECTED_PATHS[@]}" ]; do
    path=${SELECTED_PATHS[$i]}
    source_path="$SOURCE/$path"
    target_path="$TARGET_HOME/$path"
    i=$((i + 1))

    if [ ! -e "$source_path" ]; then
        if [ "$MODE" = check ]; then
            printf '%-8s %s (source missing)\n' SKIP "$path"
        else
            log_warn "source missing, skipping: $source_path"
        fi
        continue
    fi

    if points_to "$target_path" "$source_path"; then
        OK_COUNT=$((OK_COUNT + 1))
        [ "$MODE" = check ] && printf '%-8s %s\n' OK "$path"
        continue
    fi

    if [ "$MODE" = check ]; then
        if [ -L "$target_path" ] || [ -e "$target_path" ]; then
            WRONG_COUNT=$((WRONG_COUNT + 1))
            printf '%-8s %s (%s)\n' DRIFT "$path" "$(describe_target "$target_path")"
        else
            MISSING_TARGETS=$((MISSING_TARGETS + 1))
            printf '%-8s %s -> %s\n' MISSING "$path" "$source_path"
        fi
        continue
    fi

    if [ "$DRY_RUN" = true ]; then
        if [ -L "$target_path" ] || [ -e "$target_path" ]; then
            log_info "would back up $path ($(describe_target "$target_path")) and link -> $source_path"
        else
            log_info "would link $path -> $source_path"
        fi
        PLAN_COUNT=$((PLAN_COUNT + 1))
        continue
    fi

    backup=
    if [ -L "$target_path" ] || [ -e "$target_path" ]; then
        backup=$(unique_backup "$target_path")
        log_info "backup: $path -> ${backup##*/}"
        mv -- "$target_path" "$backup" ||
            die "failed to back up $target_path"
        BACKUP_COUNT=$((BACKUP_COUNT + 1))
    fi

    if ! ln -s -- "$source_path" "$target_path"; then
        if [ -n "$backup" ]; then
            if mv -- "$backup" "$target_path"; then
                log_warn "restored previous target after link failure: $path"
            else
                log_error "link failed and backup remains at $backup"
            fi
        fi
        die "failed to link $path -> $source_path"
    fi
    LINK_COUNT=$((LINK_COUNT + 1))
    log_success "linked: $path -> $source_path"
done

if [ "$SYSTEM" = true ]; then
    if [ ! -e "$SYSTEM_TARGET" ] && [ ! -L "$SYSTEM_TARGET" ]; then
        log_warn "$SYSTEM_TARGET does not exist; skipping system link"
    elif points_to "$SYSTEM_TARGET" "$SYSTEM_SOURCE"; then
        OK_COUNT=$((OK_COUNT + 1))
        [ "$MODE" = check ] && printf '%-8s %s\n' OK "$SYSTEM_TARGET"
    elif [ "$MODE" = check ]; then
        WRONG_COUNT=$((WRONG_COUNT + 1))
        printf '%-8s %s (%s)\n' DRIFT "$SYSTEM_TARGET" "$(describe_target "$SYSTEM_TARGET")"
    elif [ "$DRY_RUN" = true ]; then
        log_info "would back up $SYSTEM_TARGET and link -> $SYSTEM_SOURCE"
        PLAN_COUNT=$((PLAN_COUNT + 1))
    else
        backup=$(unique_backup "$SYSTEM_TARGET")
        log_info "backup: $SYSTEM_TARGET -> ${backup##*/}"
        system_admin mv -- "$SYSTEM_TARGET" "$backup" ||
            die "failed to back up $SYSTEM_TARGET"
        BACKUP_COUNT=$((BACKUP_COUNT + 1))
        if ! system_admin ln -s -- "$SYSTEM_SOURCE" "$SYSTEM_TARGET"; then
            if system_admin mv -- "$backup" "$SYSTEM_TARGET"; then
                log_warn "restored previous target after link failure: $SYSTEM_TARGET"
            else
                log_error "link failed and backup remains at $backup"
            fi
            die "failed to link $SYSTEM_TARGET -> $SYSTEM_SOURCE"
        fi
        LINK_COUNT=$((LINK_COUNT + 1))
        log_success "linked: $SYSTEM_TARGET -> $SYSTEM_SOURCE"
    fi
fi

printf '\n'
if [ "$MODE" = check ]; then
    if [ "$WRONG_COUNT" -gt 0 ] || [ "$MISSING_TARGETS" -gt 0 ]; then
        log_error "drift: $WRONG_COUNT wrong, $MISSING_TARGETS missing, $OK_COUNT correct, $MISSING_SOURCES source missing"
        exit 1
    fi
    log_success "all selected links are correct ($OK_COUNT checked)"
    [ "$MISSING_SOURCES" -eq 0 ] ||
        log_warn "$MISSING_SOURCES source path(s) missing were skipped"
    exit 0
fi

if [ "$DRY_RUN" = true ]; then
    log_success "dry run complete: $PLAN_COUNT change(s) planned, $OK_COUNT already correct, $MISSING_SOURCES source missing"
    exit 0
fi

log_success "link pass complete: $LINK_COUNT linked, $BACKUP_COUNT backed up, $OK_COUNT already correct, $MISSING_SOURCES source missing"
