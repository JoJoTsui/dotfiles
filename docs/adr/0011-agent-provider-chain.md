---
status: accepted
---

# Install coding agents through a per-agent provider chain

Coding agents were installed by six frozen Bun projects, one pinned native
release, and one exact-match Homebrew exception for Codex. That mix made the
same question — "which installer owns this agent?" — depend on the agent's name
rather than on the platform, and the resulting PATH order put every Bun launcher
ahead of the Homebrew package on the same Mac. Verified on one device: `kimi`
2.4.1 from Bun shadowed Homebrew 2.6.2, and `opencode` 2.2.5 shadowed 2.3.0.

Agents are now declared in one provider catalog. Each row names one agent, one
provider, the provider's package or release, its version policy, the commands it
exposes, the platforms it serves, and its order. The per-platform order is
Homebrew, then Bun on macOS; Bun alone on Linux, WSL, and native Windows; a
pinned native release stays only where Bun cannot ship the client. This applies
the installer order from ADR 0008 to agents instead of keeping a separate
ownership rule per client.

The plan reports the provider the chain selects, and that entry describes only
that provider: a Homebrew entry names its package and package kind, a Bun
entry names its package, minimum Node, and lock, and a native entry names its
release manifest. The deployment-owned project stays visible as an explicit
fallback field, so an installer-owned entry never carries a deployment-owned
lock.

The version policy follows ownership. A provider the deployment installs — a
frozen Bun project or a verified native release — keeps an exact pin and its
lock or manifest. A provider the device's installer owns carries a floor, and
the deployment records the observed version, as it already does for common
Homebrew formulas. Homebrew moves on its own schedule; demanding an exact match
would reinstall or uninstall an agent after every `brew upgrade`. The Codex
exact-match exception from ADR 0009 becomes the first floor, not a code path.

Both managed launchers (`~/.bun/bin` and `~/.local/bin`) point at the selected
provider's executable and are revalidated on every deployment, because an
installer can update or remove its copy independently. The frozen Bun project
stays on disk as the offline fallback; switching back is a reapply, not a
reinstall. A device-owned `agent` version entry still forces a
deployment-owned install, since a floating installer cannot promise an exact
version.

PATH precedence becomes per-platform. macOS resolves `~/.local/bin` before
`$BUN_INSTALL/bin`, so a launcher for a Homebrew-adopted agent wins; other
platforms keep the Bun-first order because Bun is the agent provider there. The
shared path model in `.chezmoidata.toml` owns the order, and both shell adapters
render it. Bun and Node remain common tools rather than conditional
dependencies.

Consequences: the macOS baseline floats within the catalog floors, so a fresh
Mac and an updated Mac can run different agent builds; `dotfiles-agents status`
reports the effective provider and version rather than only a pin comparison.
A Homebrew package below its floor falls through to the Bun fallback until the
formula or cask catches up. Homebrew itself is still adopted, never installed.
