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

`deployment/installer-tools.tsv` declares command groups, installer packages,
version floors, selection and platforms. Common rows identify environments
from `common-tools.tsv` and use `common` in the bundle column. Optional casks
use their selecting bundle. The package catalog owns the exact Pixi fallback
specifications.

Most installer-provided commands carry a floor rather than an exact pin. The
installer owns its own versions and moves them on its own schedule, so the
deployment records the observed command version in its state. A common group
is accepted only when every exposure is executable and its version meets the
floor. Python also checks pip. PATH adoption resolves catalog executable
aliases together from one bin directory. Formula adoption checks `bin` and
`libexec/bin`. Bun and Node use these floors on macOS, while other platforms
retain their exact runtime checks.

Atuin is an exception: native-history migration is verified against its pinned
storage schema. Adopted and Homebrew commands must report the exact Atuin pin
in `common-tools.tsv`; older, newer, or suffixed versions use the pinned Pixi
fallback. The device installation remains intact.

Resolve common providers before merging Pixi desired state. Compatible device
commands are adopted first, followed by Homebrew. A missing, incompatible, or
failed formula falls through to its exact Pixi specification. Installed formulas
below the floor also take that fallback. Existing registry entries retain extra
aliases and dependencies. Regular launchers under `~/.local/bin` give the
selected provider PATH priority. Reapply can replace an owned launcher with its
Pixi fallback. An unrelated file at that path requires the operator to resolve
the collision.

The order has a cost the exact pins do not: an installer install writes into
the installer's prefix, and a cask writes an application bundle into
/Applications. Those writes happen only on the real account home, so a
simulated deployment can adopt compatible native commands read-only and uses
Pixi when adoption is unavailable. Foreign platform or architecture selections
use their own Pixi environments. Source-only application retains Pixi command
discovery until the macOS launchers have been provisioned.
