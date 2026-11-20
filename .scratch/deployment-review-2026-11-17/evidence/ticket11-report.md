# Ticket 11 report — existing-device settings rehearsal (redacted, allow-listed)

Worktree: `/Users/joey/SHELL/dotfiles.fix-macos-settings-rehearsal`
Branch: `fix/macos-settings-rehearsal` (base verified at `37dc127`, integration
tip `fix/deployment-review` at the same commit; worktree was clean at start).
No commit was made: the supervisor reviews, commits, and integrates.

## Scope delivered

| File | Kind | Purpose |
| --- | --- | --- |
| `deployment/rehearse_settings.py` | new | operator helper: private, redacted, allow-listed projection of an existing device's managed settings + value-free report |
| `deployment/rehearsal/existing-mac-inputs.tsv` | new | the reviewed input allow-list (supervisor reviews before any real-device run) |
| `tests/test_existing_settings_rehearsal.py` | new | behaviour tests at the public helper + public bootstrap seam |
| `docs/MACOS_DEPLOYMENT.md` | edited | operator documentation of the rehearsal and its boundary |

No deployment/magpie code, no `tests/test_magpie.py`, no `docs/MAGPIE.md`, no
`AGENTS.md`, no Magpie ADR, and no README/GLOSSARY change. No new harness or
generic framework: the tests reuse `tests/fixtures/skills.py`, the public
`bootstrap.sh`, and `unittest`.

## Seam under test

* `python3 deployment/rehearse_settings.py --source-home … --manifest … --projection … --report …`
  (public CLI of the helper).
* `/bin/bash bootstrap.sh --home <projection> --apply-only`
  (public bootstrap/settings-merge boundary, run against the projected home).

No private-helper-coupled unit test: every assertion reads the helper's exit
status, its written artifacts, its report, or the result of the public
bootstrap against the projection.

## Exact allow-listed inputs (reviewed manifest)

`deployment/rehearsal/existing-mac-inputs.tsv` (path TAB format TAB requirement):

```
.claude/settings.json                json   required
.codex/config.toml                   toml   required
.codex/hooks.json                    json   optional
.kimi-code/config.toml               toml   optional
.kimi-code/tui.toml                  toml   optional
.kimi-code/mcp.json                  json   optional
.config/opencode/opencode.jsonc      jsonc  optional
.pi/agent/settings.json              json   required
.pi/agent/models-store.json          json   optional
.qoder/settings.json                 json   optional
.minimax/mcp.json                    json   optional
.claude/CLAUDE.local.md              text   optional
.codex/AGENTS.override.md            text   optional
.config/ghostty/config.local.ghostty text   optional
```

Explicitly excluded and refused by the helper even if a manifest names them:
`.claude.json` (OAuth account + user MCP fields), every `auth.json`/
`credentials*`/`.netrc` store, `sessions/`, `shell-snapshots/`, `history/`,
`logs/`, `atuin/` trees, and `.db`/`.sqlite`/`.log`/`.pem`/`.key`/`.token`/`.env`
files. The Atuin snapshot rehearsal from the earlier ticket is untouched: no
database was recopied.

## Redaction policy

1. **By name (redacted in place, value replaced with `<redacted>`):** keys
   ending in `api_key`/`apikey`, `auth_token`, `access_token`,
   `refresh_token`, `id_token`, `client_secret`, `private_key`,
   `authorization`, `password`/`passwd`, `secret`, `credential`, `passphrase`,
   `bearer`, `token`, plus the exact names `auth`, `authorization`,
   `credentials`, `secret`, `token`, `password`, `passwd`, `apikey`,
   `api_key`. A credential-named container keeps its shape and has every leaf
   blanked. A provider's environment-variable **name** (Codex `env_key`,
   `ANTHROPIC_*_MODEL`) is not a credential value and is preserved.
