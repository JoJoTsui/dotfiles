---
status: accepted
---

# Give every pinned version one owner

A bootstrap manager is fetched from a pinned upstream release and verified
before it runs. The version alone does not identify that artifact: the release
bytes differ per target and per rebuild, so the version and its per-target
SHA-256 digests are one value. A version bump that moves only the version
leaves the digests pointing at the previous release, and every install of that
manager then fails digest verification on every platform.

The same drift appears whenever a second place repeats a version. The history
importer verifies the storage layout of one Atuin release, so it repeats that
version in its own source; when the catalog moved to a newer Atuin, the
importer kept the old version and every history migration refused to run.

Each pinned version therefore has exactly one owner. The catalog owns the
version, the digests belong to the same owner as the version they verify, and
any other place that needs the version reads it from that owner instead of
copying it. This replaces treating a version constant, a digest table, and a
runtime version check as independent catalogs that may drift apart silently.

An installer that owns its own versions is not a pinned owner. Homebrew moves
its formula catalog on its own schedule, so a version pinned here would say
nothing about what the device installs. The installer catalog therefore states
a minimum version, and the deployment records the version the installer
actually provides; see the [installer order](0008-installer-order.md).
