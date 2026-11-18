#!/usr/bin/env python3
"""Create a private redacted projection of an allow-listed device settings slice.

The rehearsal helper never copies an authentication store, a session file, or a
history database. It reads only the explicitly allow-listed inputs named in a
reviewed manifest, refuses linked or escaping input/output paths, parses and
redacts credential values before any artifact is written, and reports paths,
counts, and checksums without setting values.

The projection is a home-shaped directory tree. The operator rehearses the
public deployment against it with the ordinary bootstrap, so the merge and the
preservation rules are exercised without touching the real device.
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import sys
import tomllib

REDACTED = "<redacted>"
SCHEMA = "dotfiles.existing-settings-rehearsal/1"
HELPER_VERSION = "4"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFINEMENT = 3
EXIT_MISSING = 4
EXIT_REDACTION = 5

# Credential-named fields are redacted by name. The names follow the
# client-settings baseline policy and extend it with the common credential
# spellings; a provider's environment-variable *name* is not a credential.
CREDENTIAL_KEY = re.compile(
    r"(api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|id[_-]?token"
    r"|client[_-]?secret|private[_-]?key|authorization|password|passwd|secret"
    r"|credential|passphrase|bearer|token)$",
    re.IGNORECASE,
)
CREDENTIAL_EXACT_KEYS = {
    "auth", "authorization", "credentials", "secret", "token", "password",
    "passwd", "apikey", "api_key",
}

# A credential name is recognized by its segments, so `api_key`,
# `ANTHROPIC_AUTH_TOKEN`, and `privateKey` all name a credential, while
# `env_key` names a provider's environment variable and stays a value.
CREDENTIAL_NAME_SEGMENTS = {
    "apikey", "auth", "authorization", "bearer", "credential", "credentials",
    "password", "passwd", "passphrase", "privatekey", "secret", "secrets",
    "token", "tokens",
}

# A field whose name says that it holds an integrity value is not a
# credential: a trust digest carries no secret, and it is exactly the
# device-local state that the rehearsal has to carry into the projection,
# because the projection is what proves that the deployment preserves it.
# The last segment of the name decides, so `trusted_hash` and
# `trustedContentHash` name an integrity value.
INTEGRITY_NAME_SEGMENTS = {
    "hash", "digest", "checksum", "fingerprint", "sha", "sha256", "sha512",
    "comp_hash",
}

# A value that looks like a credential under a field name that does not say so
# is unknown data. It is never copied as a convenience: the default policy
# fails the rehearsal closed, and the alternative omits the field and counts
# it.
CREDENTIAL_VALUE = re.compile(
    r"sk-ant-[A-Za-z0-9_\-]{12,}"
    r"|sk-[A-Za-z0-9_\-]{12,}"
    r"|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|glmfix_[A-Za-z0-9_\-]{8,}"
    r"|glmf_[A-Za-z0-9_\-]{8,}"
    r"|(?i:bearer)\s+[A-Za-z0-9._\-]{8,}"
    r"|(?i:oauth)\s+key\s*=\s*\S+"
    r"|(?i:password)\s*=\s*\S+"
    r"|(?i:api[_-]?key)\s*[:=]\s*\S+"
    r"|(?<![0-9A-Za-z])[0-9a-fA-F]{40,}(?![0-9A-Za-z])",
)

# A freeform assignment such as `ANTHROPIC_AUTH_TOKEN=<value>` names a
# credential even when the value carries no vendor prefix at all. The name may
# be quoted, as it is in a serialized JSON object or in a single-quoted
# mapping key: the quote is only a delimiter, and the string is never
# interpreted, parsed, or executed.
ASSIGNMENT = re.compile(
    r"[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)[\"']?\s*[:=]\s*(?P<value>[^\s,;]+)")

# A URL that carries userinfo holds a credential: a proxy or an endpoint
# value can carry `user:password@host`. A URL without userinfo is ordinary
# configuration and is preserved. The bare form carries a password and a
# port, which is how a proxy value is written when it has no scheme.
URL_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/?#]*@")
URL_USERINFO_BARE = re.compile(
    r"(?<![\w.@\-])[A-Za-z0-9._\-]+:[^\s:@/]+@[A-Za-z0-9._\-]+:\d+")

# Inputs the rehearsal never reads, whatever a manifest says. Authentication
# stores, session files, and history databases stay on the device.
DENIED_BASENAMES = {
    "auth.json", "auth.toml", "auth.yaml", "accounts.json", "credentials",
    "credentials.json", "credentials.toml", ".netrc", "id_rsa", "id_ed25519",
    ".claude.json",
}
DENIED_PARTS = {
    "auth", "authentication", "sessions", "session", "history", "shell-snapshots",
    "logs", "atuin", "credentials", "secrets",
}
DENIED_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".log", ".pem", ".key", ".token", ".env",
    ".p12", ".pfx", ".keystore",
}

FORMATS = ("json", "jsonc", "toml", "text")


class RehearsalError(Exception):
    """A refusal that names the path and the reason, never a value."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code, message):
    raise RehearsalError(code, message)


