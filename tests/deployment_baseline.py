"""Measure selected public bootstrap workloads in fresh disposable homes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import tempfile

from native_linux import (SOURCE, first_line_version_matches, managed_environment,
                          managed_paths, require, run, validate_paths, write_json)
from native_macos import minimal_environment, seed_package_cache, source_state


STEP = re.compile(rb"dotfiles: step ([a-z0-9.-]+) started")
FETCH = re.compile(rb"\b(?:download(?:ed|ing)|fetch(?:ed|ing))\b", re.IGNORECASE)
RETRY = re.compile(rb"\b(?:retry(?:ing)?|reattempt(?:ing)?)\b", re.IGNORECASE)
WORKLOADS = ("fresh", "reapply", "single-agent")


class Trace:
    """Timestamp complete trace lines without retaining unbounded output."""

    def __init__(self):
        self.pending = b""
        self.stages = []
        self.fetch_lines = 0
        self.retry_lines = 0

    def observe(self, chunk, seconds):
        *lines, pending = (self.pending + chunk).split(b"\n")
        self.pending = pending if len(pending) <= 8192 else b" " + pending[-8191:]
        for line in lines:
            match = STEP.fullmatch(line.rstrip(b"\r"))
            if match:
                self.stages.append((match[1].decode("ascii"), seconds))
            else:
                self.fetch_lines += bool(FETCH.search(line))
                self.retry_lines += bool(RETRY.search(line) and b"downloading tarball" not in line)

    def summarize(self, elapsed):
        endpoints = [start for _, start in self.stages[1:]] + [elapsed]
        return {
            "started_steps": [name for name, _ in self.stages],
            "seconds_before_first_step": round(self.stages[0][1], 3) if self.stages else None,
            "stage_intervals": [
                {"name": name, "seconds": round(max(0, end - start), 3)}
                for (name, start), end in zip(self.stages, endpoints)
            ],
            "traffic_observations": {
                "observed_fetch_lines": self.fetch_lines, "observed_retry_lines": self.retry_lines,
                "scope": "tool log lines only; silence does not establish zero traffic or retries",
            },
        }


def fingerprint_home(home, plan, chezmoi=None):
    paths = managed_paths(home, plan, chezmoi)
    paths.add(home / ".local/state/dotfiles/agents.lock.tsv")
    for name in (".bun/bin", ".agents/skills", ".claude/skills",
                 ".minimax/skills", "Library/Application Support/nushell", "Library/Application Support/pip"):
        paths.update((home / name).rglob("*"))
    snapshot = {}
    for path in paths:
        if path.is_file() and not path.is_symlink():
            info = path.stat()
            snapshot[path.relative_to(home)] = (
                hashlib.sha256(path.read_bytes()).hexdigest(), info.st_mode & 0o777, info.st_mtime_ns,
            )
    return snapshot


def mutations(before, after):
    shared = before.keys() & after.keys()
    return {
        "tracked_after": len(after),
        "added": len(after.keys() - before.keys()),
        "removed": len(before.keys() - after.keys()),
        "changed_content_or_mode": sum(before[path][:2] != after[path][:2] for path in shared),
        "rewritten_same_content_and_mode": sum(
            before[path][:2] == after[path][:2] and before[path][2] != after[path][2] for path in shared
        ),
    }


def sample(command, env, home, profile_plan, inventory_plan, report, label, before, timeout, chezmoi):
    result = {"status": "failed"}
    deploy_records = []
    diagnostic_records = []
    trace = Trace()
    after = before
    try:
        run(command, env=env, cwd=SOURCE, timeout=timeout,
            log=report / f"{label}-bootstrap.log", records=deploy_records, observe=trace.observe)
        observed = trace.summarize(deploy_records[0]["seconds"])["started_steps"]
        require(observed == profile_plan["steps"], "dispatch differs from the read-only plan")
        launcher = home / ".local/bin/pi"
        output = run([launcher, "--version"], env=env, cwd=SOURCE, timeout=30,
                     log=report / f"{label}-diagnostic.log", records=diagnostic_records)
        rows = (home / ".local/state/dotfiles/agents.lock.tsv").read_text().splitlines()
        agent_rows = [row.split("|") for row in rows if row.startswith("pi|")]
        require(len(agent_rows) == 1 and len(agent_rows[0]) == 4,
                "Pi does not have one recorded installation")
        _, provider, version, _floor = agent_rows[0]
        require(first_line_version_matches(output, version), "Pi did not report its recorded version")
        result["observed_agent"] = {"provider": provider, "version": version}
        result["time_to_usable_seconds"] = round(deploy_records[0]["seconds"] + diagnostic_records[0]["seconds"], 3)
        after = fingerprint_home(home, inventory_plan, chezmoi)
        result["owned_mutations"] = mutations(before, after)
        result["status"] = "passed"
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        result["failure"] = str(error)
    result["bootstrap"] = deploy_records[0] if deploy_records else None
    result["diagnostics"] = diagnostic_records[0] if diagnostic_records else None
    elapsed = deploy_records[0]["seconds"] if deploy_records else 0
    trace.observe(b"\n", elapsed)
    result.update(trace.summarize(elapsed))
    return result, after


def summarize(workloads):
    summaries = {}
    for workload, samples in workloads.items():
        comparable = [sample["time_to_usable_seconds"] for sample in samples if sample["status"] == "passed"]
        summaries[workload] = {
            "passed_samples": len(comparable),
            "median_seconds": statistics.median(comparable) if comparable else None,
            "spread_seconds": round(max(comparable) - min(comparable), 3) if comparable else None,
        }
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution", choices=("native-macos", "native-linux", "emulated-linux"), required=True)
    parser.add_argument("--report", type=Path, required=True, help="fresh directory outside the checkout")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--targeted-update", action="store_true",
                        help="measure the selected update dispatch in the single-agent workload")
    parser.add_argument("--timeout", type=int, default=1800, help="per bootstrap, in seconds")
    parser.add_argument("--cache-seed", type=Path, help="quiescent public package cache snapshot, copied per sample")
    for tool in ("chezmoi", "bun", "node"):
        parser.add_argument("--" + tool, type=Path, help="absolute executable for the toolchain-assisted scope")
    args = parser.parse_args()
    if args.samples < 1 or args.timeout < 1:
        parser.error("samples and timeout must be positive")
    tools = {"DOTFILES_CHEZMOI_BIN": args.chezmoi, "DOTFILES_BUN_BIN": args.bun, "DOTFILES_NODE_BIN": args.node}
    assisted = any(tools.values())
    if assisted and not all(path and path.is_absolute() and path.is_file() and os.access(path, os.X_OK)
                            for path in tools.values()):
        parser.error("provide absolute executable --chezmoi, --bun and --node together")
    system = platform.system()
    if (args.execution == "native-macos" and system != "Darwin"
            or args.execution.endswith("linux") and system != "Linux"):
        parser.error("execution scope does not match the OS")
    profile = "macos-workstation" if system == "Darwin" else "linux-remote-compute"
    result = {
        "schema": 1, "scope": "toolchain-assisted agents-only" if assisted else "full deployment, Pi selection",
        "execution": args.execution, "system": system, "architecture": platform.machine(),
        "profile": profile, "source": source_state(SOURCE),
        "fresh_cache": "public cache snapshot" if args.cache_seed else "empty",
        "single_agent_dispatch": "targeted update" if args.targeted_update else "agents-only",
        "workloads": {name: [] for name in WORKLOADS},
        "exclusions": ["Magpie gateway and account operations", "upstream version proposal and pin refresh"],
    }
    with tempfile.TemporaryDirectory(prefix="dotfiles-deployment-baseline-") as temporary:
        root = Path(temporary).resolve()
        validate_paths(root / "001", args.report)
        args.report.mkdir(parents=True, exist_ok=True)
        for index in range(1, args.samples + 1):
            home = root / f"{index:03}"
            if args.cache_seed:
                result["cache_seed"] = seed_package_cache(args.cache_seed, home)
            env = managed_environment(home, root)
            # Borrow no account, proxy credentials or package cache from the
            # controller. Tools still resolve within the disposable home.
            for name in tuple(env):
                if name.lower().endswith("_proxy") or name.lower().startswith("ssl_cert_"):
                    env.pop(name)
            env.update(DOTFILES_STEP_TRACE="1", DOTFILES_PIXI_CONCURRENCY="2")
            if assisted:
                env.update({key: str(path) for key, path in tools.items()})
                env["DOTFILES_SKILLS_DIR"] = str(SOURCE / "tests/fixtures/skill-library")
                if "toolchain" not in result:
                    result["toolchain"] = {
                        key: subprocess.check_output([path, "--version"], env=minimal_environment(root),
                                                     text=True, timeout=30).splitlines()[0].strip()
                        for key, path in tools.items()
                    }
            base = ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(home),
                    "--profile", profile, "--no-magpie", "--agents", "pi"]
            before = {}
            inventory_plan = None
            for workload in WORKLOADS:
                label = f"{index:03}-{workload}"
                if workload != "fresh" and result["workloads"]["fresh"][-1]["status"] != "passed":
                    result["workloads"][workload].append({"status": "not-run", "reason": "fresh setup failed"})
                    continue
                command = [*base, "--agents-only"] if assisted or workload == "single-agent" else base
                if args.targeted_update and workload == "single-agent":
                    command = [*base, "--agent-update"]
                plan = json.loads(run([*command, "--plan"], env=env, cwd=SOURCE, timeout=30,
                                      log=args.report / f"{label}-plan.json", records=[]))
                if inventory_plan is None:
                    inventory_plan = plan
                measurement, before = sample(command, env, home, plan, inventory_plan, args.report, label,
                                             before, args.timeout, args.chezmoi)
                result["workloads"][workload].append(measurement)
            result["summaries"] = summarize(result["workloads"])
            write_json(args.report / "baseline.json", result)
    print(f"Baseline report: {args.report / 'baseline.json'}")
    return int(any(sample["status"] != "passed" for samples in result["workloads"].values() for sample in samples))


if __name__ == "__main__":
    raise SystemExit(main())
