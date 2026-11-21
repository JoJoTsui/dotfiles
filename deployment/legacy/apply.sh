#!/usr/bin/env bash
# Apply repo-owned files to a legacy symlink home without running the public
# bootstrap. The public boundary refuses symlinked state roots; this utility
# touches only the explicitly listed files and never client settings, payload
# blocks, shell rc, authentication, packages, or runtime state.
set -uo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit 1
REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd -P) || exit 1
MANIFEST="$SCRIPT_DIR/apply.tsv"

CHECKOUT=$REPO_ROOT
HOME_DIR=${HOME:-}
LIVE_ROOT=
LIVE_ROOT_SET=false
GROUP_FILTER=
GROUP_FILTER_SET=false
TARGET_FILTER=
TARGET_FILTER_SET=false
MODE=check

usage() {
    cat <<'EOF'
Usage: apply.sh [--checkout DIR] [--home DIR] [--live-root DIR] [--groups LIST] [--targets LIST]
                [--check | --dry-run | --apply]

Apply repo-owned files to a legacy symlink home. The default is --check.

  --checkout DIR   dotfiles checkout (default: this checkout)
  --home DIR       home whose symlinks point at the live tree (default: $HOME)
  --live-root DIR  persistent tree that symlinked home entries resolve to
                   (default: parent of --checkout)
  --groups LIST    comma-separated manifest groups; "all" selects every group
                   (default: all when the flag is absent)
  --targets LIST   comma-separated manifest target paths (default: all when the
                   flag is absent)
  --check          report OK/DRIFT/MISSING/FOREIGN/CONFLICT; exit 1 on drift
  --dry-run        print planned changes and diffs; write nothing
  --apply          back up and replace the selected files
EOF
}

fail() { printf 'legacy-apply: %s\n' "$*" >&2; exit 1; }
realpath_py() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        return 1
    fi
}
file_mode() {
    if stat -c '%a' "$1" >/dev/null 2>&1; then
        stat -c '%a' "$1"
    else
        stat -f '%Lp' "$1"
    fi
}
group_selected() {
    [ -z "$GROUP_FILTER" ] && return 0
    case ",$GROUP_FILTER," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}
# Membership test for a manifest field. Blank and comment records are ignored
# exactly like the dispatcher below, so a comment header can never name a
# group or a target. The searched value travels through the environment
# because awk's -v assignment unescapes its argument, which let a name like
# "\141gent" compare equal to the group "agent". The field index stays a
# number inside this script.
manifest_has() {
    local field=$1 value=$2
    case "$field" in
        1|3) : ;;
        *) fail "internal manifest field: $field" ;;
    esac
    LEGACY_APPLY_MANIFEST_VALUE=$value awk -F '|' -v field="$field" '
        $1 == "" || $1 ~ /^#/ { next }
        $field == ENVIRON["LEGACY_APPLY_MANIFEST_VALUE"] { found = 1 }
        END { exit !found }' "$MANIFEST"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --checkout) CHECKOUT=$2; shift 2 ;;
        --home) HOME_DIR=$2; shift 2 ;;
        --live-root) LIVE_ROOT=$2; LIVE_ROOT_SET=true; shift 2 ;;
        --groups) GROUP_FILTER=$2; GROUP_FILTER_SET=true; shift 2 ;;
        --targets) TARGET_FILTER=$2; TARGET_FILTER_SET=true; shift 2 ;;
        --check) MODE=check; shift ;;
        --dry-run) MODE=dry-run; shift ;;
        --apply) MODE=apply; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[ -n "$HOME_DIR" ] || fail 'home is empty'