def name_segments(name):
    """Split a field or variable name into its lowercase segments."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return [part.lower() for part in re.split(r"[^A-Za-z0-9]+", spaced) if part]


def name_is_credential(name):
    """True when a name carries a credential word in any of its segments."""
    if not isinstance(name, str):
        return False
    segments = name_segments(name)
    if not segments:
        return False
    if any(segment in CREDENTIAL_NAME_SEGMENTS for segment in segments):
        return True
    for index, segment in enumerate(segments):
        if segment == "key" and index and segments[index - 1] in ("api", "private"):
            return True
    return False


def name_is_integrity(name):
    """True when the last segment of a name says it holds an integrity value."""
    if not isinstance(name, str):
        return False
    segments = name_segments(name)
    if not segments:
        return False
    return segments[-1] in INTEGRITY_NAME_SEGMENTS


def is_credential_key(name):
    if not isinstance(name, str):
        return False
    if name.lower() in CREDENTIAL_EXACT_KEYS:
        return True
    if CREDENTIAL_KEY.search(name):
        return True
    return name_is_credential(name)


def looks_like_credential(value):
    """True when a value carries a credential shape or a credential name."""
    if not isinstance(value, str):
        return False
    if CREDENTIAL_VALUE.search(value):
        return True
    if URL_USERINFO.search(value) or URL_USERINFO_BARE.search(value):
        return True
    for match in ASSIGNMENT.finditer(value):
        if name_is_credential(match.group("name")):
            return True
    return False


def components(path):
    """Every existing-or-future component of an absolute path, root first."""
    path = os.path.abspath(str(path))
    parts = []
    current = path
    while True:
        parts.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return list(reversed(parts))


def refuse_linked_path(path, what):
    """Refuse a path whose components include a symbolic link."""
    for component in components(path):
        if os.path.islink(str(component)):
            fail(EXIT_CONFINEMENT, "%s is a symlink: %s" % (what, component))


def inside(root, path):
    root = os.path.realpath(str(root))
    path = os.path.realpath(str(path))
    return path == root or path.startswith(root + os.sep)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint_of(status, content):
    """The checksum, mode, and modification time of one read."""
    return {
        "sha256": digest(content),
        "mode": "%04o" % (status.st_mode & 0o7777),
        "mtime_ns": status.st_mtime_ns,
    }


def file_fingerprint(path):
    status = os.stat(str(path))
    with open(str(path), "rb") as handle:
        content = handle.read()
    return fingerprint_of(status, content)


def strip_jsonc(text):
    """Remove JSONC comments outside strings."""
    out = []
    index = 0
    length = len(text)
    in_string = False
    while index < length:
        character = text[index]
        if in_string:
            out.append(character)
            if character == "\\" and index + 1 < length:
                out.append(text[index + 1])
                index += 2
                continue
            if character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            out.append(character)
            index += 1
            continue
        if character == "/" and index + 1 < length:
            following = text[index + 1]
            if following == "/":
                while index < length and text[index] != "\n":
                    index += 1
                continue
            if following == "*":
                end = text.find("*/", index + 2)
                if end == -1:
                    fail(EXIT_USAGE, "unterminated comment in a JSONC input")
                index = end + 2
                continue
        out.append(character)
        index += 1
    return "".join(out)


def read_manifest(path):
    entries = []
    seen = set()
    with open(str(path), "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                fields = [field.strip() for field in line.split()]
            if len(fields) < 2:
                fail(EXIT_USAGE, "manifest line %d is not path and format" % number)
            relative = fields[0].strip()
            fmt = fields[1].strip().lower()
            requirement = fields[2].strip().lower() if len(fields) > 2 else "required"
            if requirement not in ("required", "optional"):
                fail(EXIT_USAGE, "manifest line %d has an unknown requirement" % number)
            if fmt not in FORMATS:
                fail(EXIT_USAGE, "manifest line %d has an unknown format: %s" % (number, fmt))
            if not relative or relative.startswith("/") or relative.startswith("~"):
                fail(EXIT_USAGE, "manifest line %d is not a relative home path" % number)
            parts = relative.split("/")
            if any(part in ("", ".", "..") for part in parts):
                fail(EXIT_USAGE, "manifest line %d is not a plain relative path" % number)
            if relative in seen:
                fail(EXIT_USAGE, "manifest line %d repeats an input" % number)
            seen.add(relative)
            entries.append({"path": relative, "format": fmt, "requirement": requirement})
    if not entries:
        fail(EXIT_USAGE, "the manifest names no input")
    return entries


def refuse_excluded_input(relative):
    parts = relative.split("/")
    base = parts[-1]
    if base.lower() in DENIED_BASENAMES:
        fail(EXIT_USAGE, "the manifest names an excluded input: %s" % relative)
    for part in parts:
        if part.lower() in DENIED_PARTS:
            fail(EXIT_USAGE, "the manifest names an excluded input: %s" % relative)
    suffix = os.path.splitext(base)[1].lower()
    if suffix in DENIED_SUFFIXES:
        fail(EXIT_USAGE, "the manifest names an excluded input: %s" % relative)


def redact_structure(value, relative, policy, counts):
    """Return the redacted document; counts carry the field statistics."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if is_credential_key(key):
                counts["redacted"] += 1
                result[key] = blank_container(item, counts)
                continue
            if isinstance(item, str) and looks_like_credential(item):
                # The credential-name rule wins over the integrity rule, so
                # `api_key_hash` is still redacted above. An integrity-named
                # field is not a credential: its value is projected as it is.
                if name_is_integrity(key):
                    counts["integrity"] += 1
                    result[key] = item
                    continue
                unknown(relative, policy, counts)
                counts["omitted"] += 1
                continue
            result[key] = redact_structure(item, relative, policy, counts)
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str) and looks_like_credential(item):
                unknown(relative, policy, counts)
                counts["omitted"] += 1
                continue
            result.append(redact_structure(item, relative, policy, counts))
        return result
    return value


