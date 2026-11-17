"""Measure a skill library and gate catalog rows by description and root budget.

The repository catalog owns the shared skill library, so the review reads the
bytes that ship: the description in a skill's frontmatter and the length of
its root document. A description of at most 240 characters keeps every skill's
context cost small, and a root document of at most 200 lines keeps the skill a
router instead of a manual. A root document may be longer when the skill ships
reference files, because the detail then lives beside the root and the root
points at it.

Rows that are already over the budget are recorded as reviewed exceptions in
``deployment/skill-budget-exceptions.tsv`` with their measured values and a
reason. A row above the budget without such an exception is new and fails the
check by name; a row whose measurements no longer match its exception changed
and fails as well, because updating an exception is a review action and never
an automatic pass.

The module reads a library path and never writes one. The catalog, the
exception list, and the per-client matrix are the repository's data; this
module only measures and reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DESCRIPTION_LIMIT = 240
ROOT_LINE_LIMIT = 200

# The shape of a client's skill discovery.
SHAPE_SHARED_TREE = "shared-tree"
SHAPE_COPY = "copy"
# The scope a client receives.
SCOPE_PROFILE = "profile"
SCOPE_GLOBAL = "global"


@dataclass(frozen=True)
class Measurement:
    """What one deployed skill costs a client that reads it."""

    name: str
    description_length: int
    root_lines: int
    has_reference: bool

    @property
    def over_description(self) -> bool:
        return self.description_length > DESCRIPTION_LIMIT

    @property
    def over_root(self) -> bool:
        return self.root_lines > ROOT_LINE_LIMIT and not self.has_reference

    @property
    def over_budget(self) -> bool:
        return self.over_description or self.over_root

    def summary(self) -> str:
        return (f"description {self.description_length} characters, "
                f"root {self.root_lines} lines, "
                f"reference {'yes' if self.has_reference else 'no'}")


@dataclass(frozen=True)
class Exception:
    """A reviewed over-budget row, with the values that were reviewed."""

    name: str
    description_length: int
    root_lines: int
    has_reference: bool
    reason: str

    def summary(self) -> str:
        return (f"description {self.description_length} characters, "
                f"root {self.root_lines} lines, "
                f"reference {'yes' if self.has_reference else 'no'}")

    def matches(self, measurement: Measurement) -> bool:
        return (self.description_length == measurement.description_length
                and self.root_lines == measurement.root_lines
                and self.has_reference == measurement.has_reference)


@dataclass(frozen=True)
class Client:
    """How one client discovers the skill library."""

    name: str
    shape: str
    root: str
    scope: str

    @property
    def reads_shared_tree(self) -> bool:
        return self.shape == SHAPE_SHARED_TREE


@dataclass
class Review:
    """The result of one review run."""

    library: Path | None = None
    measured: bool = False
    profile: list[str] = field(default_factory=list)
    tree: list[str] = field(default_factory=list)
    generated: list[str] = field(default_factory=list)
    device: list[str] = field(default_factory=list)
    measurements: dict[str, Measurement] = field(default_factory=dict)
    exceptions: dict[str, Exception] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def frontmatter(text: str) -> list[str]:
    """The frontmatter lines of a skill document."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return lines[1:index]
    return []


def _block_prose(lines: list[str], start: int, marker: str) -> str:
    """The prose of a folded (``>``) or literal (``|``) block scalar.

    A folded block joins its lines with a space and keeps a blank line as a
    paragraph break; a literal block keeps its line breaks. Both are read as
    the joined prose, so the length is the cost a client pays.
    """
    content: list[str] = []
    indent: int | None = None
    for line in lines[start:]:
        if not line.strip():
            content.append("")
            continue
        current = len(line) - len(line.lstrip(" "))
        if indent is None:
            indent = current
        elif current < indent:
            break
        content.append(line[indent:])
    while content and not content[-1].strip():
        content.pop()
    if marker.startswith(">"):
        paragraphs: list[str] = []
        current_paragraph: list[str] = []
        for line in content:
            if line.strip():
                current_paragraph.append(line.strip())
            elif current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
        if current_paragraph:
            paragraphs.append(" ".join(current_paragraph))
        return "\n".join(paragraphs)
    return "\n".join(content)


def description_of(text: str) -> str:
    """The description a skill publishes, with its frontmatter block read."""
    lines = frontmatter(text)
    for index, line in enumerate(lines):
        if line[:1].isspace() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip() != "description":
            continue
        value = value.strip()
        if value[:1] in (">", "|"):
            return _block_prose(lines, index + 1, value).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1].strip()
        if value:
            return value.strip()
        return _block_prose(lines, index + 1, ">").strip()
    return ""