2. **By shape (unknown data, never copied as a convenience):** a value that
   matches `sk-…`, `sk-ant-…`, `gh[pousr]_…`, `xox[baprs]-…`, `AKIA…`, a JWT,
   `Bearer …`, `-----BEGIN … PRIVATE KEY-----`, `glmfix_…`/`glmf_…`, an
   `oauth key = …` assignment, or a 40+ character hex string. Default policy
   **fails closed** (exit 5, no artifact written, message names the path
   only). `--unknown-credential-policy omit` omits the field (or the whole text
   file) and counts it in the report.
3. **By name inside a freeform assignment:** a `NAME=value` or `NAME: value`
   assignment whose name carries a credential word (`ANTHROPIC_AUTH_TOKEN`,
   `api_key`, `client_secret`, …) is credential content even when the value
   carries no vendor prefix at all. The name may be quoted, as it is in a
   serialized JSON object (`"ANTHROPIC_AUTH_TOKEN":"…"`) or in a
   single-quoted mapping key (`'ANTHROPIC_AUTH_TOKEN': '…'`); the quote is
   only a delimiter and the string is never parsed or evaluated. This covers
   text inputs, TOML comments, and any string value. Default policy fails
   closed; the omit policy drops the comment or the field and counts it.
4. Redaction happens **before** any artifact is written: the helper processes
   every input in memory and only then creates the projection directory.
5. **By shape in a URL:** a URL that carries userinfo
   (`http://user:password@host`, and the bare `user:password@host:port` form)
   is credential content: a proxy or endpoint value can hold a password. A
   URL without userinfo is ordinary configuration and is preserved, and so is
   a provider's environment-variable name. Default policy fails closed; the
   omit policy drops the field and counts it.
6. Formats: `json`, `jsonc` (comment-stripping parser), `toml` (parsed with
   `tomllib`, redacted by structure, and re-emitted as validated TOML), `text`
   (verbatim copy, refused/omitted when it holds credential content). A
   malformed JSON or TOML input refuses the rehearsal before any artifact
   exists, and the emitted document is parsed again and compared with the
   redacted document before it is written.

## Confinement rules

* Inputs: a symlinked input file, or a symlinked directory inside the home, is
  refused; the source home is resolved once and never followed below.
* Projection/report: absolute paths only, no symbolic link anywhere in the
  path (so `/tmp` is refused on macOS; use `/private/tmp`), never inside the
  source home, never the filesystem root. The projection directory must be
  empty or absent, the report path must not exist, and the report must not
  live inside the projection. Both output paths are therefore new: a rerun
  takes fresh paths instead of writing over an earlier artifact.
* Artifacts: projection directory `0700`, projected files `0600`, report `0600`.
  Every artifact is created with `O_EXCL`, so an existing file is never
  truncated — this is what keeps a report path that is a hard link to a
  device file from rewriting that device file.
* The device is only read: the report records each source's sha256, mode, and
  mtime around the read and fails if any changed. The sha256 that is compared
  is the checksum of the bytes that were actually read; the mode and the
  modification time are sampled just before the read, and the same
  fingerprint is taken again after the projection was computed. The source
  bytes, permissions, and modification times are preserved.

## Completeness proof (value-free report)

Per input the report carries: path, format, status (`projected`/`omitted`/
`absent`), source sha256/mode/mtime_ns/records, the same fingerprint taken
again after the projection was computed, projected sha256/mode/records,
redacted/omitted/unknown counts. Totals
carry files, projected files, records, projected records, and the field
counts; `source_unchanged` is the aggregate verdict. The environment
(python/system/machine) is recorded without any value.

Record counting: JSON/JSONC = scalar leaf values; TOML = scalar leaf values
of the parsed document; text = non-empty lines. Redaction replaces a value in
place, so a redacted document keeps the record count of its source; an
omitted field lowers it by exactly one, and the report shows both numbers
(`projected_records` and `omitted_fields`).

Example from a fabricated run (counts only, no values):
`files=3, projected_files=3, records=7, projected_records=7, redacted_fields=1,
omitted_fields=0, unknown_credential_fields=0, source_unchanged=true`.

## Evidence chronology (corrected)

The first version of this report called every red state below "red → green
TDD". That was wrong, and the correction is recorded here rather than by
rewriting history. There are three different kinds of evidence in this
ticket, and only the third kind is a red-before-green regression.

