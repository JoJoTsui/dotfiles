## macOS specifics

- Use `gtimeout` when `timeout` is absent.
- Read CPU and memory with `sysctl -n hw.ncpu` and `vm_stat`.
- In-place `sed` edits require an explicit empty suffix: `sed -i ''`.
