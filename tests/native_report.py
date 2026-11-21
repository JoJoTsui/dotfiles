"""Native verification reporting: the checkout under test and scenario outcomes.

A native verification run establishes only what it actually ran. This module
owns the facts every native report carries: the checkout the run verified, the
outcome of every scenario it attempted, and the verdict. A scenario that did
not run keeps its reason, and a runner that cannot execute natively is
unavailable rather than passed.

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

UNKNOWN = "unknown"
# The identity fields the verification notes declare for every native report.
IDENTITY_FIELDS = ("commit", "tree", "working_tree_dirty", "source_sha256")
# The revision states a run may claim. An unknown revision establishes
# nothing, and a revision that differs from the one the run was asked to
# verify is not the one it verified.
REVISION_VERIFIED = "verified"
REVISION_SUPPLIED = "supplied"
REVISION_MISMATCHED = "mismatched"
ACCEPTABLE_REVISIONS = (REVISION_VERIFIED, REVISION_SUPPLIED)


def git_output(source, *arguments) -> bytes:
    """A Git answer for the checkout under test."""
    return subprocess.check_output(['git', '-c', f'safe.directory={source}', '-C', str(source), *arguments],
                                   timeout=10, stderr=subprocess.DEVNULL)


def _digest(source: Path, relatives) -> str:
    """A digest of the named source files and their content."""
    digest = hashlib.sha256()
    for relative in sorted(relatives):
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
    return digest.hexdigest()


def checkout_identity(source) -> dict:
    """Identify the checkout a verification run verified.

    The commit, the tree it names, whether the working tree carries
    uncommitted changes, and a digest of the tracked and untracked source
    bytes. Ignored device files stay out of the digest, and the digest covers
    the content itself, not its timestamp.
    """
    source = Path(source)
    revision = git_output(source, 'rev-parse', 'HEAD').decode().strip()
    tree = git_output(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
    dirty = bool(git_output(source, 'status', '--porcelain', '--untracked-files=normal'))
    relatives = set(git_output(source, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0'))
    return {'commit': revision, 'tree': tree, 'working_tree_dirty': dirty,
            'source_sha256': _digest(source, relatives)}


def source_digest(source) -> str:
    """A digest of the source bytes that does not need a Git checkout.

    A transported source (a Git archive extracted on a native runner) carries
    no repository metadata, so its bytes are the only identity it can
    establish. Bytecode caches are runtime artifacts of running the checks
    rather than source, so they stay out of the digest.
    """
    source = Path(source)
    relatives = []
    for path in source.rglob('*'):
        relative = path.relative_to(source)
        if '.git' in relative.parts or '__pycache__' in relative.parts:
            continue
        if path.suffix == '.pyc':
            continue
        relatives.append(str(relative).encode())
    return _digest(source, relatives)


def establish_identity(source, expected_revision=None) -> dict:
    """The identity a verification run establishes before it starts testing.

    A Git checkout names its own revision, and a revision that differs from
    the one the run was asked to verify is a mismatch. A transported source
    has no repository metadata, so the revision its transport supplied is the
    only one it can carry, and the identity says which of the two it holds.
    """
    source = Path(source)
    expected = None if expected_revision in (None, '', UNKNOWN) else expected_revision
    identity = {'commit': UNKNOWN, 'tree': UNKNOWN, 'working_tree_dirty': None,
                'source_sha256': UNKNOWN, 'revision_source': 'unknown',
                'revision_status': 'unknown'}
    try:
        identity.update(checkout_identity(source))
    except (OSError, subprocess.SubprocessError):
        if source.is_dir():
            identity['source_sha256'] = source_digest(source)
        if expected:
            identity['commit'] = expected
            identity['revision_source'] = 'supplied'
            identity['revision_status'] = REVISION_SUPPLIED
        return identity
    identity['revision_source'] = 'git'
    if expected and identity['commit'] != expected:
        identity['revision_status'] = REVISION_MISMATCHED
    else:
        identity['revision_status'] = REVISION_VERIFIED
    return identity


def identity_establishes_acceptance(identity) -> bool:
    """Whether an identity names a revision the run can claim."""
    if not identity:
        return False
    if identity.get('revision_status') not in ACCEPTABLE_REVISIONS:
        return False
    commit = identity.get('commit')
    return bool(commit) and commit != UNKNOWN


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


def acceptance(records, *, native_execution=True, required=(), identity=None):
    """Whether the run establishes acceptance.

    Acceptance needs a runner that executed natively, at least one scenario
    that passed, no scenario that failed, every required scenario that
    passed, and an identity that names the revision the run verified. A
    skipped scenario is visible in the report; it does not stand in for a
    passed one.
    """
    if not native_execution or not records:
        return False
    if any(record["outcome"] == FAILED for record in records):
        return False
    if not any(record["outcome"] == PASSED for record in records):
        return False
    outcomes = {record["name"]: record["outcome"] for record in records}
    if any(outcomes.get(name) != PASSED for name in required):
        return False
    if identity is not None and not identity_establishes_acceptance(identity):
        return False
    return True


def summarize(records, *, native_execution=True, required=(), identity=None):
    """The report section every native verification carries."""
    outcomes = {record["name"]: record["outcome"] for record in records}
    required_records = [{"name": name, "outcome": outcomes.get(name, "missing")} for name in required]
    return {
        "status": status(records, native_execution=native_execution),
        "acceptance": acceptance(records, native_execution=native_execution, required=required,
                                 identity=identity),
        "counts": counts(records),
        "scenarios": list(records),
        "required": {
            "scenarios": required_records,
            "missing": [record["name"] for record in required_records if record["outcome"] == "missing"],
            "unmet": [record["name"] for record in required_records if record["outcome"] != PASSED],
        },
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
    expected_revision = facts.get("expected_revision")
    identity = facts.get("identity") or establish_identity(facts["source"], expected_revision)
    required = list(facts.get("required") or ())
    native_execution = bool(facts.get("native_execution", True))
    # The checkout the run established before its tests must still be the
    # checkout it verified at the end of them.
    current = establish_identity(facts["source"], expected_revision)
    established = identity.get("source_sha256")
    if established and established != UNKNOWN and current.get("source_sha256") != established:
        log.failed("source remained unchanged", "the source changed during the verification run")
    records = log.records
    report = dict(facts.get("fields") or {})
    report["checkout"] = identity
    report["scenarios"] = records
    report.update(summarize(records, native_execution=native_execution, required=required,
                             identity=identity))
    return report


def main(argv=None) -> int:
    """Assemble a native report from the facts an adapter collected."""
    parser = argparse.ArgumentParser(description="Assemble a native verification report.")
    parser.add_argument("--source", help="the checkout the run verified")
    parser.add_argument("--facts", help="the JSON facts the adapter collected")
    parser.add_argument("--output", help="the report file to write")
    parser.add_argument("--identity", action="store_true",
                        help="print the checkout identity the run verified and exit")
    parser.add_argument("--expected-revision", default=None,
                        help="the revision the run was asked to verify")
    arguments = parser.parse_args(argv)
    if arguments.identity:
        if not arguments.source:
            print("native report: the identity needs the checkout the run verified", file=sys.stderr)
            return 1
        identity = establish_identity(arguments.source, arguments.expected_revision)
        print(json.dumps(identity, sort_keys=True))
        return 0
    if not (arguments.source and arguments.facts and arguments.output):
        print("native report: the source, the facts, and the output are required", file=sys.stderr)
        return 1
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