**(a) Original implementation failures — the behaviour did not exist yet.**
The first working version of the helper did not satisfy the assertions that
were written for it. These are genuine failures of the original
implementation, not mutation evidence.

| Slice | Original failure | Green state |
| --- | --- | --- |
| 1. redaction + preservation + untouched source | the helper crashed while writing the report (`AttributeError: 'str' object has no attribute 'parent'`) | 1 test passed |
| 2. report completeness | `source_unchanged` was false (the fingerprint comparison included the record count) | 2 tests passed |

**(b) Mutation sensitivity checks — the behaviour was removed from a working
helper to prove that the test detects it.** These are not red-before-green
regressions: the helper was already green, and a slice was deliberately
broken and restored.

| Slice | Mutation | Green state |
| --- | --- | --- |
| 3. unknown credential-shaped data | the default policy was flipped to `omit` | 4 tests passed |
| 4. linked input / linked output / projection inside the home | the link refusal was disabled | 7 tests passed |
| 5. missing input + excluded manifest inputs | the exclusion check was removed and a missing required input was tolerated | 11 tests passed |
| 6. public bootstrap rehearsal | the rehearsal fixture was missing a device MCP file (a test-fixture defect, corrected in the test) | 13 tests passed |
| 7. redaction slice re-check | credential-name redaction was disabled | 14 tests passed |
| 8. text inputs | the record-count expectation was corrected after the first run (2 non-empty lines) | 16 tests passed |
| 9. linked parent directory inside the home | the parent-link check was removed | 17 tests passed |

**(c) New red-before-fix regressions — the follow-up below.** These were
written at the public helper seam, observed failing against the delivered
helper, and only then fixed. Their evidence is in the follow-up section.

Commands (bounded, single-threaded, no network):

```
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_existing_settings_rehearsal.py" -v
# 17 tests, OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_codegraph.py" -v
# 9 tests, OK (2 skipped: pinned CodeGraph CLI / pinned MCP clients unavailable)

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_claude_model_preservation.py"
# 5 tests, OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_caveman.py"
# 2 tests, OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_agents.py"
# 14 tests, OK (3 skipped)

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_deployment.py"
# 20 tests, 2 failures (host scope, see below)

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_macos.py"
# 7 tests, 1 failure + 2 skipped (host scope, see below)

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_magpie.py"
# 256 tests, 131 failures + 4 errors — sandbox-blocked, see below
```

### Checks that did not pass, recorded accurately

* `tests/test_magpie.py`: 131 failures + 4 errors. Every failure traces to the
  sandbox denying writes to `/tmp` (`mkstemp failed on /tmp/magpie-picked.…:
  Operation not permitted`; `/tmp` is confirmed unwritable here). The suite
  fixes its fixtures in `/tmp`, so it cannot run in this confined sandbox.
  No Magpie code was touched by this ticket; this is **not** a pass.
* `tests/test_deployment.py`: 2 failures, both Linux-host scope (the suite
  assumes a Linux x86_64 host, as `AGENTS.md` records: the privileged-option
  checks expect the Linux message and get the macOS platform message).
* `tests/test_macos.py`: 1 failure — the Windows ARM architecture matrix on
  an ARM macOS host — plus 2 skips.
* Not run here (out of proportion / unavailable): `tests/native_macos.py`
  (the native macOS gate is ticket 12's stable-source gate, deliberately not
  started), the full `unittest discover` sweep of all 90+ test modules, and
  `tests/verify_portable.py` (needs network).

## Behaviour demonstrated by the tests (all fabricated fixtures)

* Credential-named fields are redacted; unrelated providers, trust records,
  hooks, MCP servers, themes, skills lists, device flags, and terminal
  preferences survive the public settings merge.
* The reviewed manifest runs as it stands; excluded inputs are refused.
* Unknown credential-shaped data fails closed with no artifact and no value in
  the message, or is omitted and counted.
* A linked input, a linked parent directory, a linked projection, a
  projection/report inside the source home, and a missing required input are
  all refused; the device keeps its bytes, mode, and mtime.
