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
