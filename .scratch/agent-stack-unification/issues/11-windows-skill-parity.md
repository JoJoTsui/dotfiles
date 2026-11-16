# 11: Native Windows parity for skill selection

**What to build:** The native Windows adapter consumes the same skill selection,
profile, and managed-inventory model as the Unix side. It builds the filtered
copy roots, prunes managed entries that leave a profile, preserves device
entries, and includes the generated Herdr skill when present. Windows performs
no Herdr installation.

**Blocked by:** 08.

**Status:** ready-for-agent

- [ ] The Windows adapter reads the same catalog selection and profile rules; no Windows-only skill list exists.
- [ ] Filtered copy roots, pruning, and device preservation behave the same as on Unix.
- [ ] No Herdr command is invoked on Windows.
- [ ] The Windows deployment tests cover selection, prune safety, and device preservation.
- [ ] The shared catalog remains the single source for both adapters.
