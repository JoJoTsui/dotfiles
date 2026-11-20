# 01: Preserve device-owned generated skills

**What to build:** Generated skills reach managed copy roots without overwriting or later claiming a device-owned entry on Unix or Windows.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Differing unrecorded directories, files, and links survive and are reported on first and repeated apply.
- [ ] Successfully copied or identical adopted entries are recorded; owned copies refresh as intended.
- [ ] Behavior tests cover both adapters and inventory transitions.

## Comments

Implementation is present in the working tree. The Unix Herdr suite passed all 33 tests, including new collision, repeated-apply, adoption, and refresh cases. Windows behavior tests were added but could not be executed locally because PowerShell is unavailable. Final review and native acceptance remain outstanding.
