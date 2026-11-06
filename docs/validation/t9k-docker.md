# Ubuntu container deployment verification

Status: both Ubuntu compatibility baselines passed. These are emulated amd64
userspace results, not native T9K or Windows results. Failed attempts remain
preserved separately from the completed evidence below.

Those historical runs used a three-skill synthetic library for the client
discovery suites. They establish fixture behavior, not discovery of every
fetched default skill. The current native Linux gate separately requires the
actual selected library to be discovered after fresh install and reapply;
new reports are required to establish that additional coverage.

The review fix was checked against the preserved Ubuntu 24.04 installation,
with its home mounted read-only and networking disabled. Pi, OpenCode, Claude,
Kimi, and Qoder discovered all 98 selected skills; Codex's prompt diagnostic
included the 73 automatic skills. Pi preserved the 25 manual-only flags, and
OpenCode exposed their explicit `autoinvoke: false` flags while omitting that
optional field for automatic skills. All 12 payload fixture tests and 10
focused discovery regressions also passed without skips. This was a runtime
verification of the fix, not a new fresh-install or reapplication matrix.
The frozen source overlays and artifact hashes are recorded in
`/private/tmp/dotfiles-discovery-proof-u1nogt1t/inputs.json`; its installed
discovery report SHA-256 is
`fb823f27b7173ebaf9fe04c42c6f7d15ca57922b289636892c3b87ecd4c7e274`.
The fixture-suite evidence remains in
`/private/tmp/dotfiles-discovery-proof-n04m9jmy/artifacts/fixture-suite.json`,
alongside the preserved initial OpenCode API-assertion failure.

## Agreed scope

The target is the T9K profile, `linux-remote-compute`, on Ubuntu x86_64.
Ubuntu 20.04 and 24.04 are the selected compatibility baselines. Neither is
asserted to be the unidentified original T9K image.
The legacy selector `--class t9k` must resolve to the same profile. Verification
covers the full default deployment: common tools, all seven coding agents,
CodeGraph, shared shell settings, portable instructions and skills, runtime
discovery/MCP, synthetic shared-history behavior, and reapplication with
preservation checks. Required behavior checks must run without unexplained skips.

Optional bundles, real account login or history import, and system/login-shell
changes retain their separate opt-in policy. This work does not apply to the
existing T9K account or run its legacy migration adapters. Native Windows
execution remains a separate Windows-runner task.

## Completed verification

| Baseline | Deployment evidence | Test evidence | Result |
| --- | --- | --- | --- |
| Ubuntu 20.04, glibc 2.31 | Fresh empty-home installation and full reapplication at `825f0e2` | Complete gate at `825f0e2`: 336 passed, 35 classified exclusions | Passed |
| Ubuntu 24.04, glibc 2.39 | Fresh empty-home installation and full reapplication at `825f0e2` | All suites repeated at `ce06804`: 337 passed, 35 classified exclusions | Passed |

Both deployments verified all 50 declared commands before and after
reapplication, exact package pins, copy-mode files, remote editor settings,
synthetic settings/auth/history preservation, unrelated package entries, shared
shell behavior, instruction/skill discovery and real CodeGraph/client MCP
connections. The history tests exercised synthetic encrypted exchange and
offline operation without activating a real account.

Ubuntu 24.04's initial run stopped at a history-fixture PTY exit race after
registration had succeeded. Commit `ce06804` changes only that test file:
production source is identical to `825f0e2`. Its continuation reused the
preserved installation and warm caches, mounted the home and original report
read-only, checked the 1,280-file strict snapshot, repeated all five runtime
suites and the 325-case deterministic suite, then rechecked the snapshot,
source and original report hash. It was not another fresh installation.

Each baseline has zero unexplained skips. The 35 exclusions comprise 29 named
foreign-platform cases and six explicitly unselected checks for optional
Herdr/bundle/foreign-resolution work and separate opt-in network installers.
The full default installation itself ran in this gate. Each excluded test's
identifier, reason and classification is recorded in its structured report.

The source stayed unchanged during each run. Successful containers and their
temporary volumes were removed; earlier failed containers/homes remain stopped
for diagnosis. These Docker checks did not apply to a real Mac/T9K account or
push changes.

Evidence on the verification Mac:

- Combined completion report:
  `/private/tmp/dotfiles-ubuntu-acceptance-825f0e2/history-continuation/completion-report.json`
- Original fresh-install/reapplication reports:
  `/private/tmp/dotfiles-ubuntu-acceptance-825f0e2/ubuntu-{20.04,24.04}/gate/report.json`
