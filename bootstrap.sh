#!/usr/bin/env bash
# Bootstrap this dotfiles repo on a NEW host. Idempotent; safe to re-run.
#
#   git clone https://github.com/JoJoTsui/dotfiles.git && cd dotfiles && bash bootstrap.sh
#
# Optional env: DOTFILES_CLASS, HTTP_PROXY_URL, GLM_BASE_URL, GLM_API_TOKEN,
# KIMI_API_KEY — see .chezmoi.toml.tmpl.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
export PATH="$BIN:$PATH"

echo "==> pixi (global tool management)"
command -v pixi >/dev/null 2>&1 || curl -fsSL https://pixi.sh/install.sh | bash

echo "==> chezmoi"
command -v chezmoi >/dev/null 2>&1 ||
    sh -c "$(curl -fsLS get.chezmoi.io)" -- -b "$BIN"

echo "==> apply dotfiles (copy mode)"
chezmoi init --apply "$SRC"

echo "==> global CLI tools from dot_pixi/manifests/pixi-global.toml"
pixi global sync

echo "==> nushell upstream completions (vendored)"
NU_SCRIPTS="$HOME/.config/nushell/nu_scripts"
[ -d "$NU_SCRIPTS/.git" ] ||
    git clone --depth 1 https://github.com/nushell/nu_scripts "$NU_SCRIPTS" ||
    git clone --depth 1 https://gh-proxy.com/github.com/nushell/nu_scripts.git "$NU_SCRIPTS"

echo "==> system-wide bash banner (optional, needs sudo)"
if [ -w /etc/bash.bashrc ]; then
    cp /etc/bash.bashrc /etc/bash.bashrc.bak
    cp "$SRC/system/bash.bashrc" /etc/bash.bashrc
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo sh -c 'cp /etc/bash.bashrc /etc/bash.bashrc.bak; cp "$1" /etc/bash.bashrc' _ "$SRC/system/bash.bashrc"
else
    echo "    skipped: /etc/bash.bashrc not writable and no passwordless sudo"
fi

echo "done — start a new login shell"
