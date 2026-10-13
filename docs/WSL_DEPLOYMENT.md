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

Common tools, all five Bun-managed agents, CodeGraph settings, instructions and
skills deploy by default. Both TUNA Python configurations, zoxide, Tailspin
`logs`, and Atuin hooks follow the Unix adapters. History initially reports
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

WSL ARM64 has an opt-in `workflow_dispatch` input named `wsl_arm64`. It requires
a self-hosted Windows ARM64 runner labeled `self-hosted`, `Windows`, `ARM64`,
and `wsl2`. Both roles use the pinned ARM64 rootfs and the same actual WSL2
checks. A missing suitable runner remains pending. Native Ubuntu ARM64
execution and Linux ARM64 package solving are recorded separately.

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
planning/refusal contracts and syntax; native Windows/WSL execution remains
pending until the workflow runs. Both WSL2 x86-64 roles and both WSL2 ARM64
roles therefore remain explicitly pending at this implementation point.
