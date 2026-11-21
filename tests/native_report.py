"""Native verification reporting: the checkout under test and scenario outcomes.

A native verification run establishes only what it actually ran. This module
owns the two facts every native report carries: the checkout the run verified,
and the outcome of every scenario it attempted. A scenario that did not run
keeps its reason, and a runner that cannot execute natively is unavailable
rather than passed.

An adapter observes a run and writes down what it saw. It hands those facts
to this module, which turns them into the report every native verification
leaves, so the verdict has one owner instead of one per adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"
UNAVAILABLE = "unavailable"

OUTCOMES = (PASSED, FAILED, SKIPPED, UNAVAILABLE)


def checkout_identity(source) -> dict:
    """Identify the checkout a verification run verified.

    The commit, the tree it names, whether the working tree carries
    uncommitted changes, and a digest of the tracked and untracked source
    bytes. Ignored device files stay out of the digest, and the digest covers
    the content itself, not its timestamp.
    """
    source = Path(source)

    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(source), *arguments], timeout=10,
                                       stderr=subprocess.DEVNULL)

    revision = git('rev-parse', 'HEAD').decode().strip()
    tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
    dirty = bool(git('status', '--porcelain', '--untracked-files=normal'))
    digest = hashlib.sha256()
    for relative in sorted(set(git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0'))):
        if not relative:
            continue
        path = source / os.fsdecode(relative)
        digest.update(relative + b'\0')
        if path.is_symlink():
            digest.update(b'link\0' + os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(str(path.stat().st_mode & 0o777).encode() + b'\0')
            digest.update(path.read_bytes())
        else:
            digest.update(b'missing')
        digest.update(b'\0')
    return {'commit': revision, 'tree': tree, 'working_tree_dirty': dirty,
            'source_sha256': digest.hexdigest()}


def checkout_identity_or_unknown(source) -> dict:
    """The checkout identity, or an unknown identity when Git cannot answer."""
    try:
        return checkout_identity(source)
    except (OSError, subprocess.SubprocessError):
        return {"commit": "unknown", "tree": "unknown", "working_tree_dirty": None,
                "source_sha256": "unknown"}


class ScenarioLog:
    """The outcome of every scenario a verification run attempted."""

    def __init__(self):
        self._records = []

    def record(self, name, outcome, *, reason=None, seconds=None, details=None):
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown scenario outcome: {outcome}")
        # A scenario that did not establish its result says why. A silent
        # failure or an unexplained skip is not evidence.
        if outcome != PASSED and not reason:
            raise ValueError(f"a {outcome} scenario needs a reason: {name}")
        record = {"name": name, "outcome": outcome}
        if reason:
            record["reason"] = reason
        if seconds is not None:
            record["seconds"] = round(seconds, 3)
        if details is not None:
            record["details"] = details
        self._records.append(record)
        return record

    def passed(self, name, **keywords):
        return self.record(name, PASSED, **keywords)

    def failed(self, name, reason, **keywords):
        return self.record(name, FAILED, reason=reason, **keywords)

    def skipped(self, name, reason, **keywords):
        return self.record(name, SKIPPED, reason=reason, **keywords)

    def unavailable(self, name, reason, **keywords):
        return self.record(name, UNAVAILABLE, reason=reason, **keywords)

    @property
    def records(self):
        return list(self._records)

    def counts(self):
        return counts(self._records)

    def names(self):
        return [record["name"] for record in self._records]


def counts(records):
    """The number of scenarios per outcome."""
    counted = {outcome: 0 for outcome in OUTCOMES}
    for record in records:
        counted[record["outcome"]] += 1
    return counted


def status(records, *, native_execution=True):
    """The status of a verification run.

    A runner that could not execute natively establishes nothing about the
    target platform, so its status is unavailable rather than passed.
    """
    if not native_execution:
        return UNAVAILABLE
    if any(record["outcome"] == FAILED for record in records):
        return FAILED
    if any(record["outcome"] == PASSED for record in records):
        return PASSED
    return UNAVAILABLE


def acceptance(records, *, native_execution=True):
    """Whether the run establishes acceptance.

    Acceptance needs a runner that executed natively, at least one scenario
    that passed, and no scenario that failed. A skipped scenario is visible in
    the report; it does not stand in for a passed one.
    """
    if not native_execution or not records:
        return False
    if any(record["outcome"] == FAILED for record in records):
        return False
    return any(record["outcome"] == PASSED for record in records)


def summarize(records, *, native_execution=True):
    """The report section every native verification carries."""
    return {
        "status": status(records, native_execution=native_execution),
        "acceptance": acceptance(records, native_execution=native_execution),
        "counts": counts(records),
        "scenarios": list(records),
    }


def build_report(facts: dict) -> dict:
    """The native report one run leaves.

    The facts are what an adapter observed: the checkout it verified, the
    scenarios it attempted, and the fields that describe the run. The verdict
    comes from the shared rules, so every adapter reports the same way.
    """
    log = ScenarioLog()
    for record in facts.get("scenarios") or ():
        log.record(record["name"], record["outcome"], reason=record.get("reason"),
                   seconds=record.get("seconds"), details=record.get("details"))
    records = log.records
    native_execution = bool(facts.get("native_execution", True))
    report = dict(facts.get("fields") or {})
    report["checkout"] = checkout_identity_or_unknown(facts["source"])
    report["scenarios"] = records
    report.update(summarize(records, native_execution=native_execution))
    return report


def main(argv=None) -> int:
    """Assemble a native report from the facts an adapter collected."""
    parser = argparse.ArgumentParser(description="Assemble a native verification report.")
    parser.add_argument("--source", required=True, help="the checkout the run verified")
    parser.add_argument("--facts", required=True, help="the JSON facts the adapter collected")
    parser.add_argument("--output", required=True, help="the report file to write")
    arguments = parser.parse_args(argv)
    try:
        facts = json.loads(Path(arguments.facts).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"native report: the collected facts are unreadable: {error}", file=sys.stderr)
        return 1
    if not facts.get("source"):
        print("native report: the facts do not name the checkout the run verified", file=sys.stderr)
        return 1
    try:
        report = build_report(facts)
    except (KeyError, TypeError, ValueError) as error:
        print(f"native report: the collected facts are not usable: {error}", file=sys.stderr)
        return 1
    Path(arguments.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"native report: {report['status']} (acceptance: {report['acceptance']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
