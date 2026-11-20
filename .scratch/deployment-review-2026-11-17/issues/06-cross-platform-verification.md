# 06: Verify deployment across supported platforms

**What to build:** Record evidence for the repaired deployment across macOS, headless Linux, and native Windows using the available native gates and disposable homes.

**Blocked by:** 01: Preserve device-owned generated skills; 02: Require reviewed Windows skill locks; 03: Preserve Windows skill collisions during preflight; 04: Gate and back up Magpie client migration; 05: Detect and reconcile Magpie wiring drift.

**Status:** ready-for-agent — the macOS native gate passes on the final
source; the headless Linux gate runs and is corrected; native Windows remains
unavailable here

- [ ] Run appropriate focused tests and simulated application checks, reporting actual results and environmental failures.
- [ ] Run native platform gates where their platform and prerequisites are available; identify each unavailable gate and why.
- [ ] Review changes, documentation, ownership preservation, and repository status without exposing secrets.

## Comments

Initial baseline: both legacy Linux profiles applied in simulated homes with the offline skill fixture. A live skill fetch failed after a partial transfer and TLS errors. The latest GitHub macOS, Linux, Windows, and WSL jobs did not start because of an account billing lock. The local machine has neither PowerShell nor a running Linux container runtime.

On Apple silicon, the macOS configuration suite's Windows remote-editor subcase failed because it inherited an unsupported ARM target; the same case passed when explicitly set to x86-64. The legacy Linux-only agent integration suite also fails on macOS because it uses GNU stat. These results are not native platform acceptance.

After the snapshot change, the Magpie suite passed 120 tests; the public-bootstrap snapshot cleanup regression also passed separately. The Herdr suite passed 33 tests; agent payload passed 17 tests with 4 skipped; and CodeGraph passed 9 tests with 2 skipped. ShellCheck, shell syntax and git diff whitespace checks passed. Both legacy simulated applies passed again with the offline skill fixture. The native macOS aarch64 workstation gate timed out during the first installation after 180 seconds; its report is `/tmp/dotfiles-review-macos-2026-11-17.json`. Native Windows execution and the headless Linux native gate remain unavailable locally.

An empty-cache macOS gate passed at commit `0853046`. Commit `a66fa10` bounds
the synthetic gate's Pixi concurrency; 17 focused common-installer and
macOS-verifier tests passed.

A fresh empty-cache macOS aarch64 workstation gate passed at commit `c694c67`
in 2459.921 seconds. The source SHA-256 was
`83b25d364313a816c6dc0dfeb4eb3618ca23dc86d48d1f59c1f8878fd52088e6`;
a post-run comparison matched the commit and source fingerprint before this
tracker update. Its report is `/tmp/dotfiles-macos-gate.mt6Fkj/report.json`.
The four required behavior suites ran 13, 18, 9, and 9 tests with no skips.
The gate excludes the account gateway and currently checks DSH/TUI versions,
not headless adapter compatibility or actual routing. The pinned incompatibility
is tracked in [issue 08](08-auxiliary-models.md). Subsequent commit `f3ff964`
changes DSH documentation only; `f94c12a` changes the macOS verifier to report
adapter validation separately; `ca8fe17` adds the Linux counterpart and shared
classifier; `ba1afbe` records macOS CLI release pins and updates the catalog
validators; `1db9204` and `43d580b` correct proxy preservation; `4768720` adds
the app-absent macOS CLI fallback using fake-payload tests; and `dc3badf`
prevents provider keys reaching process arguments on macOS. The final synthetic
Magpie suite passed 280 tests, and both offline legacy profiles applied with
regular gateway/proxy launchers. These commits are outside the recorded native
fingerprint, so the complete gate has not run on the current source. Native
Linux and Windows acceptance remain unrun.

The macOS gate at `dc3badf` was stopped during its first installation when the
requested scope changed; its report at `/tmp/dotfiles-macos-gate.liLtaz/report.json`
remains marked running and is not a pass. DSH, DSH TUI, and Windows deployment
are deferred. Commits `7cfe335`, `a0b374a`, and `a6edf41` add the scoped
macOS gate and preserve/report an excluded DSH selection. The macOS verifier
suite passed 16 tests, the Magpie suite passed 225 tests before the status
change, and four focused status/selection tests passed afterward. The next
macOS gate must cover the final selected agent set and current source. The
scoped gate started after `a6edf41` was stopped during its first installation
when review found that the requested 6.1 fallback was absent from the model
catalog; it is not a pass. Commits `1e72449`, `a2502f5`, and `3fa295c` address
fallback resolution, missing-account preflight, and provider registration
before discovery. The resulting synthetic Magpie suite passed 238 tests. The
next native gate is scoped to the seven requested agents and excludes Magpie.
A broad Herdr test discovery was stopped after its 120-second timeout; it did
not produce a completed result and is not included in the passing checks.

