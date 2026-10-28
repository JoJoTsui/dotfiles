#!/usr/bin/env python3
"""Restrict Mihomo proxy-groups to a single region.

Edits the Mihomo profile in place, narrowing every ``proxy-groups[*].proxies``
list to nodes whose name matches a region pattern. Cross-references between
groups (e.g. ``良心云`` listing ``自动选择``) and structural entries
(``DIRECT``, ``REJECT``) are preserved. ``GLOBAL`` is an implicit selector in
Mihomo and is not in the profile, so it is untouched here — the supervisor's
``configure-mihomo.py`` pins it to a region node separately.

Idempotent. Called by:

* ``refresh-profile.sh`` after the subscription YAML is written, so a fresh
  profile is narrowed before Mihomo next loads it.
* ``run-mihomo-supervised.sh`` before every supervised start, as a safety net
  in case the profile was refreshed outside the usual path.

Usage::

    ./scripts/restrict-proxy-groups.py                # default region=us
    ./scripts/restrict-proxy-groups.py us             # explicit region
    ./scripts/restrict-proxy-groups.py us /path/to/config.yaml
"""

import os
import re
import sys
from pathlib import Path

# Same pattern as configure-mihomo.py: a name is "us" if it carries a US flag,
# mentions 美国, or starts with US / United States / America.
REGION_PATTERNS: dict[str, re.Pattern[str]] = {
    "us": re.compile(r"🇺🇸|美国|^US|United States|America", re.IGNORECASE),
}

# Names that are structural (always kept verbatim in any proxies list).
STRUCTURAL: frozenset[str] = frozenset({"DIRECT", "REJECT"})

# Default install root. Matches the shell scripts; overridable via INSTALL_ROOT
# so a manual call (e.g. INSTALL_ROOT=/opt/mihomo ./scripts/restrict-proxy-groups.py us)
# still works against the historical layout.
DEFAULT_INSTALL_ROOT = os.environ.get("INSTALL_ROOT") or os.path.expanduser(
    "~/.local/share/mihomo"
)

# A proxy-group entry in the flow-style YAML emitted by the Mihomo
# subscription converter. Captured groups:
#   head  : leading indent + "name: " opener
#   qname : raw name value (possibly surrounded by ' or ")
#   mid   : ", type: <typename>, proxies: ["
#   body  : the proxies list body (zero or more items separated by ", ")
#   tail  : "] ... " (closing bracket plus any trailing fields, up to "}")
GROUP_LINE_RE = re.compile(
    r"^(?P<head>\s*-\s*\{\s*name:\s*)"
    r"(?P<qname>['\"]?[^\"',}]+['\"]?)"
    r"(?P<mid>,\s*type:\s*[A-Za-z-]+,\s*proxies:\s*\[)"
    r"(?P<body>[^\]]*)"
    r"(?P<tail>\][^}]*\})",
    re.MULTILINE,
)

# A proxy entry — used to harvest the set of node names from the proxies
# section. The ``type`` field is allowed to appear anywhere on the line
# (some types like hysteria2 emit server/port/sni before type), so we use a
# lookahead rather than a fixed position. ``type`` must be a real proxy
# type, not a stray token elsewhere in the file.
PROXY_LINE_RE = re.compile(
    r"^\s*-\s*\{\s*name:\s*(?P<qname>['\"]?[^\"',}]+['\"]?),"
    r"(?=[^{}]*\btype:\s*(?:vless|vmess|trojan|hysteria2|ss|socks|http|wireguard|tuic|anytls)\b)",
    re.MULTILINE,
)


