# Agent stack preflight

`~/.local/bin/dotfiles-agent-health` checks the dependency chain that fails
silently after a reboot or a daemon restart:

| Check | Failure it catches |
| --- | --- |
| Mihomo `127.0.0.1:9090` | proxy controller down |
| `with-proxy` egress country | node not U.S., or proxy bypassed |
| Caveman `127.0.0.1:8787` + run-file PID | gateway down or stale |
| `codex app-server daemon version` | Codex backend down |
| `herdr status` | Herdr server down |
| `codegraph --version` | MCP binary missing |

```bash
dotfiles-agent-health           # human-readable summary
dotfiles-agent-health --quiet   # failures only
dotfiles-agent-health --probe   # one paid Codex model round trip
```

The Codex session-restore hook runs the cheap checks before launching a
restored Codex. `codex-herdr`, the Herdr-scoped Codex launcher, runs them before
every Herdr launch; a stopped shared Codex daemon is a warning there because
that path uses `--no-daemon`. `--probe` is opt-in because it spends tokens and
depends on the active provider. A host without Mihomo or Caveman should skip
the script rather than weaken it.

Related: [proxy](PROXY.md), [caveman](CAVEMAN.md), [herdr](HERDR.md).
