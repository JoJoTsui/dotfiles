#!/bin/bash
set -euo pipefail
umask 077

# Test-control Python lives outside the fresh deployment under test. Its exact
# version and bootstrap manager come from the existing deployment owners.
controller_root="$HOME/controller"
export DEPLOY_SOURCE=/source DEPLOY_PLATFORM=linux DEPLOY_ARCH=x86_64
export PIXI_HOME="$controller_root/.pixi" XDG_CACHE_HOME="$controller_root/.cache"
export TMPDIR="$controller_root/tmp"
mkdir -p "$TMPDIR"
fail() { printf '%s\n' "$*" >&2; exit 1; }
source "$DEPLOY_SOURCE/deployment/common.sh"
source "$DEPLOY_SOURCE/deployment/managers.sh"
install_pixi
python_spec=$(common_python_spec)
exec "$DEPLOY_PIXI" exec --spec "$python_spec" -- python \
    "$DEPLOY_SOURCE/tests/native_linux.py" \
    --home "$HOME/device with spaces" --artifacts "$HOME/artifacts" \
    --ubuntu-release "$DOTFILES_TEST_UBUNTU_RELEASE" \
    --execution "${DOTFILES_TEST_EXECUTION_MODE:?outer runner must identify execution mode}" \
    --install-timeout 3600 --suite-timeout 1800
