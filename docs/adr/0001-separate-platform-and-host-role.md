---
status: accepted
---

# Separate platform and host role

The existing host classes mix an operating environment with the T9K deployment
context. Deployment profiles will select platform (Linux, macOS, WSL, or native
Windows) independently from host role (workstation or remote compute), with
presets for common combinations. This keeps platform-specific paths and package
support separate from role-specific behavior as more host types are added.

Platform detection is automatic unless explicitly overridden. Host role is
explicit, falling back to workstation; an SSH session does not select a compute
role. The legacy `t9k` class remains a compatibility alias for Linux remote
compute, and the current host's documented preset selects remote compute.
