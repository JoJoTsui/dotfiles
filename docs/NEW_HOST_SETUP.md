# Set up a new host

This repository applies a user-scoped environment from its working tree. Start
with a new or test device; ordinary setup does not change `/etc`, your account
login shell, credentials, command history, or project indexes.

## Select the platform and role

Linux, macOS, and WSL use `bootstrap.sh`. The platform is detected, and the
role defaults to `workstation`, including over SSH. Preview the selection and
actions before installation:

```sh
bash bootstrap.sh --plan
bash bootstrap.sh --role remote-compute --plan
```

Apply on a workstation with the detected platform, or select a remote-compute
role explicitly:

```sh
bash bootstrap.sh
bash bootstrap.sh --role remote-compute
```

You can also select a complete profile explicitly, for example
`--profile macos-workstation`, `--profile wsl-remote-compute`, or
`--profile linux-remote-compute`. Platform and role can be given separately
with `--platform` and `--role`. Linux, WSL, and macOS support x86-64 and ARM64;
native Windows currently supports x86-64 only. WSL runs the Unix bootstrap
inside the distribution and provides Nushell, Bash, and Zsh.

For native Windows, run PowerShell 5.1 or newer from the checkout:

```powershell
./bootstrap.ps1 -Profile windows-workstation -Plan
./bootstrap.ps1 -Profile windows-workstation
./bootstrap.ps1 -Role remote-compute
```

Native Windows provides Nushell and PortableGit's Git Bash. Use the Unix
bootstrap inside WSL for the full three-shell setup. Read
[Windows deployment](WINDOWS_DEPLOYMENT.md) and
[WSL deployment](WSL_DEPLOYMENT.md) for their platform-specific boundaries.

The legacy `--class t9k` selector remains an alias for Linux remote compute.
It is kept for compatibility; new deployments should name the platform and
role they intend to use.

## Choose optional tools and agents

All seven supported coding agents (six Bun-managed plus native Qoder),
CodeGraph, and the common toolchain install by default. A selection controls
new installation and does not uninstall an agent that is already present:

```sh
bash bootstrap.sh --agents all
bash bootstrap.sh --agents codex,kimi,qoder
bash bootstrap.sh --agents none
```

The managed wrapper exposes the same operations plus pin refresh and status:

```sh
dotfiles-agents install all
dotfiles-agents update all
dotfiles-agents status
```

The optional `bio`, `gpu`, `desktop`, and `developer` bundles are off by
default. Select only bundles declared for the chosen platform and architecture:

```sh
bash bootstrap.sh --bundles bio,developer
```

Unsupported bundle/platform combinations fail before deployment state is
created. The bundle inventory lists the supported targets and the host
capabilities that must be configured separately.

Use `--apply-only` to apply and validate files without installing tools or
agents. Normal bootstrap installs pinned common tools and selected agents.
`--agents-only` is for a host that already has the pinned Bun and Node runtime.

On Linux, macOS, and WSL, system Bash defaults and account login-shell changes
are separate explicit opt-ins:

```sh
bash bootstrap.sh --system-config
bash bootstrap.sh --login-shell
```

`--system-config` backs up the platform Bash rc once and installs an owned,
repeatable block. `--login-shell` registers the managed Nu launcher in
`/etc/shells` and calls `chsh`; it requires a full deployment and the current
account home. These flags are unavailable on native Windows. Planning reports
the requested actions without applying them. Simulated homes cannot execute
either action.

## Start Nushell and shared history

Managed interactive launchers prefer Nushell. Bash and Zsh remain available on
Linux, macOS, and WSL for scripts and agent subprocesses. Native Windows uses
Git Bash for agent subprocesses. Shell settings share one canonical set of
values, with syntax and startup handled by each shell's adapter. The `logs`
command opens Tailspin; `logs --print FILE` emits the log without paging.

Atuin records local command history in all supported shells. New devices can
record and search before sync activation; setup and history import are explicit
actions:

```text
dotfiles-history status
dotfiles-history first-device
dotfiles-history join
dotfiles-history import
dotfiles-history import bash --file /path/to/selected-history
dotfiles-history import zsh --file /path/to/selected-history
dotfiles-history import nu --file /path/to/selected-history.txt
dotfiles-history import nu-db --file /path/to/selected-history.sqlite3
dotfiles-history sync
```

Use `first-device` once, then `join` on other devices with the same Atuin
account and privately backed-up encryption key. Import only the history files
you select. Regular bootstrap does not read or import existing shell history,
activate an account, or copy agent conversations. See
[shared history](SHARED_HISTORY.md) for the formats and secret filtering.

## Verify and update

Run the local acceptance entry point from the checkout. It checks all fourteen
platform/architecture/role cells, agent selections, declared bundle outcomes,
the version catalogs, and the deterministic test suite. Plan checks and tests
use isolated temporary homes with inherited profile, credential, and legacy
tool-path variables removed:

```sh
python3 tests/verify_portable.py
```

To additionally install the pinned Linux common tools, install and diagnose all
seven agents (including native Qoder), run shell/history checks, and resolve
every common and declared bundle target with Pixi, opt in to the network layer:

```sh
python3 tests/verify_portable.py --network --report /tmp/dotfiles-verification.json
```

The network run creates and removes its installation, caches, homes, and
synthetic history under `/tmp`. It never deploys to the invoking user's home.
Network failures return nonzero. Native execution is a separate result: the
macOS, Windows, and WSL workflows run on native runners. A Linux render or
foreign package resolution is not a substitute for native execution. See
[the full matrix and evidence map](verification/complete-matrix.md).

Version updates are proposal-driven. `dotfiles-agents update SELECTION` performs
the selected transaction; to review or run it manually, use the explicit
refresh and verification workflow:

```sh
python3 deployment/update_versions.py check
python3 deployment/update_versions.py refresh --proposal /tmp/version-proposal.json \
  --bun /absolute/path/to/pinned/bun
python3 deployment/update_versions.py verify --bun /absolute/path/to/pinned/bun \
  --pixi /absolute/path/to/pinned/pixi --resolve
```

Review the complete repository diff and rerun `python3 tests/verify_portable.py`
before committing an accepted update. See
[version update details](verification/updates.md).

The documented `linux-remote-compute` profile describes the current legacy
compute host for validation. That live host is not an apply target; use a
disposable home or a new device for installation checks.