def read_description(path: Path) -> str:
    """The description of the skill document at a path."""
    return description_of(path.read_text(encoding="utf-8", errors="replace"))


def has_reference(directory: Path) -> bool:
    """Whether a skill ships a reference file beside its root document.

    A reference file is any other markdown document in the skill directory. A
    skill with one may carry a longer root document, because the detail the
    root would otherwise hold lives in the reference.
    """
    for path in directory.rglob("*.md"):
        if path.name == "SKILL.md":
            continue
        if path.is_file():
            return True
    return False


def measure_skill(directory: Path) -> Measurement:
    """The measured cost of one deployed skill."""
    root = directory / "SKILL.md"
    text = root.read_text(encoding="utf-8", errors="replace")
    return Measurement(
        name=directory.name,
        description_length=len(description_of(text)),
        root_lines=len(text.splitlines()),
        has_reference=has_reference(directory),
    )


def measure_library(library: Path) -> dict[str, Measurement]:
    """The measured cost of every skill in a library."""
    measurements: dict[str, Measurement] = {}
    if not library.is_dir():
        return measurements
    for directory in sorted(library.iterdir()):
        if not directory.is_dir() or directory.is_symlink():
            continue
        if not (directory / "SKILL.md").is_file():
            continue
        measurements[directory.name] = measure_skill(directory)
    return measurements


def read_exceptions(path: Path) -> dict[str, Exception]:
    """The reviewed exceptions, keyed by skill name."""
    exceptions: dict[str, Exception] = {}
    if not path.is_file():
        return exceptions
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError(f"malformed skill budget exception: {line}")
        name, description_length, root_lines, reference, reason = fields
        if not name or not reason.strip():
            raise ValueError(f"skill budget exception needs a name and a reason: {line}")
        if reference not in ("yes", "no"):
            raise ValueError(f"skill budget exception reference must be yes or no: {name}")
        try:
            length = int(description_length)
            lines = int(root_lines)
        except ValueError as error:
            raise ValueError(f"skill budget exception needs measured numbers: {name}") from error
        if name in exceptions:
            raise ValueError(f"duplicate skill budget exception: {name}")
        exceptions[name] = Exception(name, length, lines, reference == "yes", reason.strip())
    return exceptions


def read_clients(path: Path) -> list[Client]:
    """The per-client skill matrix."""
    clients: list[Client] = []
    if not path.is_file():
        return clients
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != 4:
            raise ValueError(f"malformed skill client row: {line}")
        name, shape, root, scope = fields
        if shape not in (SHAPE_SHARED_TREE, SHAPE_COPY):
            raise ValueError(f"unknown skill client shape: {name}")
        if scope not in (SCOPE_PROFILE, SCOPE_GLOBAL):
            raise ValueError(f"unknown skill client scope: {name}")
        clients.append(Client(name, shape, root, scope))
    return clients


def read_device_roots(path: Path) -> list[tuple[str, str]]:
    """The client roots the deployment never writes, with their client."""
    roots: list[tuple[str, str]] = []
    if not path.is_file():
        return roots
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != 2:
            raise ValueError(f"malformed skill root row: {line}")
        roots.append((fields[0], fields[1]))
    return roots


def read_generated_skills(path: Path) -> list[str]:
    """The names of the generated skills the device recorded."""
    names: list[str] = []
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name = line.split("|")[0].strip()
        if name and name not in names:
            names.append(name)
    return names


def ratchet_failures(measurements: dict[str, Measurement],
                     exceptions: dict[str, Exception],
                     catalog_names: set[str]) -> list[str]:
    """The rows that fail the budget gate.

    A row above the budget without a reviewed exception is new and fails. A
    row whose measurements no longer match its exception changed and fails,
    and an exception for a row that is now within the budget fails as well:
    the record is stale, and only a review removes it.
    """
    failures: list[str] = []
    for name in sorted(exceptions):
        if name not in catalog_names:
            failures.append(
                f"{name}: the reviewed exception names a row the catalog does not own")
    for name in sorted(measurements):
        if name not in catalog_names:
            # A generated or device skill is outside the catalog budget.
            continue
        measurement = measurements[name]
        exception = exceptions.get(name)
        if measurement.over_budget and exception is None:
            failures.append(
                f"{name}: over the budget ({measurement.summary()}) and has no reviewed exception")
        elif exception is not None and not exception.matches(measurement):
            failures.append(
                f"{name}: the reviewed exception records {exception.summary()}, "
                f"the row measures {measurement.summary()}")
    return failures


