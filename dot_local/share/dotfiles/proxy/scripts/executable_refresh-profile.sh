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

subscription_url=''
# A valid legacy file can end at EOF immediately after its URL.
read -r subscription_url < "$SUBSCRIPTION_URL_FILE" || :
[[ -n $subscription_url ]] || { echo "Subscription URL is empty." >&2; exit 1; }

umask 077

# The replacement profile is staged beside the profile it replaces, so the
# publication is a rename on one filesystem. The active profile is not touched
# until the staged copy has been fetched, validated, and converted: a failed
# fetch, conversion, or validation leaves the last working profile in place,
# and a later refresh publishes a valid replacement without provisioning again.
PROFILE_DIR=$(dirname "$PROFILE_PATH")
mkdir -p "$PROFILE_DIR"
staged=$(mktemp "$PROFILE_DIR/.${PROFILE_PATH##*/}.staged.XXXXXX")
trap 'rm -f "$staged"' EXIT

curl --fail --location --silent --show-error \
  --user-agent clash.meta \
  --output "$staged" \
  "$subscription_url"

# A Clash-compatible profile needs these sections; anything else is not a
# usable Mihomo configuration.
missing_profile_key() {
  local key
  for key in mixed-port proxies proxy-groups rules; do
    if ! grep -Eq "^${key}:" "$staged"; then
      printf '%s' "$key"
      return 0
    fi
  done
  return 1
}

missing_key=$(missing_profile_key || true)
if [[ -n $missing_key ]]; then
  echo "Subscription did not return a Clash-compatible profile (missing ${missing_key}:)." >&2
  exit 1
fi

# Narrow every proxy-group to the configured region so Mihomo never picks a
# non-US exit even if a rule falls through to a selector. Idempotent; safe to
# re-run; before every supervised start as well (run-mihomo-supervised.sh).
# The conversion runs on the staged copy: a profile the conversion rejects is
# never published over the working one.
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)
if [[ -x "$SCRIPT_DIR/restrict-proxy-groups.py" ]]; then
  python3 "$SCRIPT_DIR/restrict-proxy-groups.py" us "$staged"
fi

# Replace the provider's rules with the routing policy: local and China
# destinations go DIRECT, advertising domains are rejected, everything else
# goes to GLOBAL, which startup pins to a US leaf. Idempotent; safe to re-run.
if [[ -x "$SCRIPT_DIR/apply-us-routing-policy.py" ]]; then
  python3 "$SCRIPT_DIR/apply-us-routing-policy.py" "$staged"
fi

# The converted profile is published only when it still carries every section
# Mihomo needs.
missing_key=$(missing_profile_key || true)
if [[ -n $missing_key ]]; then
  echo "Converted profile is missing ${missing_key}:; the active profile is unchanged." >&2
  exit 1
fi

chmod 0600 "$staged"
mv -f "$staged" "$PROFILE_PATH"
echo "Refreshed $PROFILE_PATH"
