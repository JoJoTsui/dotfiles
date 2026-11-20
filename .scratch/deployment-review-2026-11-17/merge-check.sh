#!/usr/bin/env bash
# Supervisor-side check on the real device: the client-settings merge must not
# rewrite a device configuration it does not change.
#
# It copies the device's own ~/.codex/config.toml into a throwaway home, runs
# the public merge seam there, and compares the bytes and the modification
# time. Nothing on the device is written.
set -uo pipefail
repo=/Users/joey/SHELL/dotfiles
device=${DEVICE_CODEX_CONFIG:-$HOME/.codex/config.toml}
sim=$(mktemp -d /tmp/dotfiles-device-merge.XXXXXX)
trap 'rm -rf "$sim"' EXIT
mkdir -p "$sim/.codex" "$sim/.config/chezmoi" "$sim/.local/state" "$sim/.cache/tmp"
cp -p "$device" "$sim/.codex/config.toml"
printf '[data]\n    platform = "macos"\n    role = "workstation"\n    arch = "aarch64"\n    kimiApiKey = "REPLACE_ME"\n' \
    > "$sim/.config/chezmoi/chezmoi.toml"
before=$(shasum -a 256 "$sim/.codex/config.toml" | awk '{print $1}')
mtime_before=$(stat -f '%m' "$sim/.codex/config.toml")
cat > "$sim/merge.sh" <<EOF
export HOME=$sim
export DEPLOY_SOURCE=$repo
export DEPLOY_HOME=\$HOME
export DEPLOY_CHEZMOI=\$(command -v chezmoi)
export XDG_CONFIG_HOME=\$HOME/.config
export XDG_STATE_HOME=\$HOME/.local/state
export TMPDIR=\$HOME/.cache/tmp
fail() { printf 'dotfiles: %s\n' "\$*" >&2; exit 1; }
source "\$DEPLOY_SOURCE/deployment/payload.sh"
source "\$DEPLOY_SOURCE/deployment/client-settings.sh"
deploy_client_settings 0 0 codex
EOF
bash "$sim/merge.sh" > "$sim/merge.log" 2>&1 && echo 'merge: exit 0' || {
    echo 'merge: FAILED'
    tail -5 "$sim/merge.log"
}
after=$(shasum -a 256 "$sim/.codex/config.toml" | awk '{print $1}')
mtime_after=$(stat -f '%m' "$sim/.codex/config.toml")
printf 'sha256 before %s\nsha256 after  %s\nmtime before  %s\nmtime after   %s\n' \
    "$before" "$after" "$mtime_before" "$mtime_after"
if [ "$before" = "$after" ] && [ "$mtime_before" = "$mtime_after" ]; then
    echo 'result: the merge wrote nothing; the device bytes and the modification time survive'
else
    echo 'result: the merge REWROTE the device configuration'
fi
