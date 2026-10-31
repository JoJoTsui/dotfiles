#!/usr/bin/env bash
# Report a Codex session to Herdr with a proxied, daemon-free resume command.
#
# The managed herdr-agent-state.sh already reports the session id. This custom
# hook runs after it on SessionStart and overrides the resume argv so a Herdr
# restore runs codex-herdr (health gate + with-proxy + --no-daemon) instead of
# the bare codex command.
set -uo pipefail

dry_run=false
[ "${1:-}" = "--dry-run" ] && dry_run=true

[ "${HERDR_ENV:-}" = 1 ] || exit 0
[ -n "${HERDR_SOCKET_PATH:-}" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0
command -v herdr >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

input=$(mktemp "${TMPDIR:-/tmp}/herdr-codex-resume.XXXXXX") || exit 0
trap 'rm -f "$input"' EXIT HUP INT TERM
cat >"$input" 2>/dev/null || true

session_id=$(python3 - "$input" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception:
    raise SystemExit(0)
if payload.get("hook_event_name") not in (None, "SessionStart"):
    raise SystemExit(0)
value = payload.get("session_id")
if isinstance(value, str) and value:
    print(value)
PY
) || exit 0
[ -n "$session_id" ] || exit 0

report_agent=(
    herdr pane report-agent "$HERDR_PANE_ID"
    --source herdr:codex --agent codex --state idle
    --agent-session-id "$session_id"
    -- codex-herdr resume "$session_id"
)
report_session=(
    herdr pane report-agent-session "$HERDR_PANE_ID"
    --source herdr:codex --agent codex
    --agent-session-id "$session_id"
    -- codex-herdr resume "$session_id"
)

if [ "$dry_run" = true ]; then
    printf '%s\n' "${report_agent[*]}"
    printf '%s\n' "${report_session[*]}"
    exit 0
fi

"${report_agent[@]}" >/dev/null 2>&1 || true
"${report_session[@]}" >/dev/null 2>&1 || true
