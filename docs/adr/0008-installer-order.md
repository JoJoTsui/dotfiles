---
status: accepted
---

# Resolve commands through a per-platform installer order

A command comes from an installer, and the installers differ by platform. On
macOS the order is Homebrew, then a Pixi environment, then a native release.
On Linux, WSL, and native Windows the order is a Pixi environment, then a
native release. The order applies when the device does not already provide the
command; a command the device has is adopted as it is.

Homebrew is adopted, never installed. The deployment uses the Homebrew that the
device's PATH resolves and does not install Homebrew itself: Homebrew's
bootstrap lives in a separate unpinned script, its formula catalog moves every
day, and reimplementing that bootstrap here would write outside the home and
track an upstream the deployment cannot pin. A macOS device without Homebrew
falls through to the next installer in the order, which is a Pixi environment.

What an installer owns is declared in `deployment/installer-tools.tsv`: a
command, the installer, the installer's own package kind, the lowest version
the deployment accepts, the bundle that selects it, and its platforms. The
catalog holds what the package catalog cannot provide — a desktop application,
for instance, whose native bundle only a cask can install. The package catalog
keeps owning the command-line toolchain, where an exact pin is available.

An installer-provided command carries a floor rather than an exact pin. The
installer owns its own versions and moves them on its own schedule, so the
deployment records the installed version in its state and fails when the
installed version is below the catalog's minimum. This is the counterpart of
the exact pins the Pixi environments and the managers keep.

The order has a cost the exact pins do not: an installer install writes into
the installer's prefix, and a cask writes an application bundle into
/Applications. Those writes happen only on the real account home, so a
simulated deployment reports the tier instead of performing it.
