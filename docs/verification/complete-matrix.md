# Complete deployment matrix and evidence

Run `python3 tests/verify_portable.py` for the isolated local layer and
`python3 tests/verify_portable.py --network` to add real Linux installation,
shell/history diagnostics, and Pixi target resolution. The local command never
uses the invoking home. It supplies each plan a fresh temporary target and
starts the deterministic test suite with a scrubbed HOME, XDG, credential,
proxy, and inherited legacy-tool environment. The network layer preserves only
the proxy/certificate variables needed to reach package sources and confines
all writable state to a temporary directory under `/tmp`.

## Result layers

| Layer | Command or runner | What it establishes |
| --- | --- | --- |
| Local matrix | `python3 tests/verify_portable.py` | Fourteen profile/architecture/role cells, defaults, agent selection, all declared bundle support/rejection outcomes, source pin consistency, and deterministic acceptance tests. |
| Network install and diagnostics | `python3 tests/verify_portable.py --network` | Isolated Linux common-tool install/reapply and CLI checks; all five Bun agent installs/diagnostics; actual Nushell/Bash/Zsh and synthetic history behavior; common and bundle dependency resolution for every declared target. |
| Native macOS | [native-macos.yml](../../.github/workflows/native-macos.yml) | Intel and Apple silicon, workstation and remote-compute; native install and startup checks. |
| Native Windows | [native-windows.yml](../../.github/workflows/native-windows.yml) | Windows x86-64, both roles; PowerShell, Nu/Git Bash, Windows paths, installers, clients, and history boundary. |
| Native WSL2 | [native-wsl.yml](../../.github/workflows/native-wsl.yml) | Windows 2025 disposable WSL2 x86-64, both roles; Linux execution and Windows interoperability. |
| Native WSL2 ARM64 | Opt-in self-hosted Windows ARM64 WSL2 job in [native-wsl.yml](../../.github/workflows/native-wsl.yml) | Requires an available self-hosted runner with the documented labels; no render or x86-64 result can replace it. |

The local verifier returns nonzero on a bad plan, unsupported bundle accepted,
supported bundle rejected, package-catalog error, test failure, network
resolution failure, or required install/diagnostic failure. Without
`--network`, its JSON report labels that layer “not run.” Native cells remain
“pending” until the relevant native workflow produces runner evidence. A
foreign template, plan, or package lock is not recorded as a native pass.

The local verifier's fourteen cells are Linux x86-64/ARM64, WSL x86-64/ARM64,
macOS Intel/Apple silicon, and native Windows x86-64, each as workstation and
remote compute. For each cell it checks defaults, `--agents none`, a named
agent selection, and every declared bundle. Unsupported bundle choices must
fail explicitly without creating their target home.

## Original requests

| # | Requested behavior | Observable check or evidence |
| --- | --- | --- |
| 1 | Diverse macOS, remote-compute, WSL, and Windows profiles | Fourteen-cell matrix plus native workflow cells; foreign cells stay pending until native runners execute. |
| 2 | Test every profile without affecting the current compute host | Plan mode asserts no target creation; deterministic/network suites use disposable homes and XDG/package roots. The legacy host is never a target. |
| 3 | Nushell first, with shared Bash/Zsh settings | `test_shell_behavior.py`, platform shell suites, and canonical settings in `.chezmoidata.toml` plus shell adapters. |
| 4 | RTK installed and exposed through Pixi | Common tool catalog and isolated CLI ownership checks; Windows exception/plan checks run in its native suite. |
| 5 | Pixi installed by default | Default plan and manager install diagnostics. |
| 6 | uv installed by default with the TUNA pip mirror | Common install verifies uv and pip settings; all shell adapters assert the shared values. |
| 7 | Bun default and all five agents installed through Bun with selection | Default/named/none plan checks and `test_agents.py` isolated installation/diagnostics; frozen lock checks run through the updater verifier. |
| 8 | Deploy `AGENTS.md`, `CLAUDE.md`, and skills by default | `test_agent_payload.py` and the recorded actual-client discovery checks in [agent-payload evidence](agent-payload.md). |
| 9 | Shared command history deployed by default | `test_history_behavior.py` and `test_portable_history_import.py` use synthetic commands, fixtures, and loopback sync; platform-native adapters remain separately tested. |
| 10 | CodeGraph and agent settings installed by default | Default plan, `test_codegraph.py`, and [CodeGraph evidence](codegraph.md); project indexing remains an explicit fixture action. |
| 11 | zoxide installed and configured by default | Common install and actual `z` navigation checks in `test_shell_behavior.py` and native shell suites. |
| 12 | Tailspin installed and used by default | Common install checks `tspin`; shell suites exercise the `logs` command and print mode. |

## Accepted ADR contracts

| ADR | Contract | Observable check or boundary |
| --- | --- | --- |
| [0001](../adr/0001-separate-platform-and-host-role.md) | Platform and host role are independent; role defaults to workstation and explicit values win. | Fourteen matrix cells, selector precedence tests, and explicit remote-compute onboarding example. |
| [0002](../adr/0002-canonical-shell-settings.md) | Shared values have one canonical source with shell adapters. | `test_shell_behavior.py` compares Nu/Bash/Zsh values and preserves device overrides; native startup remains a platform CI check. |
| [0003](../adr/0003-encrypted-shell-history-sync.md) | One Atuin history with hosted encrypted sync, deliberate activation/import, and filtering. | Synthetic two-device loopback encryption, history fixtures, and explicit import tests; no real account or history is used. |
| [0004](../adr/0004-platform-runtime-boundaries.md) | Platform-specific runtimes and native execution boundaries are explicit. | Target catalog resolution plus native macOS/Windows/WSL workflows; WSL ARM64 awaits a suitable self-hosted runner. |
| [0005](../adr/0005-user-scoped-nushell-startup.md) | Managed launchers prefer Nu; ordinary deployment stays user-scoped. | Plan asserts `primaryShell=nu` and no system/login-shell changes; isolated apply/reapply and native shell startup tests. |

## Verification snapshot

On 2026-10-13, the Ticket 13 local run passed 14 matrix cells, 98 read-only
plans, and 56 bundle outcomes. The pin/catalog check passed for 29 common
environments, 79 bundle-tool rows, six agents, and eight Windows exceptions.
The deterministic suite passed 95 tests: 28 passed and 67 environment-dependent
checks were explicitly skipped. Those skips are reported rather than treated
as evidence for installed or native behavior.

The opt-in network run also passed from fresh temporary roots: the common
installer completed two apply/install passes and its managed command, pip and
uv checks; the Bun agent lifecycle suite passed with all five default agents
and selection/reapply behavior; 10/10 Linux shell tests, 7/7 synthetic history
tests, 2/2 explicit history import tests, and the Pixi resolver for all common
and declared bundle target environments passed. The agent suite reported two
additional client-specific checks as skipped because its optional per-client
executable paths were not selected; the default installed agent diagnostics
ran in the isolated bootstrap and lifecycle checks. Native execution remains
pending for the platform workflows listed above.

Previous isolated Linux evidence is recorded in the common-tool, agent payload,
CodeGraph, and shared-history verification notes linked above. Native macOS,
Windows, and WSL2 runner results remain pending until workflows execute on their
own platforms. WSL2 ARM64 additionally requires the opt-in self-hosted runner.