* An existing report path — including a hard link whose other name is a
  device file — and a report inside the projection are refused before any
  write; malformed JSON or TOML refuses before any artifact exists.
* The public bootstrap still refuses a linked managed target and still
  preserves a conflicting skill symlink instead of writing through it.
* The report is value-free and proves completeness by file/record counts and
  checksums.

## Remaining risks and limits

* **A redacted rehearsal is not credential or inference acceptance.** The
  synthetic/redacted settings do not prove that live credentials work, that
  the clients accept the projected values, that the gateway routes a request,
  or that the real device's unmanaged files are correct.
* The redaction heuristics are name- and shape-based. A credential stored
  under an unusual field name and an unusual shape would be copied; the
  fail-closed default only covers the shapes listed above. The manifest may be
  narrowed. **Superseded:** an earlier version of this report told the
  supervisor to read the projected files before running the bootstrap against
  them. That advice is withdrawn: no one — supervisor or model — should read
  projected values, real or fabricated, as a redaction check. The safety
  argument stays local and value-free, and the manifest is the control that
  narrows what is projected at all.
* The projection is a *settings* slice. Files outside the allow-list (auth
  stores, sessions, history, arbitrary trees) are not rehearsed at all — that
  is deliberate, not an omission.
* The TOML redaction is structural, not line-scoped: the document is parsed
  with `tomllib`, redacted as a structure, and re-emitted as TOML that is
  parsed again and compared with the redacted document before it is written.
  A credential held in a multi-line string or in an inline table is redacted
  rather than copied. The cost of that guarantee is that the projected TOML
  is a re-serialization: comments are not carried into the projection, and
  an inline table becomes a table. The settings values survive; the original
  formatting does not.
* The rehearsal has not been run against the real device. The supervisor must
  review the helper and the manifest first and then execute the approved
  local projection.
* No live-home deployment, no gateway probe, no paid inference, no install,
  no download, no index, no permission change, and no account login was
  performed. No live home settings, auth store, `.env`, credential, session,
  or history content was read; every fixture in the tests is fabricated.

## Follow-up: the supervisor's verified findings (this round)

The supervisor reviewed the first delivery with the public CLI and found five
gaps. Each one is listed below with the finding, the fix, and the new
red-before-fix regression that proved the gap before the fix. All fixtures
are fabricated; no value appears in this report.

### Finding 1 — a TOML credential held in a multi-line string

* Finding: a TOML file whose `api_key` holds a multi-line string was
  projected with the credential still in it, and the projected file was not
  valid TOML.
* Regression (red before the fix):
  `test_toml_multiline_credential_is_redacted_and_the_projection_stays_valid_toml`
  — the fabricated marker was found in the projection and the projection did
  not parse.
* Fix: TOML is parsed with `tomllib`, redacted as a structure, and re-emitted
  as TOML. A credential-named key is redacted whatever shape its value has,
  the emitted document is parsed again, and it is compared with the redacted
  document before it is written.

### Finding 2 — a credential-named key inside an inline table

* Finding: `headers = { Authorization = "…" }` was projected with the
  credential still in it; matching the outer key and the known value shapes
  was not enough.
* Regression (red before the fix):
  `test_toml_inline_table_with_a_credential_key_is_redacted`.
* Fix: redaction walks the parsed structure, so a credential-named key is
  redacted at any depth — nested table, inline table, or array element — and
  a value-free post-check refuses the rehearsal if a credential-named field or
  a credential-shaped string survived the redaction.

### Finding 3 — comments and freeform assignments

* Finding: a TOML comment was copied uninspected, and a freeform
  `ANTHROPIC_AUTH_TOKEN=<value>` assignment under an allowed text input was
  copied although its value carries no vendor prefix.
* Regressions (red before the fix):
  `test_toml_comment_with_credential_content_is_refused_without_artifacts` and
  `test_text_input_with_a_freeform_credential_assignment_is_refused`.
* Fix: a comment is inspected, and a `NAME=value` assignment whose name
  carries a credential word is credential content whatever its value looks
  like. The default policy refuses the rehearsal and writes no artifact; the
  omit policy drops the comment or the file and counts it. The projected TOML
  is re-emitted from the parsed values, so a comment is never carried into the
  projection at all.

