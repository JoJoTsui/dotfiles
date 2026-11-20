# 07: Default Magpie on headless platforms

## Outcome

Full default deployment provides Magpie on macOS, Linux/WSL, and native Windows,
and uses the same repository-owned provider, group, visibility, and agent
wiring intent. Linux and Windows use a pinned, digest-verified CLI. macOS
adopts its device-owned app or, since `4768720`, installs the pinned native CLI
when the app is absent. The pinned upstream release publishes macOS x86_64 and
ARM64 CLI assets, but a request to download and execute the ARM64 asset in an
isolated home was denied; do not retry or delegate around that decision. Public
GitHub release metadata identifies `magpie-cli-darwin-amd64` with SHA-256
`d939a17e93956a50bc433d1a5356a3da0d7fc960c1988c7fa2890416ba11bfaa`
and `magpie-cli-darwin-arm64` with SHA-256
`2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132`.
Only metadata was queried; neither binary was downloaded or executed. Commit
`ba1afbe` records the two macOS assets and permits their catalog rows in the
Unix and Windows validators. The fallback and installer were tested with fake
payloads, including dispatch without a test CLI override; real macOS asset
compatibility remains unverified. The synthetic Magpie suite passed 276 tests
before the subsequent provider-safety change. DSH and DSH TUI remain default
agents.

The current requested scope defers Windows, DSH, and DSH TUI deployment.
Excluding DSH from `--agents` previously left Magpie's DSH visibility,
picked models, and wiring active. The fixes below preserve them. Codex
integration is under investigation and must
preserve the device's existing configuration and login. The pinned upstream
source provides a separate `magpie.config.toml` profile, but its gateway key
handling and picker behavior remain to be verified. Commit `a0b374a` preserves
DSH gateway settings when omitted from the bootstrap selection; the synthetic
Magpie suite passed 225 tests. Commit `a6edf41` records that exclusion for
standalone status, with four focused selection and drift tests passing. Commit
`7cfe335` adds scoped selection to the macOS verifier; 16 verifier tests passed.
A fresh macOS gate and live gateway checks remain outstanding. The scoped gate
was stopped when review found that Conductor required 6.2 Sol even when 6.1
was available. A source fix now resolves the first live candidate and supplies
6.1 Sol and older GPT-6 Astra fallbacks; focused synthetic tests pass. The
older Astra is still unverified on the live account. A fresh native gate and
live gateway checks are pending. The fallback is
committed as `1e72449`. A subsequent Pi review found and a regression test
confirmed that a missing required ChatGPT account could otherwise fail after
gateway mutations; `a2502f5` moves that failure before those mutations.
The model-list fixture now reproduces the first-install ordering failure.
Commit `3fa295c` registers the credential-free provider after credential preflight
and a protected backup, checks Codex's config immediately after the command,
and then resolves models. Focused tests cover a later missing model, a failed
provider command that changes Codex, one backup, and repeat application. The
synthetic Magpie suite passed 238 tests. Two other relevant suites passed 22
installer/isolation and 25 gateway lifecycle tests; five bootstrap-isolation
checks passed; both offline simulated profiles applied. The public `linux-remote-compute` x86_64 plan with the
explicit seven-agent selection enables Magpie and includes CodeGraph without
DSH or DSH TUI; this is a plan, not native Linux acceptance. ShellCheck and
shfmt were unavailable; Bash syntax and Git whitespace checks passed. The
proxy suite passed 12 tests. Agent payload tests ran 18 with four skips, and
CodeGraph tests ran nine with two skips. The final scoped native macOS gate
passed at `3fa295c` with no behavior-suite skips; it excluded account gateway
wiring. Subsequent launcher preservation commits `d2d4a27` and `3931383`, and
the scoped Linux verifier `e52f518`, changed the source; a fresh matching macOS
gate is needed. The scoped Linux verifier passed 38 tests but has not run on a
native Linux runtime. Existing-device rehearsal and live gateway verification
remain pending.

