#!/usr/bin/env python3
"""Apply Mihomo startup preferences via the controller API.

Reads defaults from config/startup.env, then:
  1. Sets the operation mode (rule / global / direct) and the IPv6 dial
     setting via PATCH /configs.
  2. If MIHOMO_PREFER_REGION is set, probes nodes matching that region in the
     selector group named by MIHOMO_PREFER_SELECTOR and pins the lowest-delay
     one into it via PUT /proxies/{group}.

With --check, the selected node is probed first and the full search runs only
when it no longer answers. The supervisor calls that on a timer: a node can
die without Mihomo restarting, and every request would fail until the next
restart.

Idempotent. Safe to re-run after Mihomo restarts (which loses in-memory state).
"""

import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = REPO_ROOT / "config" / "startup.env"

REGION_PATTERNS = {
    "us": re.compile(r"🇺🇸|美国|^US|United States|America", re.IGNORECASE),
}

STRUCTURAL_NODES = {"DIRECT", "REJECT", "GLOBAL"}


def load_defaults(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def http(method: str, base: str, path: str, payload=None, timeout: float = 10.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return json.loads(body) if body else None


def prime_rule_sets(base: str) -> None:
    """Re-fetch rule sets that loaded empty.

    Mihomo pulls rule providers while it starts, and that first pull can fail
    when the resolver is not ready yet. An empty set matches nothing, so its
    rules stay inert until the next scheduled refresh -- a day away. Re-fetch
    the empty ones once, after startup has settled.
    """
    try:
        providers = http("GET", base, "/providers/rules") or {}
    except Exception:
        return
    for name, info in providers.get("providers", {}).items():
        if info.get("ruleCount"):
            continue
        print(f"rule set {name} is empty; re-fetching")
        encoded = urllib.parse.quote(name, safe="")
        try:
            http("PUT", base, f"/providers/rules/{encoded}", timeout=60.0)
        except Exception as error:
            print(f"rule set {name} could not be fetched: {error}", file=sys.stderr)


def probe_delay(base: str, name: str) -> int | None:
    """Round-trip delay of a proxy node in ms, or None when it does not answer."""
    encoded = urllib.parse.quote(name, safe="")
    try:
        r = http(
            "GET", base,
            f"/proxies/{encoded}/delay?timeout=4000&url=http://www.gstatic.com/generate_204",
            timeout=6.0,
        )
        delay = r.get("delay") if r else None
        return delay if isinstance(delay, int) else None
    except Exception:
        return None


def load_exit_ip():
    """The exit-IP fetch from test-proxy.py, so both scripts use one implementation."""
    path = Path(__file__).with_name("test-proxy.py")
    spec = importlib.util.spec_from_file_location("test_proxy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_exit_ip


GET_EXIT_IP = load_exit_ip()


def route_health(proxy_url: str) -> tuple[bool, str]:
    """(reachable, exit IP) for a request made through the proxy.

    The controller's delay probe is not a health signal: some nodes answer
    the probe URL and still fail every real request, and some working nodes
    cannot reach the probe URL at all.
    """
    if not proxy_url:
        return False, ""
    try:
        ip = GET_EXIT_IP(proxy_url)
    except Exception:
        return False, ""
    return bool(ip), ip or ""


def pin_node(base: str, selector: str, name: str) -> None:
    encoded = urllib.parse.quote(selector, safe="")
    http("PUT", base, f"/proxies/{encoded}", {"name": name})


def wait_for_controller(base: str, deadline_s: float = 15.0) -> None:
    deadline = time.monotonic() + deadline_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            http("GET", base, "/version", timeout=1.0)
            return
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    raise SystemExit(f"controller not reachable at {base}: {last_err}")


def main() -> int:
    env_path = Path(os.environ.get("STARTUP_ENV", DEFAULT_ENV_FILE))
    load_defaults(env_path)
    check_only = "--check" in sys.argv[1:]

    base = os.environ.get("MIHOMO_CONTROLLER", "http://127.0.0.1:9090")
    mode = os.environ.get("MIHOMO_MODE", "rule")
    ipv6 = os.environ.get("MIHOMO_IPV6", "true").strip().lower() not in ("0", "false", "no")
    proxy_url = os.environ.get("PROXY_HTTP", "http://127.0.0.1:7890")
    region = os.environ.get("MIHOMO_PREFER_REGION", "").strip()
    selector = os.environ.get("MIHOMO_PREFER_SELECTOR", "GLOBAL").strip()

    if mode not in ("rule", "global", "direct"):
        print(f"invalid MIHOMO_MODE: {mode}", file=sys.stderr)
        return 1

    wait_for_controller(base)
    print(f"setting mode: {mode}, ipv6: {ipv6}")
    http("PATCH", base, "/configs", {"mode": mode, "ipv6": ipv6})

    # Rule sets are pulled by Mihomo itself while it starts. Re-fetching an
    # empty one here would race that pull, so it waits for the periodic check.
    if check_only:
        prime_rule_sets(base)

    if not region:
        print("MIHOMO_PREFER_REGION not set; skipping node selection")
        return 0

    if region not in REGION_PATTERNS:
        print(f"unsupported region: {region}", file=sys.stderr)
        return 1

    proxies = http("GET", base, "/proxies")["proxies"]
    if selector not in proxies:
        print(f"selector {selector!r} not found in profile", file=sys.stderr)
        return 1

    members = proxies[selector].get("all", [])
    pattern = REGION_PATTERNS[region]
    candidates = [n for n in members if pattern.search(n) and n not in STRUCTURAL_NODES]

    if not candidates:
        print(f"no {region} nodes in {selector}; leaving selector unchanged")
        return 0

    current = proxies[selector].get("now")
    if check_only:
        ok, ip = route_health(proxy_url)
        if ok:
            print(f"route is healthy through {current}: exit {ip}")
            return 0
        print("route is not serving traffic; looking for a working node")

    print(f"testing {len(candidates)} {region} nodes in {selector} through the proxy...")
    working: list[tuple[int, str]] = []
    for name in candidates:
        pin_node(base, selector, name)
        time.sleep(0.4)
        started = time.monotonic()
        ok, ip = route_health(proxy_url)
        if not ok and not working:
            # The first candidates can fail while the proxy is still warming up.
            time.sleep(1.5)
            ok, ip = route_health(proxy_url)
        if ok:
            elapsed = int((time.monotonic() - started) * 1000)
            print(f"  {elapsed:>5} ms  {name}  exit {ip}")
            working.append((elapsed, name))
        else:
            print(f"  no exit    {name}")

    if not working:
        print("no node served traffic through the proxy; leaving selector unchanged")
        return 1 if check_only else 0

    elapsed, name = min(working)
    print(f"selecting {name} ({elapsed} ms) into {selector}")
    pin_node(base, selector, name)
    return 0


if __name__ == "__main__":
    sys.exit(main())