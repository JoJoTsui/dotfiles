# Windows implementation evidence

Ticket 11 implements the native PowerShell boundary and windows-2025 role jobs.
No native Windows executable or runner was available in this Linux session.

| Layer | Evidence | Status |
| --- | --- | --- |
| PowerShell 7.6.6 on Linux | Public plan, source-copy application/reapplication, native-file layout, literal JSON/TOML credentials, client/payload/auth/history preservation, invalid selections, nested copy/installer symlinks and private parser failure | Six tests passed; foreign rendering only |
| Actual Nu 0.116.1 on Linux | Ordinary startup of the Windows-rendered shared configuration, without individual config flags or inherited EDITOR/Python preference | One regression passed; `-c` failed before correction to `-e` print/exit |
| Actual Atuin 18.23 on Linux | `nu-file`/`nu-db-file` migration, original-file preservation, secret pruning, LF/UTF-8/multiline behavior, SQLite timestamp/cwd/exit/raw duration/signed-session metadata and activation still pending | Two tests passed; shared adapter behavior |
| Unix adapter regressions | Public deployment (13), actual Nu/Bash/Zsh paths/overrides/hooks/logs (10), actual Atuin import/recording/encrypted loopback sync (7) | Passed after fixing a rendered function separator |
| Integrated regression suite | Managed Python 3.13, isolated Chezmoi/PowerShell/common tools, all applicable deployment/shell/history tests after merging native macOS and WSL | 87 tests in 294.755s; 72 executed, 15 explicitly skipped |
| Native package solves | Ticket 02 resolves common win-64 requirements; ticket 08 resolves the desktop target independently | Recorded in their evidence; not binary execution |
| Native PowerShell 5.1 | Public boundary and apply-only without Git Bash | CI gate committed; execution pending |
| Native Windows tool/agent execution | Full pinned install/reapply, actual version diagnostics, Kimi shell doctor, Nu/Git Bash root/PATH behavior, uv/pip discovery | CI gate committed; execution pending |
| Native client discovery/MCP | All five client discovery interfaces, native Node stdio command, Claude/Kimi/OpenCode connections, Codex registration, explicit temporary CodeGraph fixture | CI gate committed; execution pending |
| Native console/history | Attached-console Unicode password and key input, wrong-key retry, normal/failed child mode restoration, two-device PASETOv4 loopback sync, Nu/Git Bash interactive recording/navigation/logs, non-console rejection, native explicit-file migration | CI gate committed; execution pending |
| Unredirected Known Folder fallback | Ordinary native-home discovery with XDG absent | Not exercised; isolated tests preserve pre-startup roots |
| Console cancellation/TOTP browser flow | Public wrapper terminates/waits in cancellation and masks all console input; fixture targets normal and failed child restoration | Cancellation/native browser/TOTP end-to-end gate remains pending; no hosted account requests |

The Linux PowerShell tool is the official checksum-verified 7.6.6 archive; it
establishes parsing/rendering, not PowerShell 5.1 compatibility, Windows ACLs,
reparse semantics, archive execution, native shim spawning or console behavior.
The public boundary accepts foreign `ApplyOnly` only with an explicit home;
foreign native installation fails before state creation. All local homes,
caches, commands and credentials were disposable/synthetic.

Windows upstream hashes come from primary release assets, including
[Pixi0.81](https://github.com/prefix-dev/pixi/releases/expanded_assets/v0.81.0),
[Chezmoi2.73](https://github.com/twpayne/chezmoi/releases/expanded_assets/v2.73.0),
[Bun1.3.11](https://github.com/oven-sh/bun/releases/download/bun-v1.3.11/SHASUMS256.txt),
[Atuin18.23](https://github.com/atuinsh/atuin/releases/expanded_assets/v18.23.0),
[PortableGit2.56](https://github.com/git-for-windows/git/releases/expanded_assets/v2.56.0.windows.2),
[Helix25.07.1](https://github.com/helix-editor/helix/releases/expanded_assets/25.07.1),
[jq1.8.2](https://github.com/jqlang/jq/releases/download/jq-1.8.2/sha256sum.txt),
and [Rustup1.29.1](https://static.rust-lang.org/rustup/archive/1.29.1/x86_64-pc-windows-msvc/rustup-init.exe.sha256).
PortableGit extraction follows its [official silent extraction contract](https://gitforwindows.org/zip-archives-extracting-the-released-archives.html).

Commands:

```bash
DOTFILES_TEST_POWERSHELL=/tmp/dotfiles-implementation/tools/powershell/pwsh \
DOTFILES_TEST_CHEZMOI=/tmp/dotfiles-implementation/tools/chezmoi \
DOTFILES_TEST_TOOL_HOME=/tmp/dotfiles-implementation/common-linux/home \
python3 -m unittest discover -s tests -p test_windows_deployment.py -v
DOTFILES_TEST_ATUIN=/tmp/dotfiles-implementation/common-linux/home/.pixi/envs/atuin/bin/atuin \
DOTFILES_TEST_PYTHON=/tmp/dotfiles-implementation/common-linux/home/.pixi/envs/python/bin/python \
python3 -m unittest discover -s tests -p test_portable_history_import.py -v

DOTFILES_TEST_POWERSHELL=/tmp/dotfiles-implementation/tools/powershell/pwsh \
DOTFILES_TEST_CHEZMOI=/tmp/dotfiles-implementation/tools/chezmoi \
DOTFILES_TEST_TOOL_HOME=/tmp/dotfiles-implementation/common-linux/home \
DOTFILES_TEST_ATUIN=/tmp/dotfiles-implementation/common-linux/home/.pixi/envs/atuin/bin/atuin \
DOTFILES_TEST_PYTHON=/tmp/dotfiles-implementation/common-linux/home/.pixi/envs/python/bin/python \
/tmp/dotfiles-implementation/common-linux/home/.pixi/envs/python/bin/python \
  -m unittest discover -s tests -v
```
