# Headless proxy

The dotfiles tree owns a loopback Mihomo instance for headless Linux, WSL, and
similar hosts. Nothing routes through it unless a command opts in.

## What is managed

| Path | Owner |
| --- | --- |
| `~/.local/share/mihomo/bin/mihomo` | bootstrap, pinned release |
| `~/.local/share/mihomo/subscription-url` | chezmoi, mode 0600, from `MIHOMO_SUBSCRIPTION_URL` |
| `~/.local/share/mihomo/profiles/config.yaml` | `refresh-profile.sh` |
| `~/.local/share/dotfiles/proxy/scripts/` | chezmoi, executable |
| `~/.config/systemd/user/mihomo.service` | chezmoi, opt-in start |
| `~/.local/bin/with-proxy`, `~/.local/bin/direct` | chezmoi |

## Install

Set the subscription URL as template data, never in git:

```bash
export MIHOMO_SUBSCRIPTION_URL='https://...'
bash bootstrap.sh --proxy
```

`--proxy` installs the pinned binary for x86-64 or ARM64, verifies its SHA-256,
and refreshes the profile. It requires a full deployment; it conflicts with
`--apply-only` and `--agents-only`. `DOTFILES_PROXY=true` is the environment
equivalent.

The pinned release is a Linux build, so the long-standing service belongs to
Linux and WSL. macOS applies none of the managed proxy payload, `--proxy`
fails there with that reason instead of installing a Linux binary, and the
Codex launcher runs directly rather than through `with-proxy`.

## The deployment proxy

The deployment has network needs of its own: manager releases, the skill
catalog and the agent packages. `deployment/proxy-policy.tsv` says which
sections reach the internet through a proxy and which do not, so the choice is
reviewed rather than implied by the order of the steps.

A section marked `yes` runs with the proxy environment set. A section marked
`no` runs without one, because its traffic is local or because the regional
mirror is the fast path. Loopback never goes through the proxy, so the local
agent daemons stay reachable.

The proxy that serves those sections is a **process, not a service**. It
starts with the first section that needs it and stops when the deployment
ends; it is not a unit and does not outlive the run. It is not the
long-standing service above.

The deployment reuses a proxy that is already answering on the usual port. If
none is, it starts its own instance with the pinned binary and a profile
whose ports it owns. A proxy client the user already runs — Clash Verge is
the common one — is detected and left alone: the deployment instance takes
another port rather than competing for the usual one.

Without a subscription there is nothing to route through, and the deployment
downloads directly.

The pin lives in `deployment/proxy/mihomo.tsv` with per-architecture URLs and
digests. Update all three together.

## Run

Without a service manager, run the supervisor under `zellij`, `tmux`, or the
container entrypoint:

```bash
~/.local/share/dotfiles/proxy/scripts/run-mihomo-supervised.sh
```

With user systemd:

```bash
systemctl --user enable --now mihomo.service
```

The supervisor applies the routing policy after every start, restarts after a
crash, and re-checks the selected node every five minutes.

## Use

```bash
with-proxy codex exec -C . "task"
direct codex exec -C . "task"
```

`with-proxy` sets upper- and lower-case HTTP/HTTPS/ALL proxy variables plus a
loopback `NO_PROXY`; `direct` removes every proxy variable. Both exec the
command, so exit status and signals pass through. Override the endpoint with
`PROXY_HTTP` and `PROXY_SOCKS`.

The routing policy follows the source project: local and China destinations go
direct, advertising domains are rejected, and everything
else uses the pinned US leaf. Loopback traffic never reaches the proxy.

## Checks

```bash
curl -sS http://127.0.0.1:9090/version
curl -sS http://127.0.0.1:9090/proxies | head
~/.local/share/dotfiles/proxy/scripts/configure-mihomo.py --check
```