Codex research: the pinned Magpie `v0.1.4404` source at commit
`69233d6bcfda248a17b613a199e0f2735b0a3e08` describes a profile-only mode in
[`internal/agent/codex_profile.go`](https://github.com/yetone/magpie/blob/69233d6bcfda248a17b613a199e0f2735b0a3e08/internal/agent/codex_profile.go):
plain `codex` retains its provider and `codex -p magpie` loads the Magpie
profile. The profile embeds a gateway bearer credential. In an isolated home,
Codex 0.169.0 accepted `debug prompt-input` with a valid profile and rejected a
malformed selected profile while the default invocation succeeded. An isolated
`codex exec -p magpie` sent the fixture model to an ephemeral loopback Responses
endpoint; it did not exercise real Magpie or provider access. No live picker
or inference was tested. The upstream profile tests say a native
Codex model belongs to plain `codex`, not the Magpie profile; this is separate
invocations, not a verified combined in-session picker. The profile's ownership,
collisions, backup and permissions need design before automation. On 2026-11-18
the user selected the separate profile. Codex 0.169.0 was exercised in a fresh
synthetic home using two distinct fake provider endpoints. An initial session
succeeded, but resuming its ID under the `magpie` profile returned:
`Cannot change this thread's model provider from origin to magpie on resume`.
No real sessions or providers were used. The upstream source also
describes a combined ChatGPT/Magpie route that changes the base URL; neither
integration has been applied to this device. Current upstream
[Codex integration documentation](https://usemagpie.ai/docs/codex-models)
explicitly says the ChatGPT-authenticated route places Magpie models beside
native models in `/model`, retains the login, and modifies the base Codex
configuration; its documentation also calls for restarting Codex. That is an
upstream-described behavior, not a successful test of the pinned release or
this account. The current repository deliberately preserves Codex's config
and does not run `magpie codex`; supporting the combined picker would require
a reviewed change to that boundary, a protected backup, and a separate live
transport interruption decision.

A metadata-only check on 2026-11-18 found a Magpie command on this Mac and no
existing `.codex/magpie.config.toml` or `.codex/magpie-models.json`. This is a
point-in-time collision check, not permission to replace files that appear later.
The pinned upstream CLI dispatch maps a three-argument agent command to a named
field setter; its profile tests select `scope=profile` before wiring and preserve
base Codex configuration. The setter refuses scope changes when Codex is already
connected to Magpie. Upstream profile writing can touch both the profile and model
catalog; its file permissions and collision behavior still require verification.
The pinned executable has not been exercised for this profile operation.
A further read-only Pi design assessment timed out without a result. Upstream
Codex 0.169.0 source confirms the synthetic resume failure: an explicitly selected
profile with a different provider cannot resume a thread under that new provider.
The resume picker may discover the thread across providers; `--all` widens the
working-directory filter, not provider switching. See the
[resume configuration check](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/app-server/src/config_manager.rs#L521-L594)
and [Codex resume changes](https://github.com/openai/codex/pull/59503).
The repository pins Codex 0.166.0, so the 0.169.0 result is device-version
specific. Upstream Magpie also contains session-retagging logic for its ordinary
Codex integration; its profile-specific path is separate, but scope selection
and all relevant side effects still need to be verified before device wiring.

## Current checkpoint — 2026-11-18

The evidence above is chronological; this checkpoint supersedes its earlier
statements that no asset was downloaded or that Codex is never wired.
Windows, DSH, and DSH TUI remain deferred for this task. The requested Mac
selection is `kimi,pi,opencode,claude,codex,minimax,qoder`.

- The user approved the pinned macOS ARM64 download. Its SHA-256 matched
  `2d43868faee771f4c92d8e9d9fd13a79e83bdc3752fe34271304b6da8dd5e132`.
  The task payload is `/tmp/dotfiles-magpie-cli.9rXfZ6/payload/magpie`.
  Execution was denied twice; no alternative execution path was attempted.
- The uncommitted separate-profile adapter adds Codex visibility/picks and
  `group/openai-stack` wiring while guarding both base config and auth hashes.
  It backs up the profile/catalog and auth, creates the profile privately,
  refuses unrecorded/symlinked target collisions, validates live profile
  settings, records selection exclusion, and confines interrupted-write retry
  to exact fingerprints. Ownership and rollback documentation now describe
  the narrow profile exception.
- The full synthetic suite passed **256 tests in 530.195 seconds, no skips**.
  Evidence: `/tmp/dotfiles-magpie-suite-current.log`. This followed fixture and
  assertion corrections after the earlier 17 failures. Documentation and one
  indentation-only shell correction followed the passing run; no behavioral
  source changes followed it at this checkpoint.
- All-session resume remains incomplete: a saved Magpie provider must be
  available without forcing that provider onto subscription-origin threads.
  Verify a provider-definitions-only profile against two fake endpoints in a
  fresh synthetic Codex home; omit model/provider/effort selection and preserve
  session metadata. Do not use real sessions. `codex exec resume` is not a
  substitute for interactive provider-preserving resume. The device's 0.169.0
  observations do not prove compatibility with the repository's 0.166.0 pin.
- File-preservation review still needs two concrete cases before application:
  `.codex` as a symlinked parent, and an already-recorded profile/catalog
  replaced with a hard link. The current direct-target symlink check does not
  reject either case; the pinned upstream writer can write through these
  paths. Add public apply regressions and reject them before gateway mutation.
- Pi's new bounded read-only assessment did **not start**: the approval
  classifier at `group/conductor[1m]` timed out. Further shell checks and the
  primary-source fetch were likewise blocked after the session model changed.
  Earlier Pi timeouts are not review passes. No permissions or classifier
  configuration were changed, and no blocked action was delegated around.
- No profile commit, current-source native gate, real CLI profile operation,
  live-home application, or native Linux acceptance has completed. The Atuin
  snapshot rehearsal is already complete; the remaining private device-settings
  rehearsal, protected live backup/drift recheck, and transport-preservation
  gates still apply. Do not apply until these and resume verification pass.

## Acceptance

- A plan shows the gateway enabled by default; explicit opt-out and restricted
  deployment modes do not wire clients.
- Native release versions and target digests have one repository owner. A
  missing or invalid digest fails before installation. Applying source files
  cannot overwrite an installed native binary with the macOS launcher.
- Gateway readiness precedes client migration, with pre-merge backups and an
  unchanged Codex configuration. Credentials, accounts, existing providers,
  device settings, skills, and unrelated profiles stay device-owned.
- Startup is explicit and usable on headless systems without assuming a GUI or
  a working user-systemd session. No registry entry, scheduled task, privileged
  linger, or system service is created silently. A stale PID file must not
  stop an unrelated process. A simulated home must not use or alter the real
  device gateway. Deployment-owned temporary proxy settings must not become a
  dead persistent gateway endpoint; an existing device proxy on the same port
  range is not necessarily deployment-owned. Commit `1db9204` extends the
  temporary-proxy ownership check to the macOS app. Commit `43d580b` preserves
  the current setting when no endpoint is configured or observed; the port
  probe does not establish provider connectivity.
- A fresh device can install the CLI independently of account provisioning;
  missing credentials and unavailable models are reported truthfully and do
  not produce client configurations that point at an unavailable gateway.
  Provisioning must not expose a credential in process arguments on shared
  hosts. The prior macOS adapter passed key values in CLI arguments. Commit
  `dc3badf` requires masked TUI provisioning on macOS as well as Linux/WSL;
  required, optional, existing, credential-free, and plugin-account cases pass
  synthetic tests. The complete synthetic Magpie suite passed 280 tests. The
  real TUI and provider sign-in have not been exercised.
- Verify DSH and DSH TUI startup and their actual interactive and headless model
  routes. TUI profile wiring alone is not evidence for headless automation.
- Test the public bootstrap and existing Magpie seams, including opt-outs,
  digest failure, readiness, backups, preservation, and repeated application.
  Native Linux and Windows acceptance is reported separately from foreign-host
  rendering or mock tests.

## Platform boundary

Windows remains x86_64 until its existing architecture boundary changes. The
upstream CLI has no supported Windows `daemon install`; do not assume that a
long-lived background process survives logout or reboot. The current Windows
slice installs the CLI only; it does not wire the gateway, providers,
or clients, and has not been executed under PowerShell. A source review found
that it reused a same-version binary without verifying its pinned digest, wrote
both launcher paths over existing regular files, embedded unsafe home paths in
the Windows batch launcher, and validated Magpie paths/catalogs even when
Magpie was opted out. The revised source hashes the binary before execution,
preserves unrecognized launchers, uses a relative ASCII batch path, and gates
Magpie-only preflight. Eleven static checks pass; PowerShell behavior tests
remain unrun.
The conservative collision policy also blocks a pin upgrade while the previous
binary remains in place; that upgrade path needs explicit reconciliation.
The Unix installer now hashes cached CLI bytes before execution and preserves
unrecognized destination files. Its fresh-download path also checks the pinned
version and a successful exit after digest verification, before placement.
Eight focused version tests and five installation-path tests passed with fake
payloads. The native Linux verifier checks the installed CLI's digest against
the catalog before execution and when recording evidence; 33 verifier tests
pass, but native acceptance is still pending.
The lifecycle code rejects linked PID/log paths and preserves unrecognized
regular PID and log files. An earlier fix scanned `gateway*.pid` when stopping,
which could signal a device-owned backup record naming an unrelated process.
The revised code uses only the canonical PID record. Seventeen focused lifecycle
tests passed, including unrelated backup records and a normal restart. The
253-test Magpie suite passed after the version, direct-command guard, and test
import fixes.
The installed `dsh-tui cli --help`
states that headless runs default to the `headless` profile and do not inherit
the TUI profile, so the catalog's inherited TUI wiring cannot establish the
headless route. Pinned upstream Magpie source describes synchronizing newly
created empty profiles from an already-wired profile, but that reconciliation
and its timing have not been verified with the installed headless or TUI clients.
In a synthetic home, the Mac launchers report DSH `0.2.2-rc.1` and both
`dsh-tui` and `dst` `0.20.1`; the synthetic TUI profile is absent, so those
version probes do not verify profile initialization or routing. The installed
pair also fails headless discovery and its adapter version gate. Discovery is
fixed in source but the version gate remains; see
[issue 08](08-auxiliary-models.md) for the isolated reproduction.

## Evidence

The pinned Magpie CLI accepts a provider key as an argument, not as an
interactive prompt to `provider add`. A review reproduced a native apply
regression where an absent optional key-based provider incorrectly aborts the
apply. The current source preserves optional-provider semantics without passing
keys on the command line; seven focused fake-gateway tests passed for optional,
required, provisioned, and credential-free providers. The partial cross-platform
Magpie source is committed as `c694c67`; the Windows gateway and client wiring
remain incomplete and native Windows execution is unverified. Its terminal UI has a
masked key-entry
form for adding a preset; that is a possible manual provisioning path, but it
has not been exercised with a real account. The CLI's `status` probes a gateway
address, so an isolated home alone does not isolate a shared loopback port.
Bootstrap rejects a full gateway deployment for a foreign home, and the direct
`dotfiles-magpie` wrapper now guards gateway commands against a synthetic home
and a foreign platform. Six focused direct-command tests passed using fake
CLIs and an existing synthetic PID record, and the 253-test Magpie suite passed
after fixture adaptation and the test import correction. A separately invoked
Magpie CLI does not have this wrapper's guard.
Regression tests reproduced an unrelated process being killed by a stale PID
and downloads overwriting device-owned files through symlinks. Lifecycle checks
now refuse symlinked PID/log paths, the installer refuses a symlinked
destination, and retrying startup preserves an owned but unready gateway's
process record. Readiness checks require boolean `running: true` at every
reported decision point. Exact-version tests reject a longer version. A 253-test
Magpie suite passed after the compaction, installer, canonical PID,
direct-command guard, and test import corrections. After fixing optional native
providers, the full synthetic Magpie suite passed 257 tests with no skips. The
Linux verifier and Windows test modules ran 103 tests with 59 skips; Windows
PowerShell/native execution remains unverified. Native Linux acceptance,
real-account TUI provisioning, and live gateway migration remain unverified.
