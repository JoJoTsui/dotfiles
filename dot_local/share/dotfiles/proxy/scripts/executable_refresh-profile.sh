#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT=${INSTALL_ROOT:-"${HOME}/.local/share/mihomo"}
PROFILE_PATH=${PROFILE_PATH:-"$INSTALL_ROOT/profiles/config.yaml"}

# Resolve repo-local source of the subscription URL.
# refresh-profile.sh lives at scripts/refresh-profile.sh, so the repo root is its grandparent.
SCRIPT_PATH=$(readlink -f "$0")
REPO_ROOT=$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)
REPO_SUBSCRIPTION_URL_FILE="$REPO_ROOT/secrets/subscription-url"
RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT="$INSTALL_ROOT/subscription-url"

# Materialise the repo copy to the runtime path (mode 0600) if missing.
if [[ ! -r "$RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT" && -r "$REPO_SUBSCRIPTION_URL_FILE" ]]; then
    install -d -m 0750 "$INSTALL_ROOT"
    install -m 0600 "$REPO_SUBSCRIPTION_URL_FILE" "$RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT"
    echo "Installed $REPO_SUBSCRIPTION_URL_FILE -> $RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT (mode 0600)."
fi

# Enforce 0600 on the runtime file. Git only preserves the executable bit across
# checkouts and applies the user's umask on clone, so a fresh clone lands this file
# at 0644 regardless of the mode in the working tree.
if [[ -r "$RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT" ]]; then
    chmod 0600 "$RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT"
fi

SUBSCRIPTION_URL_FILE=${SUBSCRIPTION_URL_FILE:-"$RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT"}

if [[ ! -r "$SUBSCRIPTION_URL_FILE" ]]; then
  echo "Create $SUBSCRIPTION_URL_FILE with the subscription URL (mode 0600), then rerun." >&2
  exit 1
fi

read -r subscription_url < "$SUBSCRIPTION_URL_FILE"
[[ -n $subscription_url ]] || { echo "Subscription URL is empty." >&2; exit 1; }

umask 077
tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

curl --fail --location --silent --show-error \
  --user-agent clash.meta \
  --output "$tmpfile" \
  "$subscription_url"

for key in mixed-port proxies proxy-groups rules; do
  if ! grep -Eq "^${key}:" "$tmpfile"; then
    echo "Subscription did not return a Clash-compatible profile (missing ${key}:)." >&2
    exit 1
  fi
done

mv "$tmpfile" "$PROFILE_PATH"

# Narrow every proxy-group to the configured region so Mihomo never picks a
# non-US exit even if a rule falls through to a selector. Idempotent; safe to
# re-run; before every supervised start as well (run-mihomo-supervised.sh).
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)
if [[ -x "$SCRIPT_DIR/restrict-proxy-groups.py" ]]; then
  python3 "$SCRIPT_DIR/restrict-proxy-groups.py" us "$PROFILE_PATH"
fi

# Replace the provider's rules with the routing policy: local and China
# destinations go DIRECT, advertising domains are rejected, everything else
# goes to GLOBAL, which startup pins to a US leaf. Idempotent; safe to re-run.
if [[ -x "$SCRIPT_DIR/apply-us-routing-policy.py" ]]; then
  python3 "$SCRIPT_DIR/apply-us-routing-policy.py" "$PROFILE_PATH"
fi
chmod 0600 "$PROFILE_PATH"
echo "Refreshed $PROFILE_PATH"
