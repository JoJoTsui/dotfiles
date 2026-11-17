# 11: Native Windows parity for skill selection and agent state

**What to build:** The native Windows adapter consumes the same skill selection,
profile, and managed-inventory model as the Unix side. It builds the filtered
copy roots, prunes managed entries that leave a profile, preserves device
entries, and includes the generated Herdr skill when present. Windows performs
no Herdr installation. The adapter also writes the same
`agents.lock.tsv` state file as the POSIX side, so `dotfiles-agents status`
reports the observed provider and version from state on both platforms.

**Blocked by:** 08.

**Status:** done

- [x] The Windows adapter reads the same catalog selection and profile rules; no Windows-only skill list exists.
- [x] Filtered copy roots, pruning, and device preservation behave the same as on Unix.
- [x] No Herdr command is invoked on Windows.
- [x] The Windows adapter writes the same `agents.lock.tsv` state rows as the POSIX side.
- [x] The Windows deployment tests cover selection, prune safety, device preservation, and the state file.
- [x] The shared catalog remains the single source for both adapters.

## Comments

Implemented in `deployment/windows.ps1` with the same selection, copy-root
collision rules, managed-skill inventory, prune, generated-skill propagation,
and `agents.lock.tsv` writer as the POSIX side. `bootstrap.ps1` now deduplicates
the selectable agent names, which the provider catalog's multiple rows per
agent exposed.

Verified with PowerShell 7.6.9 on a symlink-free temporary root:
`tests/test_windows_deployment.py` ran 30 tests, OK (2 skips: the pinned Nu
renderer and the actual Windows installer, both native-runner gates). The new
tests cover the design tag, the managed inventory, the selected-to-deselected
prune, a device entry preserved in every root, a device collision preserved,
the generated Herdr skill in both copy roots, idempotent reapply, and the
agent state rows.
