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

echo "==> bun global packages (coding-agent CLIs)"
BG="$HOME/.bun/install/global/package.json"
if command -v bun >/dev/null 2>&1 && [ -f "$BG" ]; then
    # word-splitting of $BG_PKGS is intended (one "name@range" per package)
    BG_PKGS="$(sed -n 's/^ *"\([^"]*\)": "\([^"]*\)".*$/\1@\2/p' "$BG" | tr '\n' ' ')"
    if [ -n "$BG_PKGS" ]; then
        bun add -g --trust $BG_PKGS || echo "    warn: bun global install failed (continuing)"
    fi
else
    echo "    skipped: bun or $BG not present yet"
fi

echo "==> rustup (matches RUSTUP_* in .env_core; TUNA mirrors, minimal profile)"
if command -v rustup >/dev/null 2>&1; then
    echo "    rustup already installed"
else
    export RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT:-https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup}"
    export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://mirrors.tuna.tsinghua.edu.cn/rustup}"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs |
        sh -s -- -y --profile minimal --no-modify-path ||
        echo "    warn: rustup install failed (continuing)"
fi

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
