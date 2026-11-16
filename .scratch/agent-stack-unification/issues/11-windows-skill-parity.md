# 11: Native Windows parity for skill selection and agent state

**What to build:** The native Windows adapter consumes the same skill selection,
profile, and managed-inventory model as the Unix side. It builds the filtered
copy roots, prunes managed entries that leave a profile, preserves device
entries, and includes the generated Herdr skill when present. Windows performs
no Herdr installation. The adapter also writes the same
`agents.lock.tsv` state file as the POSIX side, so `dotfiles-agents status`
reports the observed provider and version from state on both platforms.

**Blocked by:** 08.

**Status:** ready-for-agent

- [ ] The Windows adapter reads the same catalog selection and profile rules; no Windows-only skill list exists.
- [ ] Filtered copy roots, pruning, and device preservation behave the same as on Unix.
- [ ] No Herdr command is invoked on Windows.
- [ ] The Windows adapter writes the same `agents.lock.tsv` state rows as the POSIX side.
- [ ] The Windows deployment tests cover selection, prune safety, device preservation, and the state file.
- [ ] The shared catalog remains the single source for both adapters.
