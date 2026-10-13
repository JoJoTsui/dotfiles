# 01: Resolve and apply an isolated Linux deployment

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A Linux user can select a deployment profile, inspect the
resulting plan, and apply the working source state to an explicitly designated
home without an ordinary deployment changing account or system configuration.
This is the first verifiable deployment slice and establishes the top-level
boundary reused by later slices.

**Blocked by:** None (can start immediately).

**Status:** Resolved in the local ticket tracker; isolated deployment foundation implemented and verified.

- [x] Platform and host role are independent selectors; platform detection is automatic, role falls back to workstation, and explicit selections override detection.
- [x] The legacy T9K selection resolves to Linux remote compute, and invalid or conflicting selections produce an explanatory nonzero result.
- [x] Workstation and remote compute selections produce the appropriate Linux target state in copy mode from the working source tree.
- [x] Planning exposes selected tools/actions and target settings without applying, installing, logging in, importing history, or indexing projects.
- [x] Ordinary deployment is user-scoped; system configuration and login-shell changes require explicit options and are absent from simulated runs.
- [x] Disposable-home checks isolate XDG and package-manager state and exercise application and reapplication without real-home or system writes.
- [x] Documentation stays excluded from targets, credentials are not sourced from the real home, and required files are regular files.
- [x] External behavior tests cover selection, precedence, idempotence, failure status, and the isolation boundary rather than internal helpers.

## Implementation and evidence

Public boundary: `bash bootstrap.sh --plan`, `--home`, `--source`, `--platform`,
`--role`, `--profile`, `--class`, `--arch`, `--apply-only`, `--system-config`,
and `--login-shell`. Plans are JSON.
The boundary uses Bash 3.2-compatible syntax and actual working-tree chezmoi
application with explicit destination/config/cache/state paths. Canonical
platform/role/architecture data and an observable target profile file are
deployed; legacy class metadata remains compatible.

Checks run: public-boundary acceptance tests passed with actual chezmoi
v2.72.2 supplied from an isolated tool directory. They include all 14 accepted
profile/architecture plans, controlled platform detection, both Linux role
applications and reapplications, uncommitted source, copy-mode/executable
targets, placeholder credentials, bookkeeping exclusion, isolated state roots,
symlink refusal, named required failures, and explicit-action plan metadata.
Simulated homes are rejected before either opt-in action can run. ShellCheck
and `git diff --check` passed. No real-home apply, account operation,
existing-history read/import, user-project indexing, or system configuration
action was performed.

Extension contract: [deployment boundary](../../../DEPLOYMENT_BOUNDARY.md).
`deployment/installers.sh` declares plan arrays and functions
`install_managers`, `install_common`, `install_agents`, and `prepare_shell`.
Sourcing remains free of external side effects. Tickets 02/04 replace the
explicit pending common/agent installer failures; `--apply-only` is already
usable. This evidence establishes Linux file application and deterministic
planning, not network installation or native foreign execution. Bootstrap
offers system configuration and login-shell actions only through explicit
options; simulated runs reject them before state creation.
