# 23: The Linux T9K deployment is prepared, and the incremental path is recorded

Status: ready-for-agent — the preparation is done on 2026-11-20; the native
Windows gate is deferred by the operator
Blocked by: none
Related: 06 — the cross-platform verification carries the gate runs

**What to build:** the legacy remote-compute host can take the deployment, and
a host that is already partly deployed can be brought forward without a full
redeploy.

- [x] The canonical and the legacy plans agree, so the T9K profile and the
      legacy class deploy the same thing.
- [x] The deployment runs on the Linux baseline in a container, and the
      agents install there.
- [x] The incremental path is recorded for both shapes of host: a copy-mode
      home the public bootstrap owns, and a legacy symlinked home.

## The plan

`bootstrap.sh --profile linux-remote-compute --plan` and
`bootstrap.sh --class t9k --plan` produce the same plan: platform `linux`,
role `remote-compute`, mode `copy`, no bundle, no system change and no
login-shell change. The container gate compares them on every run.

## What the Linux baseline needs

- **A C++ toolchain for the native modules.** `better-sqlite3` is an optional
  dependency of the minimax and dsh packages. Its prebuilt binary needs
  glibc 2.33, and the Ubuntu 20.04 baseline carries 2.31, so the install
  falls back to a source build. The gate's container has no `make`, and the
  install script fails; the deployment continues because the dependency is
  optional. A host that wants the native module needs `make` and a C++
  compiler, or a newer glibc.
- **The qoder pin stays where a baseline host can install it.** The 1.1.94
  manifest no longer carries the Linux `amd64-baseline` archive that the
  installer's fallback uses on a host without AVX and AVX2, so the pin stays
  at 1.1.82 and the update refuses a bump that drops that archive.

## The incremental path

A host the public bootstrap already deployed is copy-mode, and the deployment
is incremental by construction: a second apply over the same home changed
nothing among 2472 files, the only difference being chezmoi's own state
database. `--plan` reports what an apply would do before it does it.

A host with the legacy symlinked home is a different shape: the public
bootstrap refuses it on purpose, because its state-root guard rejects the
home's symlinked `.local`, `.config` and similar entries, and running it
anyway would write through the links into the live tree. The path there is
the three legacy adapters, each with a check and a dry-run before its apply:

- `deployment/legacy/link-home.sh` — the symlink topology, and with a full
  pass the host bring-up (`dotfiles-host-up up`: the links, Mihomo, the Codex
  daemon and the saved-session restoration);
- `deployment/legacy/apply.sh` — the listed repo-owned executables and the
  Herdr config, with a backup per replaced target;
- `deployment/legacy/agent-integrations.sh` — the global skill, instruction and
  integration policy, with its own recovery batches.

The legacy history is migrated separately, because the notebook's Ceph mount
cannot hold Atuin's SQLite WAL:
`deployment/legacy/local-history.py --home "$HOME" --live-root /t9k/mnt/joey/SHELL migrate`.

## Deferred

The native Windows gate is deferred by the operator on 2026-11-20: this host
has no Windows runtime and no PowerShell, so that acceptance stays unrun.

## The code review of the two paths (2026-11-20)

Standards: the repository's own rules (AGENTS.md, docs/DEPLOYMENT_BOUNDARY.md,
docs/MACOS_DEPLOYMENT.md) read against the Linux code.

- The step order is explicit and platform-scoped. The managers, the source
  application, the installer tools, the common tools, the agents, the gateway
  step and the shell preparation run in that order, and the gateway step is
  inserted between the agents and the shell, so the gateway, the agents and
  the client settings all exist before anything is wired. The gateway step is
  off on native Windows and under `--apply-only` and `--agents-only`, and the
  reason is printed when it is skipped.
- The proxy is Linux/WSL only and is pinned with a digest; the install is
  atomic and idempotent — an installed binary that reports the pinned
  version is kept, and a cached archive is reused only when its digest
  matches. **Not covered by the container gate**, which runs without a proxy:
  the evidence is the catalog and the digest check, not a container run.
- The agents keep their ownership rules: a Bun client is a frozen project
  with its own lock, a Homebrew client is adopted and never installed, and a
  native client is a verified release. The Homebrew adoption re-resolves the
  installed path on every apply, so a client the operator upgraded by hand
  no longer leaves a launcher pointing at a removed cellar path.
- The incremental rules hold: the recorded state, the pending Codex profile
  write with its interrupted-write retry, the byte-preserving client-settings
  merge, the managed-skill inventory and its pruning are all in place, and a
  second apply over the same home changed nothing among 2472 files.

Two findings the review leaves open:

1. **A tolerated native-module failure is silent in the deployment's own
   report.** `better-sqlite3` is an optional dependency of the minimax and
   dsh packages; on the Ubuntu 20.04 baseline its prebuilt binary needs a
   newer glibc, so the install script falls back to a source build and fails
   without `make`. The dependency is optional, so the deployment continues and
   the client installs without its native module — but only Bun's own warning
   says so. The deployment's report does not mention it.
2. **The reapplication check is red on one managed file.** Something rewrites
   `~/.config/git/ignore` between two applies; the next apply restores the
   managed content, and the writer is still unidentified.
3. **A narrow apply erased the recorded state of the agents it did not
   install.** The agent state was replaced wholesale, so an install that
   covered part of the selection dropped every other agent's row, and the
   status then reported the catalog's floor instead of the version the device
   runs. The state now replaces its own rows and keeps the rest, so a narrow
   apply leaves what it did not look at alone. The bug was found on the
   device, by a `--agents kimi` update that followed a full apply.

Spec: the completion scope asks for a fresh Linux remote-compute deployment
and for an incremental path on a partly deployed host. The fresh path is
accepted by the container gate on both Ubuntu releases (bootstrap, managed
files and pins, the fetched skill discovery, and the pinned native Magpie
CLI), and the incremental path is accepted by the same gate's reapplication
check except for the finding above. The account gateway is excluded from the
gate by construction — synthetic homes have no operator accounts — so the
gateway wiring on a real account is verified on the device instead.
