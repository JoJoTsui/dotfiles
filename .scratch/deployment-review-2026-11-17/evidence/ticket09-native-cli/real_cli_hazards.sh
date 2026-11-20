#!/bin/bash
# The pinned Magpie CLI's write behaviour in isolated synthetic homes.
#
# Every case runs in its own synthetic home, with fabricated configuration and
# a fake gateway address. Nothing touches the device home or the live
# gateway. Every claim is asserted: a case that does not hold is a failure
# and the script exits non-zero, so the negative cases stay negative and a
# passing run is evidence.
set -u

SCRATCH=${SCRATCH:?"the scratch directory is required"}
PAYLOAD=${PAYLOAD:?"the payload path is required"}
DIGEST=${DIGEST:-2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132}
PORT=${PORT:-3518}
GATEWAY_LOG="$SCRATCH/gateway-requests-2.log"
BASE="$SCRATCH/cases"
FAILURES=0

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    FAILURES=$((FAILURES + 1))
}

digest_of() { shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'; }

# The digest is checked before any byte of the payload is executed.
actual=$(digest_of "$PAYLOAD")
if [ "$actual" != "$DIGEST" ]; then
    printf 'FAIL: the payload digest is %s, not the approved %s; nothing was executed\n' \
        "$actual" "$DIGEST" >&2
    exit 1
fi
printf 'the payload digest matches the approved one before execution: sha256 %s\n' "$actual"

rm -rf "$BASE"
mkdir -p "$BASE"
rm -f "$GATEWAY_LOG"
FAKE_GATEWAY_LOG="$GATEWAY_LOG" python3 "$SCRATCH/fake_gateway.py" "$PORT" >/dev/null 2>&1 &
GATEWAY_PID=$!
trap 'kill "$GATEWAY_PID" 2>/dev/null' EXIT
sleep 1

run() {
    local home=$1
    shift
    env -i HOME="$home" PATH=/usr/bin:/bin TMPDIR="$SCRATCH" MAGPIE_ADDR="127.0.0.1:$PORT" \
        "$PAYLOAD" "$@"
    return $?
}

# A home with the fabricated provider and group the profile write needs.
prepare() {
    local home=$1
    mkdir -p "$home/.codex"
    printf 'model = "chatgpt-native"\n' > "$home/.codex/config.toml"
    run "$home" provider add openai sk-synthetic-not-a-real-key >/dev/null 2>&1
    run "$home" group add openai-stack models=openai/gpt-6.1-sol >/dev/null 2>&1
    run "$home" codex scope profile >/dev/null 2>&1
}

echo "== a private placeholder keeps its mode =="
home="$BASE/private"
prepare "$home"
(umask 077; : > "$home/.codex/magpie.config.toml")
run "$home" codex group/openai-stack >/dev/null
printf 'profile mode=%s\n' "$(stat -f '%Lp' "$home/.codex/magpie.config.toml")"
printf 'catalog mode=%s\n' "$(stat -f '%Lp' "$home/.codex/magpie-models.json")"
[ "$(stat -f '%Lp' "$home/.codex/magpie.config.toml")" = 600 ] ||
    fail "the private placeholder did not keep its 0600 mode"
[ "$(stat -f '%Lp' "$home/.codex/magpie-models.json")" = 644 ] ||
    fail "the catalog was not written 0644"

echo "== a file with another name is written in place =="
home="$BASE/hardlink"
prepare "$home"
printf 'model = "device-model"\n' > "$home/alias.toml"
ln "$home/alias.toml" "$home/.codex/magpie.config.toml"
printf 'alias before: %s\n' "$(head -1 "$home/alias.toml")"
run "$home" codex group/openai-stack >/dev/null
printf 'alias after:  %s\n' "$(head -1 "$home/alias.toml")"
printf 'links=%s\n' "$(stat -f '%l' "$home/alias.toml")"
[ "$(head -1 "$home/alias.toml")" = 'model = "group/openai-stack"' ] ||
    fail "the alias was not written through"
[ "$(stat -f '%l' "$home/alias.toml")" = 2 ] || fail "the alias does not have two names"

echo "== a linked Codex home is written through =="
home="$BASE/linkedhome"
prepare "$home"
mkdir -p "$home/device-codex"
rm -rf "$home/.codex"
ln -s "$home/device-codex" "$home/.codex"
run "$home" codex group/openai-stack >/dev/null
printf 'the linked directory holds: %s\n' "$(ls "$home/device-codex" | tr '\n' ' ')"
[ -f "$home/device-codex/magpie.config.toml" ] || fail "the linked home was not written through"
[ -f "$home/device-codex/magpie-models.json" ] || fail "the linked catalog was not written through"

echo "== the ordinary integration refuses the scope change =="
home="$BASE/connected"
mkdir -p "$home/.codex"
printf 'model = "magpie/openai/gpt-6.1-sol"\nmodel_provider = "magpie"\n' > "$home/.codex/config.toml"
before=$(digest_of "$home/.codex/config.toml")
out=$(run "$home" codex scope); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the scope getter failed"
[ "$out" = "Codex applies to default" ] || fail "the connected scope getter answered '$out'"
out=$(run "$home" codex scope profile 2>&1); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 1 ] || fail "the refused scope change exited $status, not 1"
case "$out" in *"disconnect Codex from magpie first"*) ;; *) fail "the refusal message is missing" ;; esac
[ "$(digest_of "$home/.codex/config.toml")" = "$before" ] ||
    fail "the refused scope change changed the base configuration"

echo "== a profile the writer cannot parse is preserved =="
home="$BASE/malformed"
prepare "$home"
printf 'device-owned-bytes\n' > "$home/.codex/magpie.config.toml"
out=$(run "$home" codex group/openai-stack 2>&1); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
printf 'profile after: %s\n' "$(cat "$home/.codex/magpie.config.toml")"
[ "$status" -eq 1 ] || fail "the malformed profile write exited $status, not 1"
[ "$(cat "$home/.codex/magpie.config.toml")" = "device-owned-bytes" ] ||
    fail "the malformed profile was not preserved"
case "$out" in *"expected character"*) ;; *) fail "the parse error is missing" ;; esac

echo "== the rollback: disconnect the profile, then the scope itself is reset =="
home="$BASE/rollback"
prepare "$home"
run "$home" codex group/openai-stack >/dev/null
out=$(run "$home" codex default 2>&1); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the disconnect failed"
case "$out" in *"disconnected from magpie"*) ;; *) fail "the disconnect message is missing" ;; esac
# The disconnect removes the profile and its list; the scope is Magpie's own
# preference and stays until it is reset.
out=$(run "$home" codex scope); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$out" = "Codex applies to profile" ] || fail "the scope after the disconnect answered '$out'"
[ ! -f "$home/.codex/magpie.config.toml" ] || fail "the disconnect left the profile behind"
out=$(run "$home" codex scope default 2>&1); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the scope reset failed"
out=$(run "$home" codex scope); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$out" = "Codex applies to default" ] || fail "the scope after the reset answered '$out'"

echo "== the requests the fake gateway received =="
cat "$GATEWAY_LOG" 2>/dev/null || echo "(none)"

if [ "$FAILURES" -ne 0 ]; then
    printf 'FAILED: %s assertion(s) did not hold\n' "$FAILURES" >&2
    exit 1
fi
printf 'OK: every assertion held\n'