### Finding 4 — an existing report path, including a hard link

* Finding: a report path that already existed — for example a hard link
  whose other name is a file in the source home — was accepted, and writing
  the report truncated the device-owned file through that link.
* Regressions (red before the fix):
  `test_an_existing_report_path_is_refused_and_the_source_file_is_untouched`
  and `test_a_report_inside_the_projection_is_refused_before_any_write`.
* Fix: the output boundary is settled before anything is read or written. The
  report path must not exist, must not live inside the source home or inside
  the projection, and every artifact is created with `O_EXCL`. The refusal
  happens before any write, so no device file is touched.

### Finding 5 — the fixtures used an aliased scratch path

* Finding: under an ordinary macOS `TMPDIR` the suite failed because the
  fixture root was an aliased path and the helper refused that symlink.
* Fix: the test fixture uses a canonical scratch root
  (`Path(temporary.name).resolve()`). The linked-path guards in the helper
  were **not** relaxed; a helper run with an aliased output path still
  refuses it.

### Red-before-fix evidence for this round

Command (bounded, single-threaded, no network):

```
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_existing_settings_rehearsal.py" -v
```

Red state, before any fix in this round — 24 tests, 7 failures, all of them
the new regressions:

```
FAIL: test_a_report_inside_the_projection_is_refused_before_any_write
FAIL: test_an_existing_report_path_is_refused_and_the_source_file_is_untouched
FAIL: test_malformed_toml_is_refused_before_any_artifact
FAIL: test_text_input_with_a_freeform_credential_assignment_is_refused
FAIL: test_toml_comment_with_credential_content_is_refused_without_artifacts
FAIL: test_toml_inline_table_with_a_credential_key_is_redacted
FAIL: test_toml_multiline_credential_is_redacted_and_the_projection_stays_valid_toml
Ran 24 tests in 6.791s
FAILED (failures=7)
```

Green state after the fixes — 24 tests, then 25 with the extra coverage test
added after the fix (no red-before-green claim is made for that one):

```
Ran 24 tests in 7.236s
OK
Ran 25 tests in 7.000s
OK
```

Fixture evidence for finding 5, with an aliased scratch root
(`TMPDIR` pointing at a symlink that resolves to a real directory):

| Fixture | Command result |
| --- | --- |
| aliased root, fixture not canonical | `Ran 24 tests … FAILED (failures=19)` |
| aliased root, fixture canonical | `Ran 24 tests … FAILED (failures=7)` (only the new regressions) |
| aliased root, fixture canonical, after the fixes | `Ran 25 tests … OK` |
| canonical root, after the fixes | `Ran 25 tests … OK` |

The linked-path guard itself is unchanged: a helper run whose output path
traverses the alias still refuses with exit 3 and the message
`the projection path is a symlink: …`.

### Public CLI scenarios (fabricated data only)

Run with `python3 deployment/rehearse_settings.py …` against fabricated
fixtures; the column records whether the fabricated private marker was still
present in any artifact:

| Scenario | Exit | Marker in an artifact | Refusal |
| --- | --- | --- | --- |
| TOML credential in a multi-line string | 0 | no | — |
| TOML credential-named key in an inline table | 0 | no | — |
| TOML comment holding a credential assignment | 5 | no | `unknown credential-shaped value in <path>` |
| the same, with `--unknown-credential-policy omit` | 0 | no | — |
| text input with a freeform credential assignment | 5 | no | `unknown credential-shaped value in <path>` |
| the same, with `--unknown-credential-policy omit` | 0 | no | — |
| report path that is an existing hard link to a device file | 3 | no | `the report path already exists` (the device file kept its bytes and mtime) |
| malformed TOML | 2 | no | `cannot parse <path> as TOML` |
| TOML value with a credential shape under an unknown key | 5 | no | `unknown credential-shaped value in <path>` |
| the same, with `--unknown-credential-policy omit` | 0 | no | — |

### Verification for this round

