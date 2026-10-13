# Verified upstream bootstrap exceptions. Never execute an unverified download.
# shellcheck disable=SC2034 # Sourced adapter contract.
CHEZMOI_VERSION=2.73.0

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
        linux-x86_64|wsl-x86_64) target=x86_64-unknown-linux-musl; digest=7aa3ec39aecceff9062fa2ed4d42cbaa0bdc25ddea727d048e061cf188d434f6 ;;
        linux-aarch64|wsl-aarch64) target=aarch64-unknown-linux-musl; digest=9f8d2113fe9dc01788a65f5c2acec34fa56b1193461a5c3e9a775d6d2d621bcb ;;
        macos-x86_64) target=x86_64-apple-darwin; digest=9859588ba57f390b5c77d56b2654fab37bc00e10952da25e3efd6e3434557e5a ;;
        macos-aarch64) target=aarch64-apple-darwin; digest=f4e32ea91970d4e11739488817979a5f2c6ebbb9cedb0d6dea74b2b790b272dc ;;
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
        linux-x86_64|wsl-x86_64) target=linux_amd64; digest=b597729b687af4488a848240134cb633de8ca0f04e0d26d48f400ee2ac338ffa ;;
        linux-aarch64|wsl-aarch64) target=linux_arm64; digest=abcb840401d3c1f2356e0f53f5d52aa10d10f572654d9626db9ad0ca4dc03355 ;;
        macos-x86_64) target=darwin_amd64; digest=55e7b0823b40966a239cb418b37201c5f0961bab1b797c933550c97b1ab08221 ;;
        macos-aarch64) target=darwin_arm64; digest=246679a0b200e7e8be4a951be3b95d37c33ecb87eaab5af6f4949f7d0317bcc1 ;;
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
        linux-x86_64|wsl-x86_64) target=x86_64-unknown-linux-gnu; digest=dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71 ;;
        linux-aarch64|wsl-aarch64) target=aarch64-unknown-linux-gnu; digest=15f6e4ce9f583b929c996c91562bad6d4454f3281de858b02cdfdef615fac433 ;;
        macos-x86_64) target=x86_64-apple-darwin; digest=259e2b84274434085163fe8d556510571772cda2aa6d87ca6aa664f57bc644e3 ;;
        macos-aarch64) target=aarch64-apple-darwin; digest=ec1b9233e7f72990ecd8e62063fa7f6c3dfc2bec8e97f88bff165f9100ac696a ;;
        *) fail 'native Windows rustup provisioning requires the PowerShell adapter' ;;
    esac
    scratch=$(mktemp -d "$TMPDIR/rustup.XXXXXX")
    download_verified "https://static.rust-lang.org/rustup/archive/$RUSTUP_VERSION/$target/rustup-init" "$scratch/rustup-init" "$digest"
    chmod 755 "$scratch/rustup-init"
    "$scratch/rustup-init" -y --no-modify-path --default-toolchain none --profile minimal
    rm -rf "$scratch"
    [[ "$("$rustup" --version 2>/dev/null)" = "rustup $RUSTUP_VERSION "* ]] || fail 'installed rustup version does not match its pin'
}
