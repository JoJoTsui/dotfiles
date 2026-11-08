# Agent stack preflight

`~/.local/bin/dotfiles-agent-health` checks the dependency chain that fails
silently after a reboot or a daemon restart:

| Check | Failure it catches |
| --- | --- |
| Mihomo `127.0.0.1:9090` | proxy controller down |
| `with-proxy` egress country | node not U.S., or proxy bypassed |
| Caveman `127.0.0.1:8787` + run-file PID | gateway down or stale |
| `codex app-server daemon version` | Codex backend down (warning with `--no-daemon`) |
| `herdr api snapshot` | Herdr server down |
| `codegraph --version` | MCP binary missing (full check only) |
| `graphify --help` | Graphify missing or unable to execute (full check only) |

```bash
dotfiles-agent-health             # full stack, human-readable
dotfiles-agent-health --quiet     # failures only
dotfiles-agent-health --codex     # Codex launch path; skips graph tools
dotfiles-agent-health --clients   # client binaries and config paths (diagnostic)
dotfiles-agent-health --before-restore # dependencies only; Herdr can be down
dotfiles-agent-health --probe     # one paid Codex model round trip
```

This is a **preflight**, not a shell-startup check. `codex-herdr` runs the
narrow `--codex` set before every Herdr Codex launch. Explicit host preparation
also runs the full dependency check before the laptop attaches to Herdr.
`--probe` is opt-in because it spends tokens and depends on the active
provider. A host without Mihomo or Caveman should skip the script rather than
weaken it.

Related: [proxy](PROXY.md), [caveman](CAVEMAN.md), [herdr](HERDR.md),
[host bring-up](HOST_UP.md).
