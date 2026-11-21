# 03. Unify proxy endpoint selection

**What to build:** Have Nushell and POSIX launch commands share endpoint selection and direct fallback behavior.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] Both launchers agree on precedence, supported overrides, health checks, and fallback under the same input.
- [ ] Direct fallback clears supported inherited proxy variables for the child. Proxied launch applies its environment only to the child.
- [ ] Parent environment, command arguments, and child exit status are preserved.
- [ ] Verify selection and fallback using the existing public command interfaces and a local endpoint.
