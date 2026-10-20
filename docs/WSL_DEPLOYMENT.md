# WSL deployment

Run the Unix entry point from the distro's Linux filesystem on a new or test
device. WSL supplies the complete Nushell, Bash, and Zsh environment. Platform
detection recognizes WSL's session variables or Microsoft kernel; architecture
comes from Linux `uname -m`. Windows `USERPROFILE` and `APPDATA` do not replace
the Linux home or configuration paths.

```bash
bash bootstrap.sh --role workstation --plan
bash bootstrap.sh --role workstation
# A compute-oriented WSL device selects its role explicitly.
bash bootstrap.sh --profile wsl-remote-compute
```

`--platform`, `--profile`, `--role`, `--arch`, and `--home` retain the normal
selection rules. Default role is workstation, including SSH sessions. Managed
interactive launchers prefer Nu; explicit Bash/Zsh commands and agent scripts
retain their suitable shell. Shared PATH entries precede the existing PATH, so
WSL's Windows command discovery remains available when provided by the session.

Common tools, all seven supported agents (six Bun-managed plus native Qoder),
CodeGraph settings, instructions and skills deploy by default. Both TUNA Python
configurations, zoxide, Tailspin `logs`, and Atuin hooks follow the Unix
adapters. History initially reports
pending activation; use `dotfiles-history first-device` or `join` deliberately.
Indexing remains an explicit project action. Deployment uses user files and
does not import a distro, enable a Windows feature, change account login shells,
or install system packages. Read [the deployment boundary](DEPLOYMENT_BOUNDARY.md),
[shared settings](SHARED_SHELL_SETTINGS.md), and [history setup](SHARED_HISTORY.md)
for their corresponding behavior.

## Native verification

The workflow [native-wsl.yml](../.github/workflows/native-wsl.yml) runs x86-64
WSL2 on `windows-2025` for workstation and remote compute. The disposable CI
controller [wsl.ps1](../tests/native/wsl.ps1) requires explicit `-Provision`.
Its `-Plan` mode prints the selected pinned image without creating any state.

```powershell
# Planning also works with the separately supplied Linux PowerShell parser.
./tests/native/wsl.ps1 -Plan -RunnerTemp $env:RUNNER_TEMP `
  -Source $PWD -Role remote-compute -Architecture x86_64

# Provisioning is for a disposable Windows CI runner.
./tests/native/wsl.ps1 -Provision -RunnerTemp $env:RUNNER_TEMP `
  -Source $PWD -Role workstation -Architecture x86_64
```

The controller verifies an official Ubuntu 24.04.5 rootfs SHA256, imports a
unique distro under `RUNNER_TEMP` with `--version 2`, checks the reported WSL
generation, kernel and CPU, and creates an unprivileged Linux test user. It
transfers `git archive HEAD` into that user's Linux source directory. This
preserves Git executable modes and committed bytes across NTFS; the product
bootstrap continues to apply its working source. Focused LF attributes also
keep Unix entry points usable in a Windows checkout, while the raw portable
skill snapshot retains its byte-preservation exception.

Only the disposable distro receives the prerequisite apt step. Its initial
rootfs bytes are pinned; that subsequent Ubuntu package step uses repository
versions available at execution time. Node, Bun, the common managed tools and
agents are installed by the product bootstrap rather than preinstalled through
apt. Cleanup terminates and unregisters the owned distro even after a failure.

The native [Linux verification command](../tests/native/wsl.py) first requires
a Microsoft WSL2 kernel and the requested Linux architecture. It then checks
a Windows fixture path containing spaces, Windows command execution, and a
Linux-to-Windows UNC path roundtrip. Bootstrap runs without a platform override
to verify detection in the actual environment. It installs defaults, checks
exact common package versions through Pixi's public JSON inventory and harmless
CLI diagnostics, starts all three standalone shells, and verifies TUNA,
navigation and log behavior. Actual client discovery, CodeGraph access and
synthetic encrypted-history acceptance use the shared suites on WSL. Reapplication
checks local credentials/history and unrelated installations, agent opt-out,
pending activation, and absence of automatic indexing.

The artifact contains controller/runtime JSON reports only. It records the
Windows image, WSL generation/kernel/CPU, pinned rootfs, source commit and run
URL. Distro import, kernel startup, virtualization or product failures fail
visibly. WSL1 and ordinary Linux cannot satisfy this gate. No deployed home,
credential/history database or source archive is uploaded.

