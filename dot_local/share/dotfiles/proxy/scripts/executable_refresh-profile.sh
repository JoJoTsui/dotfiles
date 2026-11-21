#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT=${INSTALL_ROOT:-"${HOME}/.local/share/mihomo"}
PROFILE_PATH=${PROFILE_PATH:-"$INSTALL_ROOT/profiles/config.yaml"}
# The Mihomo binary that decides whether a configuration is usable. The
# deployment passes the managed release from both call sites: the service
# refresh and the temporary deployment instance keep separate install roots,
# but they validate with the same managed binary.
MIHOMO_VALIDATOR=${MIHOMO_VALIDATOR:-"$INSTALL_ROOT/bin/mihomo"}

# Resolve this script's own path and the directory its transforms live in.
# The repository copy carries the `executable_` prefix in the file name and
# the deployed copy does not, so a transform is looked up under both names.
SCRIPT_PATH=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_SUBSCRIPTION_URL_FILE="$REPO_ROOT/secrets/subscription-url"
RUNTIME_SUBSCRIPTION_URL_FILE_DEFAULT="$INSTALL_ROOT/subscription-url"

# The profile is published by renaming a staged copy over it. A destination
# that is not a regular file cannot be replaced that way: a directory would
# take the staged file instead of being replaced, and the refresh would
# report success while the working profile kept serving. The destination is
# checked before the refresh fetches or writes anything.
if [ -e "$PROFILE_PATH" ] || [ -L "$PROFILE_PATH" ]; then
    if [ ! -f "$PROFILE_PATH" ]; then
        echo "Refusing to publish over $PROFILE_PATH: the destination is not a regular file." >&2
        exit 1
    fi
fi

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

# The fetch output is captured so a message that quotes the subscription URL
# is not relayed: the URL is a secret.
if ! fetch_output=$(curl --fail --location --silent --show-error \
  --user-agent clash.meta \
  --output "$staged" \
  "$subscription_url" 2>&1); then
    if [ -n "$fetch_output" ]; then
        printf '%s\n' "${fetch_output//"$subscription_url"/[redacted]}" >&2
    fi
    echo "The subscription fetch failed; the active profile is unchanged." >&2
    exit 1
fi

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

# The transforms are required. A profile published without them carries the
# provider's own regions and rules, which is not the profile this deployment
# manages, so a transform that is missing or is not executable stops the
# refresh instead of publishing an unconverted profile.
require_transform() {
  local name=$1 candidate
  for candidate in "$SCRIPT_DIR/$name" "$SCRIPT_DIR/executable_$name"; do
    if [ -e "$candidate" ] || [ -L "$candidate" ]; then
      if [ ! -f "$candidate" ] || [ ! -x "$candidate" ]; then
        echo "The proxy transform $candidate is not an executable file; the active profile is unchanged." >&2
        exit 1
      fi
      printf '%s' "$candidate"
      return 0
    fi
  done
  echo "The proxy transform $name is missing from $SCRIPT_DIR; the active profile is unchanged." >&2
  exit 1
}

# Narrow every proxy-group to the configured region so Mihomo never picks a
# non-US exit even if a rule falls through to a selector. Idempotent; safe to
# re-run; before every supervised start as well (run-mihomo-supervised.sh).
# The conversion runs on the staged copy: a profile the conversion rejects is
# never published over the working one.
restrict_transform=$(require_transform restrict-proxy-groups.py) || exit 1

# Replace the provider's rules with the routing policy: local and China
# destinations go DIRECT, advertising domains are rejected, everything else
# goes to GLOBAL, which startup pins to a US leaf. Idempotent; safe to re-run.
policy_transform=$(require_transform apply-us-routing-policy.py) || exit 1

"$restrict_transform" us "$staged"
"$policy_transform" "$staged"

# The converted profile is published only when it still carries every section
# Mihomo needs.
missing_key=$(missing_profile_key || true)
if [[ -n $missing_key ]]; then
  echo "Converted profile is missing ${missing_key}:; the active profile is unchanged." >&2
  exit 1
fi

# The staged profile is validated with the managed Mihomo binary before it is
# published, so a configuration Mihomo cannot load never replaces the working
# one. The validator's own message is not relayed: a parse error quotes the
# value it rejected, and a profile carries proxy credentials.
if [ ! -x "$MIHOMO_VALIDATOR" ]; then
  echo "The Mihomo config validator $MIHOMO_VALIDATOR is missing; the active profile is unchanged." >&2
  exit 1
fi
if ! "$MIHOMO_VALIDATOR" -d "$INSTALL_ROOT" -t -f "$staged" >/dev/null 2>&1; then
  echo "The staged profile is not a usable Mihomo configuration; the active profile is unchanged." >&2
  exit 1
fi

chmod 0600 "$staged"
mv -f "$staged" "$PROFILE_PATH"
echo "Refreshed $PROFILE_PATH"
