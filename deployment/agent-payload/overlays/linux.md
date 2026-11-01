## Linux specifics

- Use `timeout`, `nproc`, and `free` directly when they are present.
- In-place `sed` edits take no suffix: `sed -i`.
- Prefer the host's managed tool directory when a client-bundled binary misbehaves.