def blank_container(value, counts):
    """Keep a credential-named container's shape and blank every leaf."""
    if isinstance(value, dict):
        return {key: blank_container(item, counts) for key, item in value.items()}
    if isinstance(value, list):
        return [blank_container(item, counts) for item in value]
    if value is None:
        return None
    counts["redacted_leaves"] += 1
    return REDACTED


def unknown(relative, policy, counts):
    if policy == "omit":
        counts["unknown"] += 1
        return
    fail(EXIT_REDACTION,
         "unknown credential-shaped value in %s; refusing to project it" % relative)


def json_leaves(value):
    if isinstance(value, dict):
        return sum(json_leaves(item) for item in value.values())
    if isinstance(value, list):
        return sum(json_leaves(item) for item in value)
    return 1


def toml_comments(text):
    """Return every comment in a TOML document, without the leading hash."""
    comments = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "#":
            end = text.find("\n", index)
            if end == -1:
                end = length
            comments.append(text[index + 1:end])
            index = end
            continue
        if character in "\"'":
            index = skip_toml_string(text, index)
            continue
        index += 1
    return comments


def skip_toml_string(text, index):
    """Return the index just after the string that starts at index."""
    length = len(text)
    if text.startswith('\"\"\"', index):
        cursor = index + 3
        while cursor < length:
            if text[cursor] == "\\":
                cursor += 2
                continue
            if text.startswith('\"\"\"', cursor):
                return cursor + 3
            cursor += 1
        return length
    if text.startswith("'''", index):
        end = text.find("'''", index + 3)
        return length if end == -1 else end + 3
    quote = text[index]
    cursor = index + 1
    while cursor < length:
        if quote == '"' and text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == quote:
            return cursor + 1
        if text[cursor] == "\n":
            return cursor
        cursor += 1
    return length


def toml_key_text(key):
    """Render a TOML key, quoting it when it is not a bare key."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key, ensure_ascii=False)


def toml_value(value):
    """Render a scalar, a list, or an inline table as a TOML value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            "%s = %s" % (toml_key_text(key), toml_value(item))
            for key, item in value.items()) + " }"
    fail(EXIT_REDACTION, "the TOML projection cannot carry this value type")