The scoped native macOS aarch64 workstation gate passed at commit
`3fa295c00a8f0467b4a40079ab91c96711f9aed8` with an empty installation cache.
Report: `/tmp/dotfiles-macos-scoped.urHvxx/report.json`. Its source SHA-256,
`72a7c9dde5b14e658e8b919808022539fa6a0ecac18e8d299018968d302b413a`,
matched the source fingerprint and HEAD immediately after the run, before this
tracker update. The selected agents were kimi, pi, opencode, claude, codex,
minimax, and qoder; DSH was not selected. Shell, payload, CodeGraph, and
history suites ran 13, 18, 9, and 9 tests respectively, all without skips.
The synthetic gate excluded account gateway wiring. The existing-device
rehearsal, protected backup, drift recheck, and live gateway remain pending.
The installed Atuin reports `18.24.1`, matching the catalog pin; the device's
history and records databases both have WAL files. A safety permission check
denied copying those databases into isolated SQLite backups; no history
contents or credentials were displayed. On 2026-11-18 the user explicitly
authorized the Atuin copy. Private read-only SQLite backups of both databases
included committed WAL contents; quick checks and source/snapshot table counts
matched for each. Installed Atuin 18.24.1 successfully wrote and searched a
synthetic entry against the isolated copies with hosted sync disabled. The
private temporary directory was removed. This proves local compatibility, not
hosted sync or account activation.

A read-only Pi assessment found no existing executable procedure for staging an
existing-device rehearsal. Its proposed copy manifest and symlink handling need
review against the credential and confinement rules before use; in particular,
raw credential-bearing configuration must not be copied or disclosed. Synthetic
homes cannot exercise live Magpie gateway wiring. The assessment also identified
a native-agent launcher replacement hazard. Pi traced the native and
Bun/Homebrew paths, and isolated regressions confirmed that existing device
launchers were overwritten. The proposed launcher fix passed 26 Qoder/macOS
installer tests and four focused collision tests; the broader agent suite ran
14 tests with three skips. The fixed-source 26-test installer rerun passed.
Two Pi follow-up reviews timed out without findings; Pi's initial assessment
identified the issue. The launcher fix was committed as `d2d4a27`. The macOS gate
at `3fa295c`
does not cover the changed source and must be rerun after the fixes are
committed. A separate isolated Qoder fixture confirmed Pi's versioned-binary
symlink concern: installation followed the link and changed its device-owned
target. Commit `3931383` refuses symlinks in the Qoder release path; all eight
Qoder fixture tests passed. Commit `e52f518` adds a scoped seven-agent native
Linux verifier; 38 Linux verifier tests passed on macOS, but native Linux
acceptance remains unrun. A metadata-only inventory of the
selected names under `~/.local/bin` found regular files for kimi, pi, opencode,
claude, codex, and qoder, and no minimax entry. This does not establish who
owns any file or whether a given installation path will replace it.

- 2026-11-20: The headless Linux gate ran on this Mac for the first time:
  OrbStack 29.8.2, the pinned source exported into read-only amd64 containers
  for Ubuntu 20.04 and 24.04, four CPUs and eight GiB each. The first run
  failed on a stale check, not on the deployment: the gate asserted that a
  fresh home's Claude Code settings carry a placeholder credential, an
  expectation from the GLM-era template. The deployment migrated to Magpie,
  where the client credentials live in the gateway's own store and the client
  settings carry no credential, so the check read a file that no longer holds
  one. The check now reads the file that carries the placeholder (the Kimi
  client settings) and asserts that the Claude Code settings carry no
  credential while the gateway is absent. Committed as `e6ff25e`.
- 2026-11-20: The second run got further: the bootstrap, the managed files and
  installed pins, and the fetched skill discovery all passed on 20.04, and the
  reapplication check reported one changed managed file, `.config/git/ignore`.
  The gate's own snapshot logic does not reproduce it on that home: the file's
  content, mode and the managed listing are identical before and after a
  reapplication, and a third apply changes nothing. The check's verdict is
  therefore unexplained by the deployment's state, and the run is recorded as
  a failure rather than a pass.
