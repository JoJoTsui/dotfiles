# Windows implementation evidence

Ticket 11 implements the native PowerShell boundary and windows-2025 role jobs.
Native Windows execution has now happened: workflow run
[38524061998](https://github.com/JoJoTsui/dotfiles/actions/runs/38524061998) at
commit `81857d6`, 2026-10-14, with both role jobs successful and the console
fixture reporting `status: passed`. The suite ran 10 tests in 628.896s, `OK
(skipped=1)`; the single skip is `test_normal_nu_startup_loads_the_rendered_
environment_without_config_flags`, which needs the pinned Nu and renderer
together and is not counted as execution.

| Layer | Evidence | Status |
| --- | --- | --- |
| PowerShell 7.6.6 on Linux | Public plan, source-copy application/reapplication, native-file layout, literal JSON/TOML credentials, client/payload/auth/history preservation, invalid selections, nested copy/installer symlinks and private parser failure | Six tests passed; foreign rendering only |
| Actual Nu 0.116.1 on Linux | Ordinary startup of the Windows-rendered shared configuration, without individual config flags or inherited EDITOR/Python preference | One regression passed; `-c` failed before correction to `-e` print/exit |
| Actual Atuin 18.23 on Linux | `nu-file`/`nu-db-file` migration, original-file preservation, secret pruning, LF/UTF-8/multiline behavior, SQLite timestamp/cwd/exit/raw duration/signed-session metadata | Two tests passed; shared adapter behavior; activation is a native claim below |
| Unix adapter regressions | Public deployment (13), actual Nu/Bash/Zsh paths/overrides/hooks/logs (10), actual Atuin import/recording/encrypted loopback sync (7) | Passed after fixing a rendered function separator |
| Integrated regression suite | Managed Python 3.13, isolated Chezmoi/PowerShell/common tools, all applicable deployment/shell/history tests after merging native macOS and WSL | 87 tests in 294.755s; 72 executed, 15 explicitly skipped |
| WSL PowerShell planning/refusal | The two shared checks omitted by the full invocation's tool flag naming, run with DOTFILES_TEST_PWSH | Two tests passed in 1.573s; no provisioning |
| Corrected shared startup integration | After merging a720b3cb385efe0b18da580dc738dc22f565c07f: selectors, actual shell startup, Windows boundary and corrected WSL ordinary Nu startup | 40 tests in 162.083s; 39 executed, native Windows install explicitly skipped |
| Native package solves | Ticket 02 resolves common win-64 requirements; ticket 08 resolves the desktop target independently | Recorded in their evidence; not binary execution |
| Native PowerShell 5.1 | Public boundary and apply-only without Git Bash | Passed in run 38524061998 |
| Native Windows tool/agent execution | Full pinned install/reapply, `.cmd` and bare companion version diagnostics through Nu/Git Bash, Kimi shell doctor, resolved root/PATH behavior, uv/pip discovery | Passed in run 38524061998 |
| Native client discovery/MCP | All five client discovery interfaces, native Node stdio command, Claude/Kimi/OpenCode connections, Codex registration, explicit temporary CodeGraph fixture | Passed in run 38524061998 |
| Native console/history | Attached-console Unicode password and key input, wrong-key retry, normal/failed child mode restoration, two-device PASETOv4 loopback sync, Nu interactive recording/navigation/logs, non-console rejection, native explicit-file migration | Passed in run 38524061998 |
| Git Bash interactive recording | The same token/navigation/log assertions for Git Bash through the managed rcfile | Deferred; see the interactive-shell boundary note below |
| Unredirected Known Folder fallback | Ordinary native-home discovery with XDG absent | Deferred; see the deferred-gates note below |
| Console cancellation/TOTP browser flow | Public wrapper terminates/waits in cancellation and masks all console input; fixture targets normal and failed child restoration | Deferred; see the deferred-gates note below |

The native rows above were verified by the GitHub-hosted Windows runner, not by
this Linux session. A separate `desktop` job also runs the native install with
`--bundles desktop` and passed at commit `b64fedb` in run
[38566605610](https://github.com/JoJoTsui/dotfiles/actions/runs/38566605610),
covering the workstation role only. See
[bundle evidence](../validation/bundles.md) for the shared optional-bundle
result. The Linux PowerShell tool remains the official
checksum-verified 7.6.6 archive; it establishes parsing and rendering only, not
PowerShell 5.1 compatibility, Windows ACLs, reparse semantics, archive execution,
native shim spawning or console behavior. The public boundary accepts foreign
`ApplyOnly` only with an explicit home; foreign native installation fails before
state creation. All local homes, caches, commands and credentials were
disposable/synthetic.

## Interactive-shell boundary

The console fixture probes Nu and Atuin as attached-console clients, because both
read a Windows console directly. Git Bash is an MSYS2 program that reads the
console through its own console layer, which upstream documents as reliable only
for plain character streams and a "lottery" for line editing; the managed wrapper
also starts this shell with `--login` rather than as a raw console shell. Its
token, navigation, shared-history and Tailspin assertions therefore run
interactively with piped input instead of through the owned console. That keeps
the managed rcfile and its hooks under test without depending on MSYS2 console
support, and it means the Nu result is not silently extended to Git Bash.

## Deferred gates

Two claims remain deliberately unexercised, and are recorded as deferred rather
than as passes or failures:

- **Unredirected Known Folder fallback.** Ordinary native-home discovery with no
  XDG variables is not exercised because every isolated test preserves its
  pre-startup roots. Establishing it needs a Windows host started with XDG
  absent, which the disposable-home contract forbids.
- **Console cancellation and TOTP/browser flow.** The public wrapper's
  cancellation path and console-input masking are untested end to end, and a
  hosted Atuin account with browser or TOTP input is outside this repository's
  synthetic-only policy. No such request was made.

Both belong to an explicit interactive Windows host session. The passing console
fixture covers normal and failed child restoration only, and neither deferred
gate may be inferred from it.

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