def serialize_toml(document):
    """Render a parsed TOML document as TOML text."""
    lines = []

    def emit(table, path):
        # A table's own values come before its sub-tables: TOML binds a key
        # to the table whose header precedes it.
        for key, value in table.items():
            if isinstance(value, dict) and value:
                continue
            lines.append("%s = %s" % (toml_key_text(key), toml_value(value)))
        for key, value in table.items():
            if not (isinstance(value, dict) and value):
                continue
            child = path + [key]
            # A table that holds only sub-tables needs no header of its own:
            # TOML implies it from the sub-table header.
            if any(not (isinstance(item, dict) and item) for item in value.values()):
                header = ".".join(toml_key_text(part) for part in child)
                lines.append("[%s]" % header)
            emit(value, child)

    emit(document, [])
    return "\n".join(lines) + "\n"


def container_is_redacted(value):
    """True when every leaf of a credential-named container is redacted."""
    if isinstance(value, dict):
        return all(container_is_redacted(item) for item in value.values())
    if isinstance(value, list):
        return all(container_is_redacted(item) for item in value)
    if value is None:
        return True
    return value == REDACTED


def check_redacted(value, relative):
    """Fail when a projected document still carries a credential."""
    if isinstance(value, dict):
        for key, item in value.items():
            if is_credential_key(key):
                if not container_is_redacted(item):
                    fail(EXIT_REDACTION,
                         "the projection for %s still holds a credential-named field"
                         % relative)
                continue
            if isinstance(item, str) and name_is_integrity(key):
                # An integrity-named field carries an integrity value, not a
                # credential: it is projected as it is.
                continue
            check_redacted(item, relative)
    elif isinstance(value, list):
        for item in value:
            check_redacted(item, relative)
    elif isinstance(value, str):
        if looks_like_credential(value):
            fail(EXIT_REDACTION,
                 "the projection for %s still holds a credential-shaped value"
                 % relative)


