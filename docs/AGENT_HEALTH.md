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
dotfiles-agent-health --codex     # Codex launch path; skips graph tools and the
                                  # legacy proxy readiness, but requires the
                                  # with-proxy executable
dotfiles-agent-health --clients   # client binaries, config paths, Herdr drift
dotfiles-agent-health --before-restore # dependencies only; Herdr can be down
dotfiles-agent-health --probe     # one paid Codex model round trip
```

`--clients` also reports the Herdr integration drift of every managed agent:
the deployment records which agent owns which Herdr kind, and the check reads
the live state from Herdr. The drift is a warning, never a failure: an
outdated integration affects restore and resume, not launch.

This is a **preflight**, not a shell-startup check. `codex-herdr` runs the
narrow `--codex` set before every Herdr Codex launch. Explicit host preparation
also runs the full dependency check before the laptop attaches to Herdr.
`--probe` is opt-in because it spends tokens and depends on the active
provider. A host without Mihomo or Caveman should skip the script rather than
weaken it.

The `--codex` set skips exactly one thing: the legacy proxy readiness (the
Mihomo controller and its U.S. egress). The launcher runs `with-proxy
--if-available`, which starts Codex direct when no endpoint answers, so a host
without the legacy proxy can still launch Codex in a pane. The set skips that
readiness only when the proxy launcher answers the option: a launcher that
always proxies — a legacy tree keeps its own `with-proxy` — depends on the
proxy stack, so the readiness stays. Everything else
stays: the Herdr server, the Codex binary, the `with-proxy` executable the
launcher itself needs, and the strict default and `--before-restore` checks
that host bring-up runs. `--before-restore` combined with `--codex` stays the
strict check, because both flags were supported together before the narrow
set existed.

Related: [proxy](PROXY.md), [caveman](CAVEMAN.md), [herdr](HERDR.md),
[host bring-up](HOST_UP.md).
