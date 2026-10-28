#!/usr/bin/env bash
# run-mihomo-supervised.sh — keep mihomo alive forever, restart on crash,
# and re-apply the startup configuration (mode + region) after every start.
#
# Use this as your container entrypoint or under your session manager
# (zellij / tmux). It replaces both run-mihomo.sh (which only blocks) and the
# manual configure-mihomo.py invocation that used to follow.
#
# Behaviour:
#   - Forks run-mihomo.sh and waits for it to exit.
#   - After it starts, waits for the controller to answer /version, then runs
#     configure-mihomo.py once with a 30s deadline. Failure here is logged
#     but does not kill mihomo — the live process continues with whatever
#     state configure achieved.
#   - If run-mihomo.sh exits after running for >=5s, logs the exit and
#     restarts in 1s.
#   - If run-mihomo.sh exits within the first 5s, gives up (startup failure;
#     a tight restart loop would just hammer the same missing-config error).
#   - On SIGINT/SIGTERM, forwards TERM to the running mihomo and exits cleanly.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
cd "$SCRIPT_DIR/.."

CONTROLLER=${MIHOMO_CONTROLLER:-http://127.0.0.1:9090}

# How often to check that the selected node still answers. A node can die
# without Mihomo restarting; without this the proxy would fail every request
# until the next restart.
HEALTH_INTERVAL=${MIHOMO_HEALTH_INTERVAL:-300}

SHUTDOWN=
PID=
HEALTH_PID=

shutdown() {
    SHUTDOWN=1
    if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
        kill -TERM "$PID" 2>/dev/null || true
    fi
    if [[ -n "$HEALTH_PID" ]] && kill -0 "$HEALTH_PID" 2>/dev/null; then
        kill "$HEALTH_PID" 2>/dev/null || true
    fi
}
trap shutdown INT TERM

wait_for_controller() {
    for _ in $(seq 1 30); do
        if curl -fsS --max-time 1 "$CONTROLLER/version" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

while [[ -z "$SHUTDOWN" ]]; do
    START=$(date +%s)

    # Narrow the profile to the configured region before every supervised
    # start, in case refresh-profile.sh was not used (e.g. profile restored
    # from a backup, or hand-edited between restarts). Idempotent.
    if [[ -x ./scripts/restrict-proxy-groups.py ]]; then
        ./scripts/restrict-proxy-groups.py || true
    fi

    # Apply the routing policy (local and China destinations DIRECT,
    # everything else through GLOBAL). Idempotent.
    if [[ -x ./scripts/apply-us-routing-policy.py ]]; then
        ./scripts/apply-us-routing-policy.py || true
    fi

    ./scripts/run-mihomo.sh &
    PID=$!

    if wait_for_controller; then
        if [[ -z "$SHUTDOWN" ]]; then
            timeout 30 ./scripts/configure-mihomo.py \
                || echo "[supervisor] configure-mihomo.py failed or timed out; continuing" >&2
        fi
    else
        echo "[supervisor] controller did not become ready; skipping startup config" >&2
    fi

    # Keep the selected node healthy while Mihomo runs.
    (
        while [[ -z "$SHUTDOWN" ]]; do
            sleep "$HEALTH_INTERVAL"
            [[ -z "$SHUTDOWN" ]] || break
            timeout 60 ./scripts/configure-mihomo.py --check \
                || echo "[supervisor] no healthy node available" >&2
        done
    ) &
    HEALTH_PID=$!

    wait "$PID" || true
    EXIT=$?
    ELAPSED=$(($(date +%s) - START))
    PID=
    kill "$HEALTH_PID" 2>/dev/null || true
    HEALTH_PID=

    if [[ -z "$SHUTDOWN" ]]; then
        if (( ELAPSED < 5 )); then
            echo "[supervisor] mihomo exited code=$EXIT after ${ELAPSED}s; not restarting (startup failure)" >&2
            exit 1
        fi
        echo "[supervisor] mihomo exited code=$EXIT after ${ELAPSED}s; restarting in 1s" >&2
        sleep 1
    fi
done