WSL ARM64 is not scheduled for native execution. It would need a self-hosted
Windows ARM64 runner labeled `self-hosted`, `Windows`, `ARM64`, and `wsl2`,
which this project does not have, so the former opt-in `workflow_dispatch` job
was removed rather than left as a permanently pending cell. The pinned ARM64
rootfs and the ARM64 planning/render checks remain, so a runner can be added
without new source state. Native Ubuntu ARM64 execution and Linux ARM64 package
solving are recorded separately.

| Rootfs target | Official versioned source | SHA256 |
| --- | --- | --- |
| x86-64 | [Ubuntu 24.04.5 WSL amd64](https://releases.ubuntu.com/24.04.5/ubuntu-24.04.5-wsl-amd64.wsl) | `bb415d824822c4b878125729af451a5d18fb13d1cf5cbed9a7393ad64ac6039e` |
| ARM64 | [Ubuntu 24.04.5 WSL arm64](https://cdimage.ubuntu.com/releases/24.04.5/release/ubuntu-24.04.5-wsl-arm64.wsl) | `74478b5024d9047397ba79d17c27f73caf85ada4988f88cffc2892d65e6a806b` |

Published hashes come from the adjacent [amd64 SHA256SUMS](https://releases.ubuntu.com/24.04.5/SHA256SUMS)
and [ARM64 SHA256SUMS](https://cdimage.ubuntu.com/releases/24.04.5/release/SHA256SUMS).
Provisioning follows [Microsoft's custom distro import](https://learn.microsoft.com/en-us/windows/wsl/use-custom-distro)
and [WSL command reference](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).

## Evidence recorded here

The local compute-host checks passed selection via WSL variables and a kernel
probe fixture; all four x86-64/ARM64 and workstation/compute rendering cells;
regular instruction/skill/config files; credential/history-marker/registry
preservation over repeated application; and Windows-checkout LF preservation.
These are isolated Linux rendering and selection results. Common Linux package
resolution for both architectures is recorded in
[common-tool evidence](verification/common-tools.md).

Linux PowerShell 7.6.6 parsed the controller and passed read-only ARM64 planning
and non-Windows provisioning refusal. The Python gate rejected this ordinary
Linux kernel before creating a deployment home and wrote `nativePass: false`.
The available yq parser accepted the workflow. These checks establish the
planning/refusal contracts and syntax only.

Both WSL2 x86-64 role cells have since passed natively in run
[38524061914](https://github.com/JoJoTsui/dotfiles/actions/runs/38524061914) at
commit `81857d6`, 2026-10-14, on a disposable Ubuntu 24.04.5 WSL2 distro. Each
controller report records `nativePass: true` and `phase: complete`, and each
passes the Windows executable/path roundtrip, a full default WSL bootstrap,
managed command and agent versions, standalone shells with navigation/logs and
TUNA mirrors, the `test_shell_behavior.py`, `test_agent_payload.py`,
`test_codegraph.py` and `test_history_behavior.py` suites on actual WSL
execution, and reapplication preserving credentials, history, unrelated
installations and omitted agents while reporting activation as pending. No WSL2
ARM64 cell has run; it is not scheduled, since no Windows ARM64 WSL2 runner is
available.

After composing the portable Unix test selectors, all 40 WSL-selected
boundary/shell/payload/CodeGraph/history cases passed in 175.614 seconds with
zero skips. These ran actual pinned Linux binaries in independently writable
fixture homes using `DOTFILES_TEST_PLATFORM=wsl` and the remote compute role.
They prove Linux execution of WSL-rendered configuration, including client
discovery, MCP, encrypted loopback history and terminal shell behavior. They
do not establish a WSL kernel or Windows interoperability result.

The required deterministic suite separately ran 70 cases: 39 passed and 31
explicit missing-hook/network/tool checks skipped. Read-only public Pixi
inventory also confirmed all 29 owned common environments' exact numeric
version components and Linux subdirs. Helix's source pin `25.07.1` appears as
`25.7.1` in Conda metadata; native verification accepts that numeric spelling
equivalence while keeping each component exact.

The native Nu checks launch with `-e` and an explicit harmless print and exit.
This loads ordinary env/config and vendor startup, which command-only `-c`
omits. The verifier's `--probe-nu` mode checks the same launch in an existing
rendered WSL home and always reports `nativePass: false`. Its two-role
regression reproduced the missing `EDITOR` with `-c` and passes with `-e`,
including role settings, navigation/log commands, prompt and history hooks.
The focused WSL/shell gate passed all 19 cases with zero skips in 78.101
seconds on Linux. Both actual WSL2 x86-64 role cells have now passed natively;
the WSL2 ARM64 cells remain unscheduled for want of a runner.
