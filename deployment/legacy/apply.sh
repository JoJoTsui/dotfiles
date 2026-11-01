#!/usr/bin/env bash
# Apply repo-owned files to a legacy symlink home without running the public
# bootstrap. The public boundary refuses symlinked state roots; this utility
# touches only the explicitly listed files and never client settings, payload
# blocks, shell rc, authentication, packages, or runtime state.
set -uo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit 1
REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd -P) || exit 1
MANIFEST="$SCRIPT_DIR/apply.tsv"

SOURCE=$REPO_ROOT
HOME_DIR=${HOME:-}
LIVE_ROOT=$(dirname "$SOURCE")
GROUP_FILTER=
MODE=check

usage() {
    cat <<'EOF'
Usage: apply.sh [--source DIR] [--home DIR] [--live-root DIR] [--groups LIST]
                [--check | --dry-run | --apply]

Apply repo-owned files to a legacy symlink home. The default is --check.

  --source DIR     dotfiles checkout (default: this checkout)
  --home DIR       home whose symlinks point at the live tree (default: $HOME)
  --live-root DIR  persistent tree that symlinked home entries resolve to
                   (default: parent of --source)
  --groups LIST    comma-separated manifest groups (default: all)
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
group_selected() {
    [ -z "$GROUP_FILTER" ] && return 0
    case ",$GROUP_FILTER," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}

while [ $# -gt 0 ]; do
    case "$1" in
        --source) SOURCE=$2; shift 2 ;;
        --home) HOME_DIR=$2; shift 2 ;;
        --live-root) LIVE_ROOT=$2; shift 2 ;;
        --groups) GROUP_FILTER=$2; shift 2 ;;
        --check) MODE=check; shift ;;
        --dry-run) MODE=dry-run; shift ;;
        --apply) MODE=apply; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[ -n "$HOME_DIR" ] || fail 'home is empty'
[ -f "$MANIFEST" ] || fail "manifest missing: $MANIFEST"
LIVE_REAL=$(realpath_py "$LIVE_ROOT") || fail "cannot resolve live root: $LIVE_ROOT"
FAILURES=0

while IFS='|' read -r op group source_rel target_rel mode owner render; do
    case "$op" in ''|\#*) continue ;; esac
    [ "$op" = file ] || { printf 'FOREIGN unknown operation: %s\n' "$op" >&2; FAILURES=$((FAILURES + 1)); continue; }
    group_selected "$group" || continue
    case "$source_rel$target_rel" in *..*) printf 'CONFLICT %s\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue ;; esac
    case "$source_rel" in /*) printf 'CONFLICT %s\n' "$source_rel" >&2; FAILURES=$((FAILURES + 1)); continue ;; esac
    case "$target_rel" in /*) printf 'CONFLICT %s\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue ;; esac
    [ "$owner" = repo ] || { printf 'FOREIGN %s owner=%s\n' "$target_rel" "$owner" >&2; FAILURES=$((FAILURES + 1)); continue; }
    [ "$render" = none ] || { printf 'FOREIGN %s render=%s\n' "$target_rel" "$render" >&2; FAILURES=$((FAILURES + 1)); continue; }
    source_file="$SOURCE/$source_rel"
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
        [ "$MODE" = dry-run ] && printf '  would create %s\n' "$target_rel"
        [ "$MODE" = check ] && FAILURES=$((FAILURES + 1))
        [ "$MODE" = apply ] || continue
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
    if [ "$source_hash" = "$target_hash" ]; then
        printf 'OK %s\n' "$target_rel"
        continue
    fi
    printf 'DRIFT %s\n' "$target_rel"
    if [ "$MODE" = check ]; then
        FAILURES=$((FAILURES + 1))
    elif [ "$MODE" = dry-run ]; then
        diff -u "$target" "$source_file" 2>/dev/null || true
    else
        [ -d "$(dirname "$target_real")" ] || { printf 'CONFLICT %s parent missing\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        backup="$target.bak.$(date +%Y%m%d-%H%M%S)"
        suffix=1
        while [ -e "$backup" ]; do backup="$target.bak.$(date +%Y%m%d-%H%M%S)-$suffix"; suffix=$((suffix + 1)); done
        cp -p "$target" "$backup" || { printf 'CONFLICT %s backup failed\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        temporary="$target_real.tmp.$$"
        cp -p "$source_file" "$temporary" || { printf 'CONFLICT %s copy failed\n' "$target_rel" >&2; FAILURES=$((FAILURES + 1)); continue; }
        chmod "$mode" "$temporary" || { rm -f "$temporary"; FAILURES=$((FAILURES + 1)); continue; }
        mv -f "$temporary" "$target_real" || { rm -f "$temporary"; FAILURES=$((FAILURES + 1)); continue; }
        printf 'WRITE %s (backup %s)\n' "$target_rel" "$backup"
    fi
done < "$MANIFEST"

[ "$FAILURES" -eq 0 ] || exit 1
[ "$MODE" = check ] && printf 'legacy apply check is clean\n'
exit 0