```
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_existing_settings_rehearsal.py"
# 25 tests, OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_codegraph.py"
# 9 tests, OK (2 skipped: pinned CodeGraph CLI / pinned MCP clients unavailable)

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_claude_model_preservation.py"
# 5 tests, OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_caveman.py"
# 2 tests, OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_agents.py"
# 14 tests, OK (3 skipped)

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_deployment.py"
# 20 tests, 2 failures (host scope, unchanged by this ticket)

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_macos.py"
# 7 tests, 1 failure + 2 skipped (host scope, unchanged by this ticket)
```

`tests/test_magpie.py` was **not** run in this round: no Magpie file changed,
and the suite fixes its fixtures under `/tmp`, which this sandbox refuses.
That is an environment limitation, not a pass.

The two `tests/test_deployment.py` failures
(`test_privileged_options_are_rejected_for_native_windows_plans`,
`test_privileged_options_reject_a_simulated_home_before_writing`) and the one
`tests/test_macos.py` failure
(`test_remote_editor_uses_selected_platform_and_managed_paths_with_literal_proxy`
for `platform='windows'`) are the same host-scope failures as in the first
round: they expect Linux/Windows-host behaviour and are unchanged by this
ticket, which touches no deployment, Magpie, or platform code.

### Corrected limitations after this round

* The report's `helper_version` moved from `1` to `2` because the projection
  semantics changed: TOML is now parsed and re-emitted, and the output paths
  must be new. The report schema is unchanged.

* The projected TOML is a re-serialization of the parsed device document:
  comments are dropped, an inline table becomes a table, and the byte layout
  of the device file is not reproduced. The settings values are preserved and
  the emitted TOML is validated, but the projection is not a byte copy.
* A TOML comment that names a credential assignment refuses the rehearsal
  under the default policy. A device file with such a comment (for example an
  example line in a comment) needs the operator's judgement or a narrower
  manifest; the rehearsal will not guess.
* The redaction is still name- and shape-based. A credential under a name
  that carries no credential word and under a shape that carries no known
  shape, in a freeform text file, is not detected. The freeform
  `NAME=value` rule narrows that gap but does not close it.
* The output boundary is now a new-output boundary: the report path must not
  exist and the projection directory must be empty or absent, so a rerun
  needs fresh paths. That is deliberate — it is what keeps an existing hard
  link from rewriting a device file.
* The safety argument is local and value-free: the helper refuses before it
  writes, and it validates the in-memory emitted structure — the redacted
  document it is about to serialize — so that no credential-named field and
  no credential-shaped string survived the redaction. The read that follows
  the write computes the projected checksum only; it is not a re-read for
  redaction. Nothing in this ticket reads a projected real setting as a
  redaction check, and the supervisor is not asked to do so.
* Nothing in this round read a live home setting, an auth store, a session,
  or a history file; no real-device projection was run; no commit was made.

## Follow-up round 2: the supervisor's two credential-boundary findings

The supervisor re-ran the public CLI against fabricated JSON and reproduced
two defects that the previous round's tests did not cover. Both are fixed
here, with a genuine red-before-fix regression at the public helper seam for
each. All fixtures are fabricated; no value appears in this report.

### Finding 6 — a quoted credential assignment inside a string

* Finding: a JSON settings file whose `command` value held a serialized
  object with a quoted credential assignment (`"ANTHROPIC_AUTH_TOKEN":"…"`)
  was projected with the credential still in it. The assignment rule matched
  `NAME=value` and `NAME: value`, but a quote between the name and the colon
  broke the match, so the string bypassed the check. The same held for a
  single-quoted mapping key (`'ANTHROPIC_AUTH_TOKEN': '…'`). A hook or MCP
  command can carry such a serialized object, so this is credential-bearing
  configuration inside the approved settings boundary.
* Regressions (red before the fix):
  `test_a_json_string_with_a_quoted_credential_assignment_is_refused` and
  `test_a_json_string_with_a_single_quoted_credential_key_is_refused`, plus
  `test_a_quoted_credential_assignment_is_omitted_with_a_count` for the omit
  policy.