def inventory_lines(profile: list[str], tree: list[str], generated: list[str],
                    device: list[str], clients: list[Client],
                    device_roots: list[tuple[str, str]],
                    automatic: int) -> list[str]:
    """The per-client inventory of the selected profile."""
    tagged = len(profile) - automatic
    selection = (f"{automatic} automatic, {tagged} tagged"
                 if tagged else f"{automatic} automatic")
    lines = [f"skill inventory: {len(profile)} profile skills ({selection}), "
             f"{len(generated)} generated skill{'' if len(generated) == 1 else 's'}, "
             f"{len(tree)} in the shared tree"]
    for client in clients:
        if client.shape == SHAPE_COPY:
            shape = f"a filtered copy in {client.root}"
            count = len(profile)
        else:
            shape = f"the shared tree {client.root}, no managed root of its own"
            count = len(profile) if client.scope == SCOPE_PROFILE else len(tree)
        lines.append(f"  {client.name}: {shape} ({client.scope}, {count} skills)")
    if device_roots:
        roots = ", ".join(f"{root} ({client})" for client, root in device_roots)
        lines.append(f"  device roots the deployment never writes: {roots}")
    if generated:
        lines.append(f"  generated skill: {', '.join(generated)}")
    if device:
        lines.append(f"  device skill: {', '.join(device)}")
    return lines


def review(library: Path | None, selections: dict[str, str],
           exceptions: dict[str, Exception], clients: list[Client],
           device_roots: list[tuple[str, str]],
           generated: list[str]) -> Review:
    """Review one library and report the inventory, the findings, and the ratchet."""
    result = Review(library=library, exceptions=exceptions)
    if library is None or not library.is_dir():
        where = "no library was named" if library is None else f"no library at {library}"
        result.lines.append(f"skill budget: NOT MEASURED ({where}); "
                            "point the check at a library with --library")
        result.lines.append("skill ratchet: NOT MEASURED (the budget was not measured)")
        return result
    result.measured = True
    measurements = measure_library(library)
    result.measurements = measurements
    result.tree = sorted(measurements)
    result.profile = sorted(name for name in measurements if name in selections)
    result.generated = [name for name in sorted(measurements)
                        if name in generated and name not in selections]
    result.device = [name for name in sorted(measurements)
                     if name not in selections and name not in result.generated]
    automatic = sum(1 for name in result.profile if selections[name] == "auto")
    result.lines.extend(inventory_lines(result.profile, result.tree, result.generated,
                                        result.device, clients, device_roots, automatic))
    catalog = set(selections)
    over = [measurements[name] for name in sorted(measurements)
            if name in catalog and measurements[name].over_budget]
    generated_over = [measurements[name] for name in sorted(result.generated)
                      if measurements[name].over_budget]
    result.lines.append(
        f"skill budget: a description of at most {DESCRIPTION_LIMIT} characters and a root "
        f"document of at most {ROOT_LINE_LIMIT} lines without a reference file")
    result.lines.append(
        f"skill budget: {len(over)} rows over the budget, {len(exceptions)} reviewed exceptions, "
        f"{len(catalog & set(measurements)) - len(over)} rows within the budget")
    for measurement in generated_over:
        result.lines.append(
            f"skill budget: {measurement.name}: generated skill, outside the catalog budget "
            f"({measurement.summary()})")
    outside = sum(1 for name in exceptions if name not in measurements)
    if outside:
        result.lines.append(
            f"skill budget: {outside} reviewed exceptions name rows outside this library "
            "(tagged or not deployed)")
    for measurement in over:
        exception = exceptions.get(measurement.name)
        state = "reviewed exception" if exception else "not reviewed"
        result.lines.append(
            f"skill budget: {measurement.name}: {measurement.summary()} ({state})")
    result.failures = ratchet_failures(measurements, exceptions, catalog)
    if result.failures:
        result.lines.append(f"skill ratchet: {len(result.failures)} failures")
        for failure in result.failures:
            result.lines.append(f"skill ratchet: {failure}")
    else:
        result.lines.append(
            f"skill ratchet: no failures, {len(exceptions)} reviewed exceptions match the "
            "measured rows")
    return result