[ -f "$MANIFEST" ] || fail "manifest missing: $MANIFEST"
# Validate the entire selection before any write; typos must not silently skip.
# An explicit selection must carry names: an empty selection or an empty
# member is refused instead of selecting everything. The absent flag keeps the
# default selection of every record.
if [ "$TARGET_FILTER_SET" = true ]; then
    [ -n "$TARGET_FILTER" ] || fail 'targets selection is empty'
    remaining=$TARGET_FILTER
    while :; do
        target_name=${remaining%%,*}
        [ -n "$target_name" ] || fail 'targets selection has an empty member'
        manifest_has 3 "$target_name" || fail "unknown manifest target: $target_name"
        case "$remaining" in *,*) remaining=${remaining#*,} ;; *) break ;; esac
    done
fi
# An explicit group must name a manifest group; "all" keeps the default
# selection of every group. An unknown group fails before any file is written.
select_all=false
if [ "$GROUP_FILTER_SET" = true ]; then
    [ -n "$GROUP_FILTER" ] || fail 'groups selection is empty'
    remaining=$GROUP_FILTER
    while :; do
        group_name=${remaining%%,*}
        [ -n "$group_name" ] || fail 'groups selection has an empty member'
        if [ "$group_name" = all ]; then
            select_all=true
        else
            manifest_has 1 "$group_name" || fail "unknown manifest group: $group_name"
        fi
        case "$remaining" in *,*) remaining=${remaining#*,} ;; *) break ;; esac
    done
fi
[ "$select_all" = true ] && GROUP_FILTER=
[ "$LIVE_ROOT_SET" = true ] || LIVE_ROOT=$(dirname "$CHECKOUT")
LIVE_REAL=$(realpath_py "$LIVE_ROOT") || fail "cannot resolve live root: $LIVE_ROOT"
FAILURES=0

backup_target() {
    local target=$1 backup="$target.bak.$(date +%Y%m%d-%H%M%S)" suffix=1
    while [ -e "$backup" ]; do
        backup="$target.bak.$(date +%Y%m%d-%H%M%S)-$suffix"
        suffix=$((suffix + 1))
    done
    cp -p "$target" "$backup" || return 1
    printf '%s' "$backup"
}

while IFS='|' read -r group source_rel target_rel mode; do
    case "$group" in ''|\#*) continue ;; esac
    group_selected "$group" || continue
    if [ -n "$TARGET_FILTER" ]; then
        case ",$TARGET_FILTER," in *",$target_rel,"*) ;; *) continue ;; esac
    fi
    case "$source_rel$target_rel" in *..*) printf 'CONFLICT %s\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue ;; esac
    case "$source_rel" in /*) printf 'CONFLICT %s\n' "$source_rel" >&2; FAILURES=$((FAILURES + 1)); continue ;; esac
    case "$target_rel" in /*) printf 'CONFLICT %s\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue ;; esac
    case "$mode" in 0[0-7][0-7][0-7]) ;; *) printf 'FOREIGN %s mode=%s\n' "$target_rel" "$mode" >&2; FAILURES=$((FAILURES + 1)); continue ;; esac
    source_file="$CHECKOUT/$source_rel"
    target="$HOME_DIR/$target_rel"
    if [ ! -f "$source_file" ] || [ -L "$source_file" ]; then
        printf 'CONFLICT %s (source missing or symlink)\n' "$source_rel" >&2
        FAILURES=$((FAILURES + 1))
        continue
    fi
    if [ -L "$target" ] || { [ -e "$target" ] && [ ! -f "$target" ]; }; then
        printf 'FOREIGN %s (target is not a regular file)\n' "$target_rel" >&2
        FAILURES=$((FAILURES + 1))
        continue
    fi
    target_real=$(realpath_py "$target") || { printf 'CONFLICT %s\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
    case "$target_real" in
        "$LIVE_REAL"/*) ;;
        *) printf 'CONFLICT %s (outside live root %s)\n' "$target_rel" "$LIVE_REAL" >&2; FAILURES=$((FAILURES + 1)); continue ;;
    esac
    if [ ! -f "$target" ]; then
        printf 'MISSING %s\n' "$target_rel"
        if [ "$MODE" = dry-run ]; then printf '  would create %s\n' "$target_rel"; continue; fi
        if [ "$MODE" = check ]; then FAILURES=$((FAILURES + 1)); continue; fi
        [ -d "$(dirname "$target_real")" ] || { printf 'CONFLICT %s parent missing\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        temporary="$target_real.tmp.$$"
        cp -p "$source_file" "$temporary" || { printf 'CONFLICT %s copy failed\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        chmod "$mode" "$temporary" || { rm -f "$temporary"; FAILURES=$((FAILURES + 1)); continue; }
        mv -f "$temporary" "$target_real" || { rm -f "$temporary"; FAILURES=$((FAILURES + 1)); continue; }
        printf 'WRITE %s\n' "$target_rel"
        continue
    fi
    source_hash=$(hash_file "$source_file") || fail 'no SHA-256 tool'
    target_hash=$(hash_file "$target") || fail 'no SHA-256 tool'
    want_mode=${mode#0}
    target_mode=$(file_mode "$target") || { printf 'CONFLICT %s mode unreadable\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
    target_mode=${target_mode#0}
    content_same=false
    [ "$source_hash" = "$target_hash" ] && content_same=true
    mode_same=false
    [ "$want_mode" = "$target_mode" ] && mode_same=true
    if [ "$content_same" = true ] && [ "$mode_same" = true ]; then
        printf 'OK %s\n' "$target_rel"
        continue
    fi
    if [ "$content_same" = true ]; then
        printf 'DRIFT %s (mode %s -> %s)\n' "$target_rel" "$target_mode" "$want_mode"
    else
        printf 'DRIFT %s\n' "$target_rel"
    fi
    if [ "$MODE" = check ]; then
        FAILURES=$((FAILURES + 1))
    elif [ "$MODE" = dry-run ]; then
        if [ "$content_same" = false ]; then diff -u "$target" "$source_file" 2>/dev/null || true; fi
        if [ "$mode_same" = false ]; then printf '  would chmod %s to %s\n' "$target_rel" "$mode"; fi
    else
        [ -d "$(dirname "$target_real")" ] || { printf 'CONFLICT %s parent missing\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        backup=$(backup_target "$target") || { printf 'CONFLICT %s backup failed\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        if [ "$content_same" = false ]; then
            temporary="$target_real.tmp.$$"
            cp -p "$source_file" "$temporary" || { printf 'CONFLICT %s copy failed\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
            mv -f "$temporary" "$target_real" || { rm -f "$temporary"; FAILURES=$((FAILURES + 1)); continue; }
        fi
        chmod "$mode" "$target_real" || { printf 'CONFLICT %s chmod failed\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        printf 'WRITE %s (backup %s)\n' "$target_rel" "$backup"
    fi
done < "$MANIFEST"

[ "$FAILURES" -eq 0 ] || exit 1
[ "$MODE" = check ] && printf 'legacy apply check is clean\n'
exit 0
