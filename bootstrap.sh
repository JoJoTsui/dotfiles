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

echo "==> GitHub release binary (no conda package: gping)"
# Idempotent: skips when already on PATH. Version is pinned on purpose.
fetch_release() { # <command-name> <url>
    local name="$1" url="$2" tmp f
    if command -v "$name" >/dev/null 2>&1; then
        echo "    $name already installed"
        return 0
    fi
    tmp="$(mktemp -d)"
    if curl -fsSL "$url" -o "$tmp/blob"; then
        case "$url" in
        *.tar.gz | *.tgz) tar xzf "$tmp/blob" -C "$tmp" ;;
        esac
        f="$(find "$tmp" -type f -name "$name" | head -n1)"
        [ -n "$f" ] || f="$tmp/blob" # raw (non-archive) release asset
        cp "$f" "$BIN/$name" && chmod 755 "$BIN/$name"
        echo "    installed $name -> $BIN/$name"
    else
        echo "    warn: $name download failed (continuing)"
    fi
    rm -rf "$tmp"
}
if [ "$(uname -s)" = "Linux" ]; then
    case "$(uname -m)" in
    x86_64) gping_arch=x86_64 ;;
    aarch64 | arm64) gping_arch=arm64 ;;
    *)
        gping_arch=""
        echo "    skipped: unsupported arch $(uname -m)"
        ;;
    esac
    if [ -n "$gping_arch" ]; then
        fetch_release gping "https://github.com/orf/gping/releases/download/gping-v1.21.0/gping-Linux-musl-$gping_arch.tar.gz"
    fi
else
    echo "    skipped: only Linux release binaries are wired up"
fi

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

echo "==> rustup (matches RUSTUP_* in .env_core; TUNA mirrors, default profile)"
if command -v rustup >/dev/null 2>&1; then
    echo "    rustup already installed"
else
    export RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT:-https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup}"
    export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://mirrors.tuna.tsinghua.edu.cn/rustup}"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs |
        sh -s -- -y --profile default --no-modify-path ||
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
