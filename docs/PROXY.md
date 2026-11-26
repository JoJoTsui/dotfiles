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
Linux and WSL. macOS applies none of the managed proxy payload and `--proxy`
fails there with that reason instead of installing a Linux binary. The Codex
launcher still asks `with-proxy --if-available`, which uses whatever proxy the
device runs (Clash Verge on macOS) and otherwise starts direct.

Destination validation refuses symlinks in every proxy path the deployment
writes. The device-owned `~/.local/share/mihomo/releases/` tree is the one
exception: legacy installers keep versioned virtualenvs there, whose Python
entry points are normally symlinks. The `releases` directory itself must still
be a real directory inside the selected home.

## Refresh

The refresh fetches the subscription, converts it, validates it, and publishes
it. The replacement is staged beside the profile it replaces, so publication is
a rename on one filesystem, and the active profile is published only after
every step succeeds:

1. The destination must be a regular file. A directory would take the staged
   copy instead of being replaced, so the refresh stops before it fetches
   anything.
2. The fetch writes the subscription to a staged file.
3. The staged profile must carry `mixed-port`, `proxies`, `proxy-groups`, and
   `rules`; without them it is not a usable Mihomo configuration.
4. The US restriction and the routing policy are applied to the staged copy,
   not to the profile in use. Both transforms are required: a profile
   published without them carries the provider's own regions and rules, so a
   transform that is missing or is not executable stops the refresh.
5. The converted profile is checked again and validated with the managed
   Mihomo binary (`mihomo -t -f`), so a configuration Mihomo cannot load
   never replaces the working one.
6. The validated profile is renamed over the active one.

A failed fetch, conversion, or validation leaves the active profile exactly as
it was, so the last working profile keeps serving and a later refresh can
publish a valid replacement without provisioning again. The staged file is
removed on every exit, so a failed refresh leaves nothing behind.

The deployment passes the same managed binary to both refresh call sites: the
service refresh and the temporary deployment instance keep separate install
roots, but both validate with the release the deployment installed.

The refresh keeps its diagnostics secret-safe. The subscription URL is redacted
from a fetch error, and the validator's own message is not relayed, because a
parse error quotes the value it rejected and a profile carries proxy
credentials.

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

### US nodes

The deployment instance routes through US leaves, the same policy the
long-standing service uses. Its groups are narrowed to the US nodes and the
routing policy is applied, so local and China destinations stay direct and
everything else leaves through a US node. The instance configures itself
through a controller port of its own and pins the `GLOBAL` group to the
lowest-latency US leaf, the way the service's supervisor does.

US is a preference, not a restriction: when no US leaf serves traffic, the
helper measures the remaining nodes and pins the lowest-latency working one,
printing that it fell back. Groups are never candidates, since pinning a
selector to another group would measure that group's choice rather than a node.

The instance builds **its own** profile. The long-standing service keeps its
own profile untouched, and the deployment never overwrites it.

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
`PROXY_HTTP` and `PROXY_SOCKS`, and the bypass list with `PROXY_NO`.

The endpoint is resolved per call, not per platform. A port belongs to the
proxy process that owns it — the deployment instance uses 7890, Clash Verge
uses 7897, on every OS — so `with-proxy` probes 7897 then 7890 and falls back
to 7890 when neither answers. An explicit `PROXY_HTTP` skips the probe.
`with-proxy --print-url-if-available` instead exits unsuccessfully with no
output when no endpoint is configured or observed; use it when persisting an
endpoint, rather than persisting the ordinary fallback.
`noproxy`, in both the POSIX and the Nu adapter, asks `with-proxy` for the same
answer, so the port is never baked in at `chezmoi init` and one checkout
serves a headless host and a desktop running a different client.

### One endpoint decision

`with-proxy` owns that decision, and every shell reads it from there. The
Nushell adapter (`~/.config/nushell/proxy.nu`) and the POSIX helper
(`~/.env_core`) both ask the same launcher, so a session in Nushell and a
session in Bash route the same way.

A caller asks the launcher whether it answers `--if-available` before it uses
the option, because a launcher that does not know the option would exec it as
a command. The Codex launch wrapper does exactly that, so a legacy tree that
keeps its own `with-proxy` keeps the plain proxied route instead of failing.

| Command | Answers |
| --- | --- |
| `with-proxy cmd ...` | runs the child through the resolved endpoint |
| `with-proxy --if-available cmd ...` | runs the child directly when no endpoint is healthy |
| `direct cmd ...` | runs the child without any proxy variable |
| `with-proxy --print` | the export lines for a POSIX session |
| `with-proxy --print-env` | the same variables as `KEY=VALUE` lines |
| `with-proxy --print-url` | the endpoint, with the ordinary fallback |
| `with-proxy --print-url-if-available` | the endpoint, or nothing |

The variables the launchers own are `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`,
`https_proxy`, `ALL_PROXY`, `all_proxy`, `NO_PROXY`, `no_proxy`, and `PROXY`.
A direct launch clears those and the two FTP spellings, so a stale inherited
value cannot route a child through an endpoint that is not there. A proxied
launch applies its variables to the child only: the calling session keeps its
own environment, and the child's arguments and exit status are unchanged.

The answer is line-delimited, so the interface fixes two things. The bindings
carry fixed variable names: the launcher owns the names and the value each
name carries, so a value never chooses the name it is bound to. The supported
overrides are single-line values, and an override that carries a line
separator is refused before any binding is emitted — a second line inside a
value would otherwise be read as another variable name, both in the child's
environment and in the export lines a POSIX session evaluates. The POSIX
`noproxy` reads the launcher's answer before it evaluates it, so a refusal is
the caller's failure and the session keeps the environment it had.

In Nushell, `with-proxy`, `direct`, `noproxy`, and `unproxy` are the same four
commands. `noproxy` sets the session variables and `unproxy` clears them.
Nushell's environment is case-insensitive, so a session keeps one spelling per
variable; a launched child receives every spelling, because the shared
launcher applies them in a POSIX environment.

The routing policy follows the source project: local and China destinations go
direct, advertising domains are rejected, and everything
else uses the pinned US leaf. Loopback traffic never reaches the proxy.

The policy rewriter accepts block collections (including indentless rule lists)
and empty inline `rules: []` / `rule-providers: {}`, with optional header comments.
Nonempty or multiline flow collections, anchored or aliased headers, and
unsupported complex keys report an error and leave that file unchanged.

## Checks

```bash
curl -sS http://127.0.0.1:9090/version
curl -sS http://127.0.0.1:9090/proxies | head
~/.local/share/dotfiles/proxy/scripts/configure-mihomo.py --check
```