- Continued Ubuntu 24.04 test report:
  `/private/tmp/dotfiles-ubuntu-acceptance-825f0e2/history-continuation/ubuntu-24.04/gate/report.json`
- Independent artifact recheck:
  `/private/tmp/dotfiles-ubuntu-acceptance-825f0e2/history-continuation/final-integrity.json`

The artifact recheck verified all 391 Ubuntu 20.04 artifacts, 382 original
Ubuntu 24.04 artifacts and 24 continuation artifacts against their recorded
SHA-256 inventories, every command log hash, the preserved report hash, and
both continuation-script hashes. The combined
completion report SHA-256 is
`5c849c1db75c5c047b301a0168bec6d8da1fb35693f7249d1f4a87e2d960c4f7`.

The immutable Ubuntu base images were:

- 20.04: `ubuntu@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214`
- 24.04: `ubuntu@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852`

Fresh targets started with empty managed-tool caches. Docker base/build layers
were reused after the initial attempt; the Ubuntu 24.04 continuation explicitly
reused its installed tools. Public downloads used the container's direct
network route, with no host credentials, host home or Docker socket mounted.

## Repeating the gate

Use a clean committed checkout, Python 3.11 or newer, Docker with Buildx and a
local Linux engine capable of `linux/amd64`, and room for four CPUs and 8 GiB:

```bash
artifacts_parent=$(mktemp -d)
python3 tests/docker_ubuntu.py --artifacts "$artifacts_parent/run"
```

The runner freezes the source, tests both baselines sequentially in fresh
non-root homes, records emulation and resource limits, audits skips, and retains
failed attempts. It does not deploy to an existing account.

## Environment facts

The supplied T9K `uname` reports Linux x86_64 with Ubuntu kernel
`5.4.0-144-generic`. It does not identify the Ubuntu userspace release, glibc
version, or original container image.

The available local Docker endpoint is OrbStack's Linux ARM64 engine. It reports
Docker Engine 29.8.2, kernel `7.2.12-orbstack-00394-gbecdd6130068`, 14 CPUs, and
16,818,343,936 bytes of VM memory. Ubuntu x86_64 execution requires emulation;
successful execution must be established by the test. No Ubuntu base image was
cached before this verification began. The initial Ubuntu 20.04 amd64 probe
succeeded, reporting Ubuntu 20.04.6, glibc 2.31, four effective CPUs and an 8 GiB
memory limit.

An Ubuntu container shares the engine's kernel. These tests can establish
deployment behavior for the selected Ubuntu userspace under the recorded
emulation, but cannot establish behavior on T9K's exact kernel, network-mounted
filesystem, watcher limits, device/GPU configuration, or existing legacy state.

## Existing checks to reuse

`tests/verify_portable.py` provides profile planning and deterministic checks.
Its network mode installs Linux common tools and agents and runs shell/history
checks, but its installation defaults to the workstation role. The T9K gate
therefore needs an explicit full remote-compute installation and reapplication.

The existing network mode also does not supply the installed CodeGraph/client
binaries to the runtime MCP tests. Passing that mode alone does not prove this
scope. The container gate must supply the real installed binaries to the
applicable discovery/MCP suites and audit every required skip.

Use synthetic device settings, credentials, history and project fixtures. Keep
source read-only, install into task-owned storage, and expose neither the real
home nor Docker socket to the test container. Test source must exclude ignored
device files and credentials. Container loopback is distinct from Mac loopback;
record any container-reachable public-download proxy arrangement explicitly.

Reports must identify the tested source and checksum, image digest, userspace,
glibc, kernel, processor/execution mode, resource limits, network/cache mode,
executed checks, skips and artifact checksums. Preserve failed attempts rather
than replacing them with later successful results.

## Confirmed execution plan

1. Resolve each Ubuntu image digest and verify `linux/amd64` execution. Record
   processor emulation and the actual engine kernel.
2. Run one baseline at a time, initially capped at four CPUs and 8 GiB of memory.
   Measure container cgroup limits and cap child parallelism within that grant.
   After any Docker client failure, confirm its container is absent or stopped
   before advancing. Uncertain state or failed shutdown blocks later baselines.
3. Supply a read-only, identified source export containing no ignored device
   files. Start with a fresh non-root test account and empty managed-tool caches
   on each baseline. Retain subsequent cache use and failed attempts explicitly.
4. Exercise the ordinary full public bootstrap and reapplication for
   `linux-remote-compute`, plus legacy-selector equivalence. Preserve synthetic
   pre-existing settings, auth sentinels and unrelated package entries.
