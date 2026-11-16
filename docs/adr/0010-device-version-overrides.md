---
status: accepted
---

# Let a device own the version of the components it runs

The repository catalogs own the default version of every managed component: an
agent package, a Pixi tool, an installer command. That ownership is what makes
a deployment reproducible, and it is why a version bump is a reviewed change
that moves the catalog, the lock, and the digests together.

A device still needs to run a version the catalog does not carry. A new agent
release arrives before the review lands, a tool breaks against the pinned
release, or a device needs a build that upstream published after the pin. The
answer cannot be another catalog edit: the catalog is shared by every device,
and a pin that one host needs would then be the pin every host runs.

Ownership therefore moves per device. `~/.config/dotfiles/versions.tsv` is a
device-owned manifest that names the components the device runs and the
version it runs. The repository keeps owning the default; the device owns the
named components while the entry exists.

The manifest has three kinds, one per ownership model:

- `agent|<name>|<exact version>` — a coding client, installed through its
  frozen Bun project or its verified native release. The exact version replaces
  the catalog pin, and the client's diagnostic must report it.
- `tool|<package>|<exact version>` — a Pixi-managed command. The exact version
  replaces the catalog specification when the registry is merged.
- `cli|<name>|<minimum version>` — an installer-owned command. The installer
  still owns the installed version; the override raises the floor the device
  accepts, so an older command is not adopted.

A kind is not interchangeable with another. An agent override is an exact
version because the client reports its version; a tool override is an exact
specification because Pixi installs one; a CLI override is a floor because
Homebrew moves its catalog on its own schedule.

The installer order still decides the provider. On macOS an adopted installer
command keeps the version the device installed, so a `tool` entry does not
replace it; a `cli` entry is the way to require a newer command there.

The manifest is read, never written, by the deployment. An unknown name, an
unknown kind, a malformed line, a duplicate entry, or a version outside the
accepted shape fails the deployment before any state is created. The plan
reports every effective override together with the catalog default it
replaces, so the effective version of every component is visible before an
apply.

An overridden agent keeps the frozen-install property. Its manifest and lock
are generated once into device state from the overridden version, and every
later install of that version reuses that lock. The repository lock is used
again as soon as the entry is removed, which restores the catalog default
without a second decision.

Two boundaries stay with the repository. The Atuin version is the storage
contract of one history release, and the importer reads that version from the
applied profile; a device override would leave the importer and the installed
command describing different releases, so the manifest rejects Atuin. Manager
versions are not overridable at all: a manager release is verified by its
per-target digests, and those digests move with the version in the catalog.

The native Windows adapter keeps the catalog pins for now. It is a separate
native implementation of the same boundary, and it reads no override manifest
until that adapter grows the same reader.
