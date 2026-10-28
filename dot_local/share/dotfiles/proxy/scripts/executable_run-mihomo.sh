#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT=${INSTALL_ROOT:-"${HOME}/.local/share/mihomo"}
PROFILE_PATH=${PROFILE_PATH:-"$INSTALL_ROOT/profiles/config.yaml"}

[[ -r "$PROFILE_PATH" ]] || { echo "No profile at $PROFILE_PATH; run scripts/refresh-profile.sh first." >&2; exit 1; }

exec "$INSTALL_ROOT/bin/mihomo" -d "$INSTALL_ROOT" -f "$PROFILE_PATH"
