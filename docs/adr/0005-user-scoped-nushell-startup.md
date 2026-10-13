---
status: accepted
---

# Prefer Nushell through user-scoped launchers

Managed interactive launchers will prefer Nushell while Bash and Zsh remain
available for direct use, scripts, and agent subprocesses. Bootstrap is
user-scoped by default: changing an account's login shell or system-wide
configuration requires an explicit option. This keeps the preferred interactive
shell separate from the POSIX shell behavior that existing jobs and agents
depend on, and prevents a simulated home from authorizing changes to `/etc`.