def parse_name(raw: str) -> str:
    """Strip optional surrounding quotes from a YAML scalar name."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def split_proxies(body: str) -> list[str]:
    """Split a flow-style YAML list body into items, respecting quoted commas.

    Returns the *unquoted* form of each item so callers can compare them
    against the unquoted set of node names produced by :func:`parse_name`.
    The original quoting style (single vs double vs none) is preserved by
    :func:`join_proxies` via :func:`quote_for_flow`.
    """
    items: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in body:
        if quote is not None:
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        items.append(tail)
    out = [parse_name(x) for x in items if x]
    return out


def quote_for_flow(name: str) -> str:
    """Quote a name for emission in a flow-style YAML list if it contains
    characters that would otherwise require quoting."""
    if name in STRUCTURAL:
        return name
    needs_quote = any(c in name for c in ",:#{}[]&*?|<>=!%@`")
    if needs_quote and "'" not in name:
        return f"'{name}'"
    if "'" in name:
        return f'"{name}"'
    return name


def join_proxies(items: list[str]) -> str:
    return ", ".join(quote_for_flow(it) for it in items)


# Match a single proxy entry line (one of the top-level `proxies:` list items).
# Returns the entire line; we replace it wholesale.
PROXY_ENTRY_RE = re.compile(
    r"^[ \t]*-\s*\{[^\n]*?\}[ \t]*\n",
    re.MULTILINE,
)


def strip_non_region_proxies(text: str, region_nodes: set[str]) -> str:
    """Remove proxy entries whose name is not in ``region_nodes``.

    Walks the file and removes whole `- { ... }` lines from the ``proxies:``
    section. Leaves non-``proxies:`` content untouched (rules, dns, etc.).
    """
    out_lines: list[str] = []
    in_proxies_section = False
    proxies_indent: int | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("proxies:"):
            in_proxies_section = True
            proxies_indent = len(line) - len(stripped)
            out_lines.append(line)
            continue
        # Detect end of proxies section: a non-blank, non-comment line at or
        # below proxies_indent that doesn't start with '- {'.
        if in_proxies_section:
            indent = len(line) - len(line.lstrip())
            is_entry = stripped.startswith("- {") or stripped.startswith("-{")
            is_blank = not stripped.strip()
            if is_blank or (indent == proxies_indent and not is_entry):
                # End of proxies section when we see a non-entry line at the
                # same indent level.
                if not is_blank:
                    in_proxies_section = False
                    out_lines.append(line)
                    continue
            if is_entry:
                # Decide: keep or drop?
                name_match = re.search(r"name:\s*['\"]?([^'\",}]+)['\"]?", line)
                if name_match and name_match.group(1) in region_nodes:
                    out_lines.append(line)
                else:
                    # Drop this proxy entry entirely.
                    continue
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)
    return "".join(out_lines)


def main() -> int:
    region = (sys.argv[1] if len(sys.argv) > 1 else "us").lower()
    profile = Path(
        sys.argv[2] if len(sys.argv) > 2 else f"{DEFAULT_INSTALL_ROOT}/profiles/config.yaml"
    )

    if region not in REGION_PATTERNS:
        print(f"unsupported region: {region}", file=sys.stderr)
        return 1
    if not profile.is_file():
        print(f"profile not found: {profile}", file=sys.stderr)
        return 1

    text = profile.read_text()
    pattern = REGION_PATTERNS[region]

    # Collect node names from the proxies section. We use this to distinguish
    # "leaf node references" (filterable) from "group references" (always kept).
    all_node_names: set[str] = {
        parse_name(m.group("qname")) for m in PROXY_LINE_RE.finditer(text)
    }
    region_nodes: set[str] = {n for n in all_node_names if pattern.search(n)}
    if not region_nodes:
        print(f"no {region} nodes in profile", file=sys.stderr)
        return 1
    print(f"profile has {len(all_node_names)} nodes; {len(region_nodes)} match {region}")

    group_names_seen: list[str] = []

    def replace_group(match: re.Match[str]) -> str:
        name = parse_name(match.group("qname"))
        body = match.group("body")
        items = split_proxies(body)
        kept: list[str] = []
        for it in items:
            if it in STRUCTURAL:
                kept.append(it)
                continue
            if it in all_node_names:
                if pattern.search(it):
                    kept.append(it)
                # else: leaf node outside the region — drop it.
            else:
                # Group reference (e.g. '自动选择' inside 良心云). Keep verbatim.
                kept.append(it)
        new_body = join_proxies(kept)
        group_names_seen.append(name)
        return (
            f"{match.group('head')}{match.group('qname')}"
            f"{match.group('mid')}{new_body}{match.group('tail')}"
        )

    new_text = GROUP_LINE_RE.sub(replace_group, text)

    # Also strip non-US entries from the top-level `proxies:` list, so Mihomo's
    # implicit GLOBAL selector has only US options to choose from. This
    # hardens "no matter the mode" — even a manual PUT against /proxies/GLOBAL
    # can only select a US node.
    new_text = strip_non_region_proxies(new_text, region_nodes)

    if new_text == text:
        print("no changes needed")
        return 0

    profile.write_text(new_text)
    print(f"rewrote {profile}")
    # Report proxy counts after the rewrite.
    for g in group_names_seen:
        for m in GROUP_LINE_RE.finditer(new_text):
            if parse_name(m.group("qname")) == g:
                count = len(split_proxies(m.group("body")))
                print(f"  {g}: {count} proxies")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())