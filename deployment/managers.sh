# Verified upstream bootstrap exceptions. Never execute an unverified download.
# shellcheck disable=SC2034 # Sourced adapter contract.
CHEZMOI_VERSION=2.73.3

verify_sha256() {
    local file=$1 expected=$2 actual
    if command -v sha256sum >/dev/null 2>&1; then
        actual=$(sha256sum "$file"); actual=${actual%% *}
    elif command -v shasum >/dev/null 2>&1; then
        actual=$(shasum -a 256 "$file"); actual=${actual%% *}
    else
        fail 'a SHA-256 utility (sha256sum or shasum) is required'
    fi
    [ "$actual" = "$expected" ] || fail "SHA-256 mismatch for ${file##*/}"
}

download_verified() {
    curl -fsSL --connect-timeout 15 --max-time 180 --retry 2 "$1" -o "$2"
    verify_sha256 "$2" "$3"
}

install_pixi() {
    if [ -n "${DOTFILES_PIXI_BIN:-}" ]; then
        [ -x "$DOTFILES_PIXI_BIN" ] || fail 'DOTFILES_PIXI_BIN is not executable'
        DEPLOY_PIXI=$DOTFILES_PIXI_BIN
        [ "$("$DEPLOY_PIXI" --version)" = "pixi $PIXI_VERSION" ] || fail "DOTFILES_PIXI_BIN must provide pixi $PIXI_VERSION"
        return
    fi
    DEPLOY_PIXI="$PIXI_HOME/bin/pixi"
    if [ -x "$DEPLOY_PIXI" ] && [ "$("$DEPLOY_PIXI" --version)" = "pixi $PIXI_VERSION" ]; then return; fi
    local target digest scratch
    case "$DEPLOY_PLATFORM-$DEPLOY_ARCH" in
        linux-x86_64|wsl-x86_64) target=x86_64-unknown-linux-musl; digest=064f371e692aaa3400ac581c89da2843c91437f20c2d9155395a5d0037f33551 ;;
        linux-aarch64|wsl-aarch64) target=aarch64-unknown-linux-musl; digest=d08403d8f048626ec93ba7b7c56e3b747a5f3a95c4e6e0c815ceb264f5f0b9ce ;;
        macos-x86_64) target=x86_64-apple-darwin; digest=145e26ba860b5a08a2904ca4354cdfdcec1332a8f1d09ea08f1ec663c08e3ac8 ;;
        macos-aarch64) target=aarch64-apple-darwin; digest=b46066fbaf931284a3f4a61d68e0eb352295f4b3ce4330315a3de3dc5da5736c ;;
        *) fail 'native Windows Pixi provisioning requires the PowerShell adapter' ;;
    esac
    scratch=$(mktemp -d "$TMPDIR/pixi.XXXXXX")
    download_verified "https://github.com/prefix-dev/pixi/releases/download/v$PIXI_VERSION/pixi-$target.tar.gz" "$scratch/pixi.tar.gz" "$digest"
    tar -xzf "$scratch/pixi.tar.gz" -C "$scratch" pixi
    mkdir -p "$PIXI_HOME/bin"
    cp "$scratch/pixi" "$DEPLOY_PIXI"
    chmod 755 "$DEPLOY_PIXI"
    rm -rf "$scratch"
    [ "$("$DEPLOY_PIXI" --version)" = "pixi $PIXI_VERSION" ] || fail 'downloaded Pixi version does not match its pin'
}

install_chezmoi() {
    if [ -n "${DOTFILES_CHEZMOI_BIN:-}" ]; then
        [ -x "$DOTFILES_CHEZMOI_BIN" ] || fail 'DOTFILES_CHEZMOI_BIN is not executable'
        DEPLOY_CHEZMOI=$DOTFILES_CHEZMOI_BIN
        return
    fi
    DEPLOY_CHEZMOI="$HOME/.local/bin/chezmoi"
    if [ -x "$DEPLOY_CHEZMOI" ] && [[ "$("$DEPLOY_CHEZMOI" --version)" = *"v$CHEZMOI_VERSION,"* ]]; then return; fi
    local target digest scratch
    case "$DEPLOY_PLATFORM-$DEPLOY_ARCH" in
        linux-x86_64|wsl-x86_64) target=linux_amd64; digest=6e5827598cbfc02d132b04f95b5ea10efb5b79230e2a4a0e52df4af144a8ee9f ;;
        linux-aarch64|wsl-aarch64) target=linux_arm64; digest=c9e6a6e71eb5291018e161a8426d7c313cd2e8553c2ca4029511fec2a33bc28c ;;
        macos-x86_64) target=darwin_amd64; digest=d865487d6669243c948ee5542087bd95f4ad4ecb5a1311b85cf19f557694fe03 ;;
        macos-aarch64) target=darwin_arm64; digest=ec2d0005f369c912ee9891a26c30d65dc0eda51708f06948e5f7a43db69e1aa7 ;;
        *) fail 'native Windows provisioning requires the PowerShell adapter' ;;
    esac
    scratch=$(mktemp -d "$TMPDIR/chezmoi.XXXXXX")
    download_verified "https://github.com/twpayne/chezmoi/releases/download/v$CHEZMOI_VERSION/chezmoi_${CHEZMOI_VERSION}_$target.tar.gz" "$scratch/chezmoi.tar.gz" "$digest"
    tar -xzf "$scratch/chezmoi.tar.gz" -C "$scratch" chezmoi
    cp "$scratch/chezmoi" "$DEPLOY_CHEZMOI"
    chmod 755 "$DEPLOY_CHEZMOI"
    rm -rf "$scratch"
}

install_rustup() {
    local rustup="$CARGO_HOME/bin/rustup" target digest scratch
    if [ -x "$rustup" ] && [[ "$("$rustup" --version 2>/dev/null)" = "rustup $RUSTUP_VERSION "* ]]; then return; fi
    case "$DEPLOY_PLATFORM-$DEPLOY_ARCH" in
        linux-x86_64|wsl-x86_64) target=x86_64-unknown-linux-gnu; digest=5be191e8c70a5007074254cb74d78dbfdd25cd5a61c27de7b8e5410122ec24f4 ;;
        linux-aarch64|wsl-aarch64) target=aarch64-unknown-linux-gnu; digest=a9c168dbea81a84671c6b7a5c1795cb0eb699020110d107ddfca427bd797e697 ;;
        macos-x86_64) target=x86_64-apple-darwin; digest=b9610730ddeef52765723847866fd1e3540b2bf7d5ab0c324aa143a5edf25ba0 ;;
        macos-aarch64) target=aarch64-apple-darwin; digest=f7c7e11eb2e07f006e532a8aaac77b32f4527d305ac386c0c633ca6133d35ca9 ;;
        *) fail 'native Windows rustup provisioning requires the PowerShell adapter' ;;
    esac
    scratch=$(mktemp -d "$TMPDIR/rustup.XXXXXX")
    download_verified "https://static.rust-lang.org/rustup/archive/$RUSTUP_VERSION/$target/rustup-init" "$scratch/rustup-init" "$digest"
    chmod 755 "$scratch/rustup-init"
    "$scratch/rustup-init" -y --no-modify-path --default-toolchain none --profile minimal
    rm -rf "$scratch"
    [[ "$("$rustup" --version 2>/dev/null)" = "rustup $RUSTUP_VERSION "* ]] || fail 'installed rustup version does not match its pin'
}
