# 01. Publish Nushell completions safely

**What to build:** Make bootstrap and standalone refresh use a single Nushell completion publication module. After a failed refresh each active loader can still start Nu using a complete generation.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] The existing preparation and refresh commands publish to the loader paths active on their supported platforms.
- [ ] New generations validate before a live loader switches. An interrupted publication leaves every active loader usable, including when some loaders switched and others did not.
- [ ] Cleanup retires managed generations only after all managed loaders stop referencing them and preserves device-created files.
- [ ] Exercise normal publication, failed second publication, and retry with real Nu. Document the preserved startup contract.

## Comments

Codex review in progress. The draft retirement check searches for the raw
`str(entry)` inside loader source, but loader imports encode the path as a JSON
string. On Windows, escaped backslashes make the active generation invisible.
Derive the reference from the encoded import syntax or parse the generated
reference, and add a test for Windows-style paths that can also run off Windows.

Codex independently ran the 22 focused completion and real-Nu preparation
tests on macOS. The full unittest discovery loop is interrupted because that
suite assumes Linux for its cross-platform checks. Finish with the focused
suite and the Windows loader escaping regression. The integration supervisor
will run the main deployment gate.

Pi resumed the preserved draft diff and fixed the reviewer's finding. The
retirement check now derives its reference from the encoded import syntax:
`loader_imports` decodes the JSON string a loader stores for every import, and
`published_generation` matches the generation directory name as a path
component. A Windows path with escaped backslashes and a home name with a
quoted character therefore keep the generation they name, and an import the
module cannot decode keeps every generation.

Regressions `test_a_windows_style_import_keeps_the_generation_it_names` and
`test_a_quoted_home_name_keeps_the_generation_it_names` run on every platform
and both fail against the raw `str(entry)` matching.

The macOS preparation now selects the native vendor autoload loader and the
native user autoload loader, so the deployment's own discovery copy never
outlives the generation it imports. The startup contract is documented in
`docs/SHARED_SHELL_SETTINGS.md`, `docs/MACOS_DEPLOYMENT.md`,
`docs/DEPLOYMENT_BOUNDARY.md`, and the AGENTS.md invariants.

Checks on this Mac: `python3 -m unittest tests.test_nu_completions` (24
tests, OK) and `git diff --check` (clean). The full unittest discovery loop,
the native deployment gate, the Windows acceptance, and the package downloads
stay with the coordinator. The ticket stays open for the Codex review.