* Fix: the assignment name may be wrapped in a single or double quote. The
  quote is treated as a delimiter only: the string is never parsed,
  evaluated, or executed, and the rule stays a name-and-shape check.

### Finding 7 — a URL that carries userinfo

* Finding: a JSON settings file whose `env` held a proxy URL with userinfo
  (`http://operator:password@host:port`) was projected with the password
  still in it. Userinfo is credential-bearing configuration in an ordinary
  proxy or endpoint field.
* Regressions (red before the fix):
  `test_a_url_with_userinfo_is_refused_before_artifacts`,
  `test_a_url_with_userinfo_is_omitted_with_a_count`, and
  `test_a_toml_endpoint_with_userinfo_is_refused_before_artifacts`.
* Fix: a URL whose authority carries userinfo is credential content. Under
  the default policy the rehearsal refuses before any artifact is written;
  under `--unknown-credential-policy omit` the affected string or field is
  omitted and counted. A URL without userinfo and a provider's
  environment-variable name are ordinary values and are preserved, which
  `test_ordinary_urls_and_environment_variable_names_are_preserved` pins.

### Red-before-fix evidence for this round

Command (bounded, single-threaded, no network):

```
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_existing_settings_rehearsal.py" -v \
  -k quoted_credential -k userinfo -k ordinary_urls
```

Red state, before any fix in this round — 7 tests, 6 failures, all of them
the new regressions (the preservation test was already green):

```
FAIL: test_a_json_string_with_a_quoted_credential_assignment_is_refused
FAIL: test_a_json_string_with_a_single_quoted_credential_key_is_refused
FAIL: test_a_quoted_credential_assignment_is_omitted_with_a_count
FAIL: test_a_toml_endpoint_with_userinfo_is_refused_before_artifacts
FAIL: test_a_url_with_userinfo_is_omitted_with_a_count
FAIL: test_a_url_with_userinfo_is_refused_before_artifacts
Ran 7 tests in 0.291s
FAILED (failures=6)
```

The failures were the reproduced defect: the helper exited `0` and the
fabricated marker was still in the projected file. The diagnostic output was
rewritten afterwards so that a failing assertion never echoes the projected
value: the assertions now report only whether the marker was present.

Green state after the fixes — the same 7 tests, then the whole focused suite:

```
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_existing_settings_rehearsal.py" -v \
  -k quoted_credential -k userinfo -k ordinary_urls
# Ran 7 tests in 0.292s — OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -m unittest discover -s tests -p "test_existing_settings_rehearsal.py" -v
# Ran 32 tests in 7.931s — OK

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) \
  python3 -m unittest discover -s tests -p "test_existing_settings_rehearsal.py"
# Ran 32 tests in 7.401s — OK (no skips)
```

### Public CLI scenarios (fabricated data only)

Run with `python3 deployment/rehearse_settings.py …` against fabricated
fixtures. The columns record the exit status, whether the fabricated marker
was present in any artifact (the projection files and the report), whether it
reached stdout or stderr, and whether the source file still held it:

| Scenario | Policy | Exit | Marker in an artifact | Marker in the diagnostics | Projection/report written |
| --- | --- | --- | --- | --- | --- |
| JSON string with a quoted credential assignment | fail (default) | 5 | no | no | no / no |
| the same | omit | 0 | no | no | yes / yes |
| JSON string with a single-quoted credential key | fail (default) | 5 | no | no | no / no |
| JSON env value with URL userinfo | fail (default) | 5 | no | no | no / no |
| the same | omit | 0 | no | no | yes / yes |
| TOML endpoint with URL userinfo | fail (default) | 5 | no | no | no / no |
| JSON ordinary URL and an environment-variable name | fail (default) | 0 | no | no | yes / yes |

Every refusal message named the input path and the reason only:
`dotfiles: rehearsal refused: unknown credential-shaped value in <path>;
refusing to project it`.

### Corrected limitations after this round

