#!/usr/bin/env python3
"""Apply the routing policy to a Mihomo Profile.

The Profile keeps the provider's nodes and groups (already narrowed to US
leaves by ``restrict-proxy-groups.py``), but its rule set is replaced by one
policy:

  - local addresses (loopback, private, link-local) go DIRECT
  - China destinations go DIRECT
  - advertising domains are rejected
  - everything else goes to Mihomo's ``GLOBAL`` selector, which startup pins
    to the lowest-latency US leaf

Domain rules come from the Loyalsoldier clash-rules sets, the same sources a
Clash Verge merge template uses: the set names, behaviours and ordering match
that template, with ``PROXY`` mapped to ``GLOBAL`` and the catch-all mapped
from ``DIRECT`` to ``GLOBAL``.

Idempotent: the rules and rule-providers blocks are replaced wholesale, so
re-running is a no-op.

    ./scripts/apply-us-routing-policy.py                # default profile
    ./scripts/apply-us-routing-policy.py /path/config.yaml
"""

import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# Same default install root as the shell scripts; overridable via INSTALL_ROOT.
DEFAULT_INSTALL_ROOT = os.environ.get("INSTALL_ROOT") or os.path.expanduser(
    "~/.local/share/mihomo"
)

# Local destinations that must not be proxied. Loopback carries the local
# MCP and API services; the private and link-local ranges carry container
# and LAN services.
LOCAL_RULES = (
    "DOMAIN,localhost,DIRECT",
    "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
    "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,169.254.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,224.0.0.0/4,DIRECT,no-resolve",
    "IP-CIDR6,::1/128,DIRECT,no-resolve",
    "IP-CIDR6,fc00::/7,DIRECT,no-resolve",
    "IP-CIDR6,fe80::/10,DIRECT,no-resolve",
)

# Rule sets, as (name, behavior, target). Sources are the Loyalsoldier
# clash-rules release, the same lists a Clash Verge merge template pulls in.
# The order is the template's order: local applications, private names,
# advertising, then the sets that decide where a destination leaves from.
RULE_SETS = (
    ("applications", "classical", "DIRECT"),
    ("private", "domain", "DIRECT"),
    ("reject", "domain", "REJECT"),
    ("icloud", "domain", "GLOBAL"),
    ("apple", "domain", "GLOBAL"),
    ("google", "domain", "GLOBAL"),
    ("gfw", "domain", "GLOBAL"),
    ("tld-not-cn", "domain", "GLOBAL"),
    ("telegramcidr", "ipcidr", "GLOBAL"),
    ("proxy", "domain", "GLOBAL"),
    ("direct", "domain", "DIRECT"),
    ("lancidr", "ipcidr", "DIRECT"),
    ("cncidr", "ipcidr", "DIRECT"),
)
PROVIDER_BASE_URL = "https://raw.githubusercontent.com/Loyalsoldier/clash-rules/release"
PROVIDER_INTERVAL = 86400

# Rules that consume the sets above, plus the IP-based China rules.
IP_RULES = (
    "GEOIP,LAN,DIRECT",
    "GEOIP,CN,DIRECT",
)

# Everything else leaves through the US leaf selected into GLOBAL.
MATCH_RULE = "MATCH,GLOBAL"


def provider_host() -> str:
    return urlparse(PROVIDER_BASE_URL).hostname or ""


def provider_rules() -> list[str]:
    """Rules that keep rule-set downloads off the proxy.

    Mihomo fetches rule providers through its own routing rules, so a set
    whose host the pinned US node cannot reach never updates. Routing the
    source host DIRECT makes every update work regardless of node health.
    """
    host = provider_host()
    return [f"DOMAIN,{host},DIRECT"] if host else []


def policy_rules() -> list[str]:
    return [
        *LOCAL_RULES,
        *provider_rules(),
        *(f"RULE-SET,{name},{target}" for name, _, target in RULE_SETS),
        *IP_RULES,
        MATCH_RULE,
    ]


def render_providers() -> list[str]:
    lines = ["rule-providers:\n"]
    for name, behavior, _ in RULE_SETS:
        lines.extend(
            [
                f"    {name}:\n",
                "        type: http\n",
                f"        behavior: {behavior}\n",
                f'        url: "{PROVIDER_BASE_URL}/{name}.txt"\n',
                f"        path: ./ruleset/{name}.yaml\n",
                f"        interval: {PROVIDER_INTERVAL}\n",
            ]
        )
    return lines


def find_block(lines: list[str], key: str) -> tuple[int, int] | None:
    """Return the (start, end) line indexes of a top-level ``key:`` block.

    ``start`` is the line of the key itself, ``end`` the first line of the
    next top-level key (or the end of the file).
    """
    start = None
    for index, line in enumerate(lines):
        if line.rstrip("\n") == f"{key}:":
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line[0].isspace():
            end = index
            break
    return start, end


def render(rules: list[str]) -> list[str]:
    return [f"    - '{rule}'\n" for rule in rules]


def write_atomic(path: Path, text: str) -> None:
    mode = path.stat().st_mode & 0o777
    handle = tempfile.NamedTemporaryFile(
        "w", dir=str(path.parent), prefix=f".{path.name}.", delete=False
    )
    try:
        with handle as file:
            file.write(text)
        os.chmod(handle.name, mode)
        os.replace(handle.name, path)
    except BaseException:
        os.unlink(handle.name)
        raise


def main() -> int:
    profile = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(DEFAULT_INSTALL_ROOT) / "profiles" / "config.yaml"
    )
    if not profile.is_file():
        print(f"profile not found: {profile}", file=sys.stderr)
        return 1

    lines = profile.read_text().splitlines(keepends=True)

    # Drop a rule-providers block left by an earlier run.
    providers_block = find_block(lines, "rule-providers")
    if providers_block is not None:
        start, end = providers_block
        lines = lines[:start] + lines[end:]

    rules_block = find_block(lines, "rules")
    if rules_block is None:
        print("profile has no rules: block", file=sys.stderr)
        return 1
    rules_start, rules_end = rules_block
    old_count = sum(1 for line in lines[rules_start + 1 : rules_end] if line.strip())

    rules = policy_rules()
    lines = (
        lines[:rules_start]
        + render_providers()
        + lines[rules_start : rules_start + 1]
        + render(rules)
        + lines[rules_end:]
    )
    write_atomic(profile, "".join(lines))

    print(f"rewrote rules in {profile}: {old_count} -> {len(rules)}")
    print(f"  local bypass: {len(LOCAL_RULES)} rules -> DIRECT")
    print(f"  rule sets:    {', '.join(name for name, _, _ in RULE_SETS)}")
    print(f"  all other traffic -> {MATCH_RULE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