5. Run applicable deterministic, real shell, instruction/skill discovery,
   CodeGraph/MCP and synthetic encrypted-history suites using the installed
   runtimes. Audit required skips separately from foreign-platform exclusions.
6. Verify regular files, command versions, remote editor settings, isolated state
   roots and reapplication stability. Require repository-owned configuration,
   skills, helpers and executable bytes to remain stable. Record Pixi's generated
   activation settings before and after reapplication separately: their values
   depend on the install environment. Validate their executable targets and
   rerun inventory, version, command-path and runtime checks after reapplication.
7. Record value-free reports and checksums outside the source. Keep repository
   documentation/tests and any necessary fixes reviewable in focused local
   commits; publishing changes remains a separate action.

Completion requires an explicit pass or failure for each Ubuntu baseline and
each required behavior gate. A container or emulation limitation must remain
visible rather than being counted as a successful deployment.

The shared plan was confirmed before image pulls and execution. It does not
authorize application to the real T9K or Mac account.

## Preserved attempts

The first attempt tested source `8ea9debe698dbcfa913ac228777904610fbec40a`.
Its report is `/private/tmp/dotfiles-ubuntu.f6YTGZ/run/docker-report.json`.

- Ubuntu 20.04 stopped at source application: the standard Chezmoi 2.73.3 amd64
  archive requires glibc 2.32/2.34, above this baseline's glibc 2.31. The
  same-version official static musl archive replaces it in source; runtime
  verification of that fix is pending.
- Ubuntu 24.04 completed both full bootstraps, inventory and version checks.
  The verifier then rejected changed Pixi activation metadata before runtime
  suites ran. Pixi regenerates `exe`, `env` and `path_diff` from its activation
  context; all three affect launch behavior. Initial values were not retained,
  so this attempt does not establish semantic equality or behavioral success.
  The corrected verifier records those values separately and repeats command
  checks after reapplication, while retaining strict source-file stability.

Failed containers and home volumes are stopped and retained for diagnosis.
Neither baseline had passed that first attempt.

The second attempt tested source `88b46aa7b845a361f6d9842ff15a16503815a042`.
Its report is `/private/tmp/dotfiles-ubuntu-rerun-88b46aa/docker-report.json`.
Fresh installation, all 50 declared commands, full reapplication and synthetic
preservation passed on both baselines. Ubuntu 20.04 passed 37 runtime tests but
stopped at a relocated Atuin test executable: its `$ORIGIN/../lib` OpenSSL
dependencies were missing. A read-only follow-up confirmed the loader error;
the prefix-preserving fixture then passed all six applicable importer tests.

Ubuntu 24.04 passed all five required runtime suites (43 applicable tests and
two named macOS-only exclusions). The remaining 324-test suite then reported
45 failures and five errors. Diagnosed harness issues included an executable
path containing spaces in generated shebangs, Docker's default `noexec` tmpfs,
missing system Python/Zsh fixture prerequisites, an omitted Worktrunk fixture
tool and Psych's changed alias default. These results remain preserved as
failed attempts.

The third attempt tested source `3565dbcbbe9499b6863896670d5d0257d72afe79`.
Its report is `/private/tmp/dotfiles-ubuntu-final-3565dbc/docker-report.json`.
Both fresh installations, all 50 commands and reapplications passed. A PTY
fixture then observed EOF before the child exit was waitable, despite receiving
the expected shell output. A controlled child reproduced that fixture race;
the fix waits within the original deadline.

The separate continuation at test source
`ebd356123e6bb0e55f71421c23ff84f15043641e` preserved the old report and mounted
the deployment read-only. Its report is
`/private/tmp/dotfiles-ubuntu-final-3565dbc/continuations-ebd3561/completion-report.json`.
Ubuntu 20.04 passed all 44 applicable runtime tests, then the 325-case broader
suite found nine errors in Git fixtures and one proxy-helper failure. The
continuation stopped before Ubuntu 24.04 and remains a failed attempt.

Focused Focal checks identified Git 2.25 fixture assumptions and eager generic
annotations in the proxy helper before managed Python exists. Portable fixture
initialization and explicit reachable-ancestor serving fix the Git tests;
postponed annotations fix the helper on Python 3.8.10. The original helper's
TypeError was reproduced, and all 28 affected skill/helper cases then passed
with Focal's actual Git 2.25.1 and Python 3.8.10. The deployed helper change
required another fresh verification, recorded in the completed evidence above.
