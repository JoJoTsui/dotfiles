#!/bin/bash
# The pinned Magpie CLI, exercised in an isolated synthetic home.
#
# Nothing here touches the device home, a real credential, or the live
# gateway: the home is synthetic, the configuration is fabricated, and the
# CLI is pointed at a fake gateway on a private port with MAGPIE_ADDR, the
# address the CLI's own help names. The fake gateway logs every request it
# receives, so the evidence shows which address the CLI used.
#
# Every claim is asserted: the script fails (non-zero exit) when an expected
# outcome does not hold, so a passing run is evidence and a printed line is
# not. The payload digest is checked before the payload is executed.
set -u

SCRATCH=${SCRATCH:?"the scratch directory is required"}
PAYLOAD=${PAYLOAD:?"the payload path is required"}
DIGEST=${DIGEST:-2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132}
PORT=${PORT:-3499}
GATEWAY_LOG="$SCRATCH/gateway-requests.log"
ISO="$SCRATCH/real-cli-home"
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

rm -rf "$ISO"
mkdir -p "$ISO/.codex"
printf 'model = "chatgpt-native"\nmodel_provider = "origin"\n' > "$ISO/.codex/config.toml"
printf '{"tokens":{"access_token":"synthetic-not-a-real-credential"}}\n' > "$ISO/.codex/auth.json"
chmod 600 "$ISO/.codex/auth.json"

rm -f "$GATEWAY_LOG"
FAKE_GATEWAY_LOG="$GATEWAY_LOG" python3 "$SCRATCH/fake_gateway.py" "$PORT" >/dev/null 2>&1 &
GATEWAY_PID=$!
trap 'kill "$GATEWAY_PID" 2>/dev/null' EXIT
sleep 1

# run prints the output and returns the exit status of the CLI.
run() {
    env -i HOME="$ISO" PATH=/usr/bin:/bin TMPDIR="$SCRATCH" MAGPIE_ADDR="127.0.0.1:$PORT" \
        "$PAYLOAD" "$@"
    return $?
}

echo "== version =="
out=$(run --version); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the version command failed"
case "$out" in magpie\ *) ;; *) fail "the version output is not a magpie version" ;; esac

echo "== status (the address the CLI uses) =="
out=$(run status --json); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the status command failed"
case "$out" in *127.0.0.1:$PORT*) ;; *) fail "the status does not name the fake address" ;; esac
case "$out" in *3425*) fail "the status names the live gateway port" ;; esac

echo "== scope getter, before =="
out=$(run codex scope); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the scope getter failed before the selection"
[ "$out" = "Codex applies to default" ] || fail "the scope getter answered '$out'"

echo "== scope setter =="
out=$(run codex scope profile); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the scope setter failed"
case "$out" in *"applies to profile"*) ;; *) fail "the scope setter did not report the profile scope" ;; esac

echo "== scope getter, after =="
out=$(run codex scope); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the scope getter failed after the selection"
[ "$out" = "Codex applies to profile" ] || fail "the scope getter answered '$out'"

echo "== fabricated provider and group =="
run provider add openai sk-synthetic-not-a-real-key >/dev/null || fail "the provider was not added"
run group add openai-stack models=openai/gpt-6.1-sol >/dev/null || fail "the group was not added"

echo "== base configuration and authentication before the profile write =="
config_before=$(digest_of "$ISO/.codex/config.toml")
auth_before=$(digest_of "$ISO/.codex/auth.json")
printf 'config.toml %s\n' "$config_before"
printf 'auth.json %s\n' "$auth_before"

echo "== profile write =="
out=$(run codex group/openai-stack); status=$?
printf '%s\n[exit %d]\n' "$out" "$status"
[ "$status" -eq 0 ] || fail "the profile write failed"

echo "== the base configuration and authentication after the profile write =="
config_after=$(digest_of "$ISO/.codex/config.toml")
auth_after=$(digest_of "$ISO/.codex/auth.json")
printf 'config.toml %s\n' "$config_after"
printf 'auth.json %s\n' "$auth_after"
[ "$config_before" = "$config_after" ] || fail "the base configuration changed"
[ "$auth_before" = "$auth_after" ] || fail "the base authentication changed"

echo "== generated files =="
count=0
find "$ISO/.codex" -maxdepth 1 -type f | sort | while read -r file; do
    count=$((count + 1))
    printf '%s mode=%s bytes=%s sha256=%s\n' \
        "$(basename "$file")" \
        "$(stat -f '%Lp' "$file")" \
        "$(wc -c < "$file" | tr -d ' ')" \
        "$(digest_of "$file")"
done
for name in config.toml auth.json magpie-models.json magpie.config.toml; do
    [ -f "$ISO/.codex/$name" ] || fail "the generated file $name is missing"
done
[ -f "$ISO/.codex/magpie.config.toml" ] || fail "the profile was not written"
[ -f "$ISO/.codex/magpie-models.json" ] || fail "the catalog was not written"

echo "== the profile's keys (no values) =="
awk -F= '/^[a-z_]+ =/ {print $1}' "$ISO/.codex/magpie.config.toml" | sort -u | tr '\n' ' '
printf '\n'
for key in base_url experimental_bearer_token http_headers model model_catalog_json model_provider name wire_api; do
    grep -q "^$key = " "$ISO/.codex/magpie.config.toml" || fail "the profile has no $key"
done

echo "== the gateway address the profile names =="
address=$(grep -o 'http://[0-9.]*:[0-9]*[^"]*' "$ISO/.codex/magpie.config.toml" | head -1)
printf '%s\n' "$address"
case "$address" in *127.0.0.1:$PORT*) ;; *) fail "the profile does not name the fake address" ;; esac

echo "== the live gateway port in any output or generated file =="
if grep -rl '3425' "$ISO/.codex" 2>/dev/null | head -1 | grep -q .; then
    fail "the live port appears in the generated files"
    echo "the live port appears in the generated files"
else
    echo "the live port appears nowhere in the generated files"
fi

echo "== the requests the fake gateway received =="
cat "$GATEWAY_LOG" 2>/dev/null || echo "(none)"
requests=$(grep -c '^\(GET\|POST\) ' "$GATEWAY_LOG" 2>/dev/null || echo 0)
printf 'requests=%s\n' "$requests"
[ "$requests" -eq 1 ] || fail "the fake gateway received $requests requests, not 1"

if [ "$FAILURES" -ne 0 ]; then
    printf 'FAILED: %s assertion(s) did not hold\n' "$FAILURES" >&2
    exit 1
fi
printf 'OK: every assertion held\n'