def project_toml(text, relative, policy, counts):
    """Parse a TOML document, redact it, and re-emit valid TOML."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        fail(EXIT_USAGE, "cannot parse %s as TOML" % relative)
    for comment in toml_comments(text):
        if looks_like_credential(comment):
            unknown(relative, policy, counts)
            counts["omitted"] += 1
    redacted = redact_structure(document, relative, policy, counts)
    projected = serialize_toml(redacted)
    try:
        emitted = tomllib.loads(projected)
    except tomllib.TOMLDecodeError:
        fail(EXIT_USAGE, "cannot emit a valid TOML projection for %s" % relative)
    if emitted != redacted:
        fail(EXIT_USAGE, "the emitted TOML projection for %s does not round-trip"
             % relative)
    check_redacted(emitted, relative)
    return projected, json_leaves(document), json_leaves(redacted)


def project_document(entry, text, policy):
    """Return the projected text, its record count, and the field counts."""
    counts = {"redacted": 0, "omitted": 0, "unknown": 0, "redacted_leaves": 0,
              "integrity": 0}
    relative = entry["path"]
    if entry["format"] == "text":
        if looks_like_credential(text):
            unknown(relative, policy, counts)
            counts["omitted"] += 1
            return None, 0, 0, counts
        records = len([line for line in text.splitlines() if line.strip()])
        return text, records, records, counts
    if entry["format"] == "toml":
        projected, records, projected_records = project_toml(text, relative, policy, counts)
    else:
        try:
            document = json.loads(strip_jsonc(text))
        except ValueError:
            fail(EXIT_USAGE, "cannot parse %s as %s" % (relative, entry["format"]))
        redacted = redact_structure(document, relative, policy, counts)
        projected = json.dumps(redacted, indent=2, ensure_ascii=False) + "\n"
        try:
            emitted = json.loads(projected)
        except ValueError:
            fail(EXIT_USAGE, "cannot emit a valid JSON projection for %s" % relative)
        if emitted != redacted:
            fail(EXIT_USAGE, "the emitted JSON projection for %s does not round-trip"
                 % relative)
        check_redacted(emitted, relative)
        records = json_leaves(document)
        projected_records = json_leaves(redacted)
    return projected, records, projected_records, counts


def validate_projection_path(projection, source_home):
    """Refuse a projection path that is not a fresh, private directory."""
    if not os.path.isabs(str(projection)):
        fail(EXIT_CONFINEMENT, "the projection path must be absolute")
    if str(projection) == os.sep:
        fail(EXIT_CONFINEMENT, "the projection path cannot be the filesystem root")
    if inside(source_home, projection):
        fail(EXIT_CONFINEMENT, "the projection must not live inside the source home")
    refuse_linked_path(projection, "the projection path")
    if os.path.lexists(str(projection)):
        if not os.path.isdir(str(projection)):
            fail(EXIT_CONFINEMENT, "the projection path is not a directory")
        if os.listdir(str(projection)):
            fail(EXIT_CONFINEMENT, "the projection directory is not empty")
    return projection


def validate_report_path(report_path, projection, source_home):
    """Refuse a report path that is not a fresh file outside every output."""
    if not os.path.isabs(str(report_path)):
        fail(EXIT_CONFINEMENT, "the report path must be absolute")
    if inside(source_home, report_path):
        fail(EXIT_CONFINEMENT, "the report must not live inside the source home")
    if report_path == projection or inside(projection, report_path):
        fail(EXIT_CONFINEMENT, "the report must not live inside the projection")
    refuse_linked_path(report_path, "the report path")
    if os.path.lexists(str(report_path)):
        fail(EXIT_CONFINEMENT, "the report path already exists")
    return report_path


def write_private(path, text):
    parent = os.path.dirname(str(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, mode=0o700, exist_ok=True)
        os.chmod(parent, 0o700)
    try:
        handle = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        fail(EXIT_CONFINEMENT, "cannot write the private artifact: %s" % path)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.chmod(str(path), 0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Project a redacted, allow-listed device settings slice.")
    parser.add_argument("--source-home", required=True,
                        help="the device home that holds the allow-listed inputs")
    parser.add_argument("--manifest", required=True,
                        help="the reviewed input manifest")
    parser.add_argument("--projection", required=True,
                        help="the private directory that receives the projection")
    parser.add_argument("--report", required=True,
                        help="the private, value-free report path")
    parser.add_argument("--unknown-credential-policy", choices=("fail", "omit"),
                        default="fail",
                        help="fail closed on unknown credential-shaped data (default), "
                             "or omit it and count it")
    arguments = parser.parse_args(argv)

    source_home = os.path.realpath(arguments.source_home)
    if not os.path.isdir(source_home):
        fail(EXIT_USAGE, "the source home is not a directory")
    if not os.path.isfile(arguments.manifest):
        fail(EXIT_USAGE, "the manifest is not a file")
    projection = os.path.abspath(arguments.projection)
    report_path = os.path.abspath(arguments.report)

    # The output boundary is settled before anything is read or written: the
    # projection is a fresh directory, and the report is a fresh file that
    # lives in neither the source home nor the projection.
    validate_projection_path(projection, source_home)
    validate_report_path(report_path, projection, source_home)

    entries = read_manifest(arguments.manifest)
    for entry in entries:
        refuse_excluded_input(entry["path"])

    prepared = []
    totals = {"files": 0, "records": 0, "redacted": 0, "omitted": 0, "unknown": 0,
              "integrity": 0}
    for entry in entries:
        relative = entry["path"]
        source = os.path.join(source_home, relative)
        if os.path.islink(source):
            fail(EXIT_CONFINEMENT, "the input path is a symlink: %s" % relative)
        if not os.path.exists(source):
            if entry["requirement"] == "optional":
                prepared.append({"path": relative, "format": entry["format"],
                                 "status": "absent", "required": False})
                continue
            fail(EXIT_MISSING, "the allow-listed input is missing: %s" % relative)
        refuse_linked_path(os.path.dirname(source), "the input path")
        if not os.path.isfile(source):
            fail(EXIT_MISSING, "the allow-listed input is not a regular file: %s" % relative)
        # The fingerprint that is compared with the later one is taken from
        # the bytes that were actually read: the status is sampled before the
        # read and the checksum is computed over the content that came back.
        status = os.stat(str(source))
        with open(source, "rb") as handle:
            raw = handle.read()
        text = raw.decode("utf-8", "replace")
        before = fingerprint_of(status, raw)
        projected, records, projected_records, counts = project_document(
            entry, text, arguments.unknown_credential_policy)
        after = file_fingerprint(source)
        if before != after:
            fail(EXIT_CONFINEMENT, "the input changed while it was read: %s" % relative)
        totals["files"] += 1
        totals["records"] += records
        totals["redacted"] += counts["redacted"]
        totals["omitted"] += counts["omitted"]
        totals["unknown"] += counts["unknown"]
        totals["integrity"] += counts["integrity"]
        if projected is None:
            prepared.append({"path": relative, "format": entry["format"],
                             "status": "omitted", "required": entry["requirement"] == "required",
                             "source": {"sha256": before["sha256"], "mode": before["mode"],
                                        "mtime_ns": before["mtime_ns"], "records": records},
                             "source_after": {"sha256": after["sha256"], "mode": after["mode"],
                                              "mtime_ns": after["mtime_ns"]},
                             "projected": {"records": 0},
                             "redacted_fields": counts["redacted"],
                             "omitted_fields": counts["omitted"],
                             "unknown_credential_fields": counts["unknown"],
                             "integrity_fields": counts["integrity"]})
            continue
        prepared.append({
            "path": relative,
            "format": entry["format"],
            "status": "projected",
            "required": entry["requirement"] == "required",
            "source": {"sha256": before["sha256"], "mode": before["mode"],
                       "mtime_ns": before["mtime_ns"], "records": records},
            "source_after": {"sha256": after["sha256"], "mode": after["mode"],
                             "mtime_ns": after["mtime_ns"]},
            "projected": {"records": projected_records},
            "redacted_fields": counts["redacted"],
            "omitted_fields": counts["omitted"],
            "unknown_credential_fields": counts["unknown"],
            "integrity_fields": counts["integrity"],
            "_text": projected,
        })

    # The projection directory is created only after every input has been
    # redacted, and its path is checked again so that a directory that
    # appeared in the meantime is never written into.
    validate_projection_path(projection, source_home)
    parent = os.path.dirname(str(projection))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, mode=0o700, exist_ok=True)
        os.chmod(parent, 0o700)
    os.makedirs(str(projection), mode=0o700, exist_ok=True)
    os.chmod(str(projection), 0o700)
    files = []
    for item in prepared:
        if item["status"] == "absent":
            files.append({"path": item["path"], "format": item["format"],
                          "status": "absent", "required": False})
            continue
        if item["status"] == "omitted":
            files.append({
                "path": item["path"],
                "format": item["format"],
                "status": "omitted",
                "required": item["required"],
                "source": item["source"],
                "source_after": item["source_after"],
                "projected": {"records": 0},
                "redacted_fields": item["redacted_fields"],
                "omitted_fields": item["omitted_fields"],
                "unknown_credential_fields": item["unknown_credential_fields"],
                "integrity_fields": item["integrity_fields"],
            })
            continue
        target = os.path.join(str(projection), item["path"])
        write_private(target, item.pop("_text"))
        with open(target, "rb") as handle:
            projected_digest = digest(handle.read())
        files.append({
            "path": item["path"],
            "format": item["format"],
            "status": "projected",
            "required": item["required"],
            "source": item["source"],
            "source_after": item["source_after"],
            "projected": {"sha256": projected_digest,
                          "mode": "%04o" % (os.stat(target).st_mode & 0o7777),
                          "records": item["projected"]["records"]},
            "redacted_fields": item["redacted_fields"],
            "omitted_fields": item["omitted_fields"],
            "unknown_credential_fields": item["unknown_credential_fields"],
            "integrity_fields": item["integrity_fields"],
        })

    report = {
        "schema": SCHEMA,
        "helper_version": HELPER_VERSION,
        "manifest": os.path.abspath(arguments.manifest),
        "source_home": source_home,
        "projection": projection,
        "unknown_credential_policy": arguments.unknown_credential_policy,
        "policy_notes": {
            "credential_names": "a credential-named field is redacted by name",
            "integrity_names": "an integrity-named field is not a credential; "
                               "its value is projected as it is",
            "unknown_credential_shaped_values": arguments.unknown_credential_policy,
        },
        "source_unchanged": all(
            all(entry["source"][key] == entry["source_after"][key]
                for key in ("sha256", "mode", "mtime_ns"))
            for entry in files if entry["status"] in ("projected", "omitted")),
        "environment": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "files": files,
        "totals": {
            "files": totals["files"],
            "projected_files": sum(1 for entry in files if entry["status"] == "projected"),
            "records": totals["records"],
            "projected_records": sum(entry["projected"]["records"]
                                     for entry in files if entry["status"] == "projected"),
            "redacted_fields": totals["redacted"],
            "omitted_fields": totals["omitted"],
            "unknown_credential_fields": totals["unknown"],
            "integrity_fields": totals["integrity"],
        },
    }
    write_private(report_path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RehearsalError as error:
        sys.stderr.write("dotfiles: rehearsal refused: %s\n" % error.message)
        sys.exit(error.code)
