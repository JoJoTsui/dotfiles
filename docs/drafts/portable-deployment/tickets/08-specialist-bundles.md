# 08: Install selectable specialist tool bundles

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A user adds a requested bioinformatics, GPU, or desktop
bundle to the common deployment, or receives a clear unsupported-target error.
The existing specialist inventory remains owned and discoverable without
forcing every new device to install it.

**Blocked by:** 02 — Install common tools through managed installers.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] Classify the existing specialist inventory into selectable bundles with declared supported platforms and architectures.
- [ ] No specialist bundle is installed by default for workstation or remote compute; requested combinations add their declared tools without duplicating common commands.
- [ ] Invalid bundle names and unsupported target combinations fail clearly before a partial requested bundle is installed.
- [ ] Selecting a supported bundle yields exposed usable commands and corresponding required configuration; configuration does not reference an unmanaged required binary.
- [ ] Package versions follow the common pin/update policy, and tool-specific host prerequisites are distinguished from user-scoped package installation.
- [ ] Reapplication preserves unrelated installations and selecting fewer bundles does not silently uninstall previously installed tools.
- [ ] Resolution checks cover all declared bundle targets, and native diagnostics cover supported representative installs with network-dependent outcomes reported separately.
