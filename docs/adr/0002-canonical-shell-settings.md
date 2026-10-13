---
status: accepted
---

# Generate shared shell values from one source

Nushell currently mirrors the POSIX environment manually, leaving differences
in managed-tool paths and Python preferences. Shared values will have one
canonical source that renders Nushell and POSIX configurations; each shell keeps
its own initialization adapter. This replaces coordinated edits to separate
copies with a common model whose rendered behavior can be checked for parity.
