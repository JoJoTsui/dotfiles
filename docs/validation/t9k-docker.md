# Ubuntu container deployment verification

Status: shared plan confirmed; implementation and execution in progress.
The first full attempt failed on both baselines; corrected-source verification
is pending. Installation success alone is not a deployment-gate pass.

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
No baseline is recorded as passed yet.
