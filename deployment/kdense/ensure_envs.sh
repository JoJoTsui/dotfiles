#!/usr/bin/env bash
# Create or reconcile the isolated environments for the filtered K-Dense skills.
#
# The skills themselves are catalog entries (deployment/skills.tsv) and deploy
# like every other managed skill. Their Python stacks cannot share one
# environment: scVelo pins an older numpy/pandas than the core stack, and
# Arboreto needs Python 3.11 with a pinned Dask. This utility keeps the three
# environments reproducible without touching the system Python or an agent
# host runtime.
#
# Usage: bash deployment/kdense/ensure_envs.sh
#   KDENSE_VENV_ROOT  parent directory for the environments (default ~/.venvs)
#   UV                uv executable (default: uv on PATH)
set -uo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit 1
VENV_ROOT=${KDENSE_VENV_ROOT:-$HOME/.venvs}
UV_BIN=${UV:-uv}

fail() {
    printf 'kdense: %s\n' "$*" >&2
    exit 1
}

command -v "$UV_BIN" >/dev/null 2>&1 || fail "uv is not available: $UV_BIN"

ensure() {
    local name=$1 python=$2 requirements=$3 verify=$4 venv
    venv="$VENV_ROOT/$name"
    [ -f "$requirements" ] || fail "missing requirements file: $requirements"
    if [ ! -x "$venv/bin/python" ]; then
        printf 'kdense: creating %s with Python %s\n' "$venv" "$python"
        "$UV_BIN" venv --python "$python" "$venv" || fail "cannot create $venv"
    fi
    printf 'kdense: reconciling %s from %s\n' "$venv" "$(basename "$requirements")"
    "$UV_BIN" pip install --quiet --python "$venv/bin/python" -r "$requirements" ||
        fail "install failed for $name"
    "$venv/bin/python" -c "$verify" || fail "import check failed for $name"
    printf 'kdense: %s ok\n' "$name"
}

ensure kdense-research 3.13 "$SCRIPT_DIR/requirements-core.txt" \
    'import scanpy, anndata, scvi, pysam, gtars, shap, lightning, cellxgene_census, gget, alphagenome, pyzotero'
ensure kdense-scvelo 3.13 "$SCRIPT_DIR/requirements-velocity.txt" \
    'import scvelo, scanpy, anndata'
ensure kdense-arboreto 3.11 "$SCRIPT_DIR/requirements-grn.txt" \
    "import dask; dask.config.set({'dataframe.query-planning': False}); from arboreto.algo import grnboost2, genie3"

printf 'kdense: environments ready under %s\n' "$VENV_ROOT"
