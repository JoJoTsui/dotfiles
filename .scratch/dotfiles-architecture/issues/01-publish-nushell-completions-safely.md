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

The spec review found a second publisher after shell preparation. The macOS
catalog still lists nu-scripts.nu, and deploy_macos_config uses cp -p over the
active native loader after generation retirement. Remove that secondary writer
and make the publication module create the catalog's canonical user-autoload
path even in a fresh synthetic macOS home. Exercise the normal bootstrap
ordering as well as standalone refresh.

Also preserve the destination guard when extending it to native paths.
A lexical path outside HOME using an alias symlink that resolves into HOME
currently passes safe_destination and the write uses the alias. Require the
original destination relative to HOME (or its legitimate platform canonical
spelling) and check the actual path components written through. Add the alias
regression.

Pi fixed the loader ownership finding on `20c7823`.

The macOS preparation selected the native vendor autoload loader because that
directory existed. The directory is not the deployment's own: the macOS
catalog names the user autoload directory (`~/Library/Application Support/nushell/autoload`)
as the canonical native copy, and the vendor autoload directory only holds the
loader an earlier preparation mirrored into it. The selection therefore
overwrote a device `nu-scripts.nu` of the same name and created a duplicate
loader in a directory the catalog never declared.

Ownership now decides which loader a publication may write. A canonical loader
is owned by declaration: the XDG loader the deployment writes, plus the native
copy the platform's catalog names. A legacy loader path is taken over only when
the file on disk carries the managed marker; a device file of the same name is
preserved, an existing native directory is no reason to create a loader in it,
and a preserved loader keeps the generation it names, so the cleanup never
removes a generation under a live loader. The macOS preparation passes the
vendor autoload path as a legacy loader and the catalog user-autoload path as
a canonical one.

The other publication paths were reviewed. The Windows native appdata autoload
directory belongs to that deployment, which copies its own prepared startup
resources into it, so its loader stays canonical and is still published.

Regressions, all in `tests/test_nu_completions.py`: the module seam covers a
legacy loader that is taken over only when it is demonstrably managed, and a
preserved device loader that keeps the generation it names; the command seam
runs the real preparation and covers the canonical publication, a preserved
device loader of the same name, and a previously managed native loader that
follows the live generation. Each regression fails against the previous
behavior.

Checks on this Mac (Python 3.15.2, nu 0.117.0):
`python3 -m unittest tests.test_nu_completions` (28 tests, OK),
`git diff --check` (clean), and `sh -n dot_local/bin/executable_dotfiles-shell-prepare`
(ok). The full unittest discovery loop, the native deployment gate, the
Windows acceptance (this host has no PowerShell), and the package downloads
stay with the coordinator.

The second publisher and the alias destination guard reported above are not
addressed by this fix and stay open for the Codex review. The ticket stays
open.

Pi finished the second publisher and the discovery failure.

The macOS catalog mapped the pinned loader, so `deploy_macos_config` copied
the XDG loader over the active native loader after the publication and after
the generation retirement. The catalog no longer maps it: the completion
module is the only writer of the pinned loader, and the deployment's
discovery adapter is no longer a second publisher for it.

The macOS preparation now derives the native paths from the Nu discovery
command and falls back to the documented macOS directories when that command
fails. A discovery failure previously omitted the canonical native user
autoload path: the module stopped managing that loader, retired the
generation it imported, and left the native loader with missing imports. The
fallback keeps the path, so the loader stays published, its generation stays
complete, and the cleanup never removes a generation under a live loader.

The command seam now models a macOS home on every host: the canonical XDG
roots and the native autoload directories the catalog names. Regressions cover
the deployment's discovery adapter leaving the published loader alone, and a
discovery failure keeping the canonical native loader published across two
publications. Both fail against the previous behavior.

Checks on this Mac (Python 3.15.2, nu 0.117.0):
`python3 -m unittest tests.test_nu_completions` (30 tests, OK),
`git diff --check` (clean), and `sh -n dot_local/bin/executable_dotfiles-shell-prepare`
(ok). The full unittest discovery loop, the native deployment gate, the
Windows acceptance (this host has no PowerShell), and the package downloads
stay with the coordinator. The alias destination guard reported above stays
open for the Codex review. The ticket stays open.
