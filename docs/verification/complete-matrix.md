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
| Network install and diagnostics | `python3 tests/verify_portable.py --network` | Isolated Linux common-tool install/reapply and CLI checks; all selected Bun-managed agents plus native Qoder installed/diagnosed; actual Nushell/Bash/Zsh and synthetic history behavior; common and bundle dependency resolution for every declared target. |
| Native macOS | [native-macos.yml](../../.github/workflows/native-macos.yml) | Intel and Apple silicon, workstation and remote-compute; native install and startup checks. Passed in run 38524061897 at commit `81857d6`. |
| Native Windows | [native-windows.yml](../../.github/workflows/native-windows.yml) | Windows x86-64, both roles; PowerShell, Nu/Git Bash, Windows paths, installers, clients, and history boundary. Passed in run 38524061998 at commit `81857d6`. |
| Native WSL2 | [native-wsl.yml](../../.github/workflows/native-wsl.yml) | Windows 2025 disposable WSL2 x86-64, both roles; Linux execution and Windows interoperability. Passed in run 38524061914 at commit `81857d6`. |
| Native WSL2 ARM64 | Not scheduled; the former opt-in self-hosted job was removed | Requires a Windows ARM64 runner labeled `self-hosted`, `Windows`, `ARM64` and `wsl2`, which is unavailable; no render or x86-64 result can replace it. |
| Native optional bundles | A dedicated `desktop` job per native platform in the macOS and Windows workflows | Optional bundle selection needs its own slot because the default matrices install common defaults only. Passed at commit `b64fedb` for Apple silicon and Windows x86-64 workstations; see [bundle evidence](../validation/bundles.md). |

The local verifier returns nonzero on a bad plan, unsupported bundle accepted,
supported bundle rejected, package-catalog error, test failure, network
resolution failure, or required install/diagnostic failure. Without
`--network`, its JSON report labels that layer “not run.” A foreign template,
plan, or package lock is not recorded as a native pass. The local verifier still
labels native cells “pending native CI” because it cannot observe the
platform runners; the per-platform verification notes record the actual results.

The local verifier's fourteen cells are Linux x86-64/ARM64, WSL x86-64/ARM64,
macOS Intel/Apple silicon, and native Windows x86-64, each as workstation and
remote compute. For each cell it checks defaults, `--agents none`, a named
agent selection, and every declared bundle. Unsupported bundle choices must
fail explicitly without creating their target home.

## Original requests

| # | Requested behavior | Observable check or evidence |
| --- | --- | --- |
| 1 | Diverse macOS, remote-compute, WSL, and Windows profiles | Fourteen-cell matrix plus native workflow cells; macOS, native Windows and WSL2 x86-64 have executed natively and WSL2 ARM64 remains unscheduled. |
| 2 | Test every profile without affecting the current compute host | Plan mode asserts no target creation; deterministic/network suites use disposable homes and XDG/package roots. The legacy host is never a target. |
| 3 | Nushell first, with shared Bash/Zsh settings | `test_shell_behavior.py`, platform shell suites, and canonical settings in `.chezmoidata.toml` plus shell adapters. |
| 4 | RTK installed and exposed through Pixi | Common tool catalog and isolated CLI ownership checks; Windows exception/plan checks run in its native suite. |
| 5 | Pixi installed by default | Default plan and manager install diagnostics. |
| 6 | uv installed by default with the TUNA pip mirror | Common install verifies uv and pip settings; all shell adapters assert the shared values. |
| 7 | Bun default and six Bun agents plus native Qoder installed with selection | Default/named/none plan checks and `test_agents.py` isolated installation/diagnostics; frozen lock and native manifest checks run through the updater verifier. |
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
| [0004](../adr/0004-platform-runtime-boundaries.md) | Platform-specific runtimes and native execution boundaries are explicit. | Target catalog resolution plus native macOS/Windows/WSL workflows, all of which have now run; WSL2 ARM64 is unscheduled for want of a runner. |
| [0005](../adr/0005-user-scoped-nushell-startup.md) | Managed launchers prefer Nu; ordinary deployment stays user-scoped. | Default plan asserts `primaryShell=nu` and no system/login-shell changes; explicit action plans and simulated-home guards cover opt-ins; native shell startup remains a CI check. |

## Verification snapshot

On 2026-10-13, the Ticket 13 local run passed 14 matrix cells, 98 read-only
plans, and 56 bundle outcomes. The pin/catalog check passed for 29 common
environments, 79 bundle-tool rows, six agents, and eight Windows exceptions.
The deterministic suite passed 99 tests: 32 passed and 67 environment-dependent
checks were explicitly skipped. The added opt-in checks confirm plan visibility,
simulated-home refusal, and native Windows rejection. Those skips are reported
rather than treated as evidence for installed or native behavior.

The opt-in network run also passed from fresh temporary roots: the common
installer completed two apply/install passes and its managed command, pip and
uv checks; the Bun agent lifecycle suite passed with all five default agents
and selection/reapply behavior; 10/10 Linux shell tests, 7/7 synthetic history
tests, 2/2 explicit history import tests, and the Pixi resolver for all common
and declared bundle target environments passed. The agent suite reported two
additional client-specific checks as skipped because its optional per-client
executable paths were not selected; the default installed agent diagnostics
ran in the isolated bootstrap and lifecycle checks.

On 2026-10-14 the platform runners reported at commit `81857d6`: native macOS
run 38524061897 passed all four architecture/role cells, native Windows run
38524061998 passed both roles with its console fixture, and native WSL2 run
38524061914 passed both x86-64 roles. WSL2 ARM64 did not run and is not
scheduled; no render or x86-64 result stands in for it. Those native results are
recorded per platform in the notes linked above rather than re-derived here.

MiniMax Code and native Qoder were added after those runs. Their Bun/native
installation contracts are covered by the local tests and an isolated Linux
install, but the native macOS, Windows, and WSL evidence above predates them and
must be rerun before those additions are called natively verified.

Previous isolated Linux evidence is recorded in the common-tool, agent payload,
CodeGraph, and shared-history verification notes linked above. Native macOS,
Windows, and WSL2 runner results are now recorded for the platforms that ran;
WSL2 ARM64 additionally requires a Windows ARM64 WSL2 runner.
