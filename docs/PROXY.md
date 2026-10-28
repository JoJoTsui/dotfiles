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