* The three statements the supervisor flagged are corrected in place above:
  the advice to read the projected files is withdrawn and superseded, the
  claim that the helper re-reads its own projection to prove redaction is
  replaced by the accurate description (the in-memory emitted structure is
  validated before the write; the post-write read computes the projected
  checksum only, and no redundant revalidation was added), and the input
  fingerprint wording now says what the code does — the checksum is taken
  over the bytes that were read, the mode and modification time are sampled
  just before the read, and the same fingerprint is taken again after the
  projection was computed. No race machinery was added.
* The new rules are still name- and shape-based and are deliberately not a
  generic secret detector. A credential named by something other than a
  credential word, held in a string whose shape carries no known shape, is
  still copied; the fail-closed default covers only the listed shapes.
* A quoted assignment name is recognized by its shape as a name followed by
  a colon or an equals sign. The string is never interpreted, so a value
  that merely mentions a credential word in prose is not a false positive,
  but a credential whose *name* is not a credential word inside a quoted
  assignment is not detected by this rule either.
* A URL is detected by its scheme and by an authority that carries userinfo.
  A username-only userinfo is treated as credential content as well, which
  is stricter than a password-only reading. The bare (scheme-less)
  `user:password@host:port` form is recognized; a scheme-less
  `user:password@host` without a port is not, and neither is a credential
  embedded in a URL in any other position.
* The helper's `helper_version` moved from `2` to `3` because the detection
  rules changed; the report schema is unchanged.
* The helper needs Python 3.11 or newer, because TOML is read with the
  standard-library `tomllib`. Nothing is installed for it, and the helper
  has no third-party dependency. The requirement is recorded in
  `docs/MACOS_DEPLOYMENT.md`.
* `docs/MACOS_DEPLOYMENT.md` no longer claims that the allow-listed
  rehearsal is the whole of gate item 2: it is described as the
  settings-slice component of that item, and the backed-up replacement of
  conflicting launcher/skill symlinks, the contents of unmanaged skills, the
  live client transport, and credentials stay open requirements. The closing
  paragraph of the rehearsal section now limits what is demonstrated to the
  allow-listed setting values and the fabricated symlink cases.
* Nothing in this round read a live home setting, an auth store, a session,
  or a history file; no real-device projection was run; no commit was made.
* No broad neighbouring suite was re-run in this round: only the focused
  rehearsal suite (32 tests, OK) was executed. The results of the other
  suites recorded in the earlier sections belong to those earlier rounds and
  were not repeated here; no claim is made about them now.

## Proposed commit message

```
[agents]: rehearse existing-device settings through a redacted projection

Add an operator helper that projects an explicitly allow-listed slice of an
existing device's managed settings into a private, redacted directory and
writes a value-free report with file/record counts and checksums. The helper
refuses authentication stores, session files, and history databases, refuses
linked input/output paths and a projection inside the source home, redacts
credential-named fields before it writes anything, and fails closed on
credential-shaped data under an unknown field name.

Add the reviewed input allow-list, the behaviour tests at the public helper
and public bootstrap seam, and the operator documentation of the rehearsal.
The device is only read: source bytes, permissions, and modification times
are preserved and recorded.

Parse every structured input before writing anything: JSON and JSONC are
parsed and re-emitted, and TOML is parsed, redacted as a structure, and
re-emitted as validated TOML, so a credential in a multi-line string or in an
inline table is redacted instead of copied. Fail closed on credential-shaped
content under an unknown field name, including a freeform `NAME=value`
assignment whose value carries no vendor prefix. Settle the output boundary
before the first write: the report path must not exist, the report must not
live inside the projection, and every artifact is created exclusively.

Also treat a quoted credential assignment inside a string and a URL that
carries userinfo as credential content, so a serialized hook command or a
proxy endpoint cannot carry a credential into the projection. The rules stay
name- and shape-based: the strings are never parsed or evaluated.

Co-Authored-By: Claude Code <noreply@anthropic.com>
```

(The trailer follows the repository convention of the surrounding commits; the
supervisor commits this branch and may adjust the attribution.)

## Attribution

Implemented by the Pi agent (ticket 11) under supervisor review, with
implement-spec and TDD: vertical red → green slices, no subagents, no nested
coding client, no live device access.
