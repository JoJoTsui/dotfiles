# 01: Resolve and apply an isolated Linux deployment

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A Linux user can select a deployment profile, inspect the
resulting plan, and apply the working source state to an explicitly designated
home without an ordinary deployment changing account or system configuration.
This is the first verifiable deployment slice and establishes the top-level
boundary reused by later slices.

**Blocked by:** None (can start immediately).

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] Platform and host role are independent selectors; platform detection is automatic, role falls back to workstation, and explicit selections override detection.
- [ ] The legacy T9K selection resolves to Linux remote compute, and invalid or conflicting selections produce an explanatory nonzero result.
- [ ] Workstation and remote compute selections produce the appropriate Linux target state in copy mode from the working source tree.
- [ ] Planning exposes selected tools/actions and target settings without applying, installing, logging in, importing history, or indexing projects.
- [ ] Ordinary deployment is user-scoped; system configuration and login-shell changes require explicit options and are absent from simulated runs.
- [ ] Disposable-home checks isolate XDG and package-manager state and exercise application and reapplication without real-home or system writes.
- [ ] Documentation stays excluded from targets, credentials are not sourced from the real home, and required files are regular files.
- [ ] External behavior tests cover selection, precedence, idempotence, failure status, and the isolation boundary rather than internal helpers.
