# Ticket 05 verification

Local Linux x86-64 public bootstrap checks used Chezmoi 2.72.2 and Python
3.13.16, with a fresh disposable home for every test. Read-only installed
clients were the ticket 04 pins: Codex 0.162.1, Claude Code 2.1.296, Kimi Code
2.1.1, Pi 1.2.0, and OpenCode 2.0.27, using Node 24.21.0.

The copy/preservation/isolation and literal-rendering tests were red before
their implementation. They then verified the 105/847 snapshot, nine executable
resources, explicit-only metadata, real files, repeated application, preserved
custom instructions/skills and synthetic authentication/trust state, rejected
nested symlink escapes, and uninterpreted `run_*` / `.tmpl` resources.

Pinned-client diagnostics sent no model prompt or authentication request:

- Codex assembled the managed global instructions and automatic skill catalog;
  explicit-only `implement-spec` remained absent from automatic discovery.
- Pi's public resource loader found 105 skills, 24 explicit-only, and the
  managed global instructions.
- Claude's SDK initialize response advertised all 105 user skills; built-in
  commands remained separate.
- Kimi's ACP initialize/new-session response advertised the 105 portable skill
  commands, including explicit-only commands. Only synthetic local session
  state was created.
- OpenCode's loopback API found 105 owned and two built-in skills after
  asynchronous discovery; `implement-spec` had `autoinvoke: false`.

All nine payload/discovery tests passed in 19.481 seconds with the actual pinned
clients. Secrets used by rendering tests were synthetic. No live-home
deployment, skill helper execution, real account access, history import,
repository index, or agent model request occurred. macOS/WSL/native Windows
execution is pending their downstream gates; Linux rendering alone is not
native execution.
