# 03: Pinned Magpie plugin catalog

**What to build:** `deployment/magpie/plugins.tsv` with
`zed|@magpie-community/opencode-zed-auth|0.1.19|yes`. The apply reads
`magpie plugin list --json` (`.loaded[].spec`), installs an absent package with
`magpie plugin add npm:@magpie-community/opencode-zed-auth@0.1.19`, and runs
`magpie plugin on <name>` when the package is loaded but off. It never signs
in, never updates a present plugin, and reports `plugin|zed|loaded|missing` in
`status`. This plugin is community-owned; the repository only pins and installs
it.

**Blocked by:** 01.

**Status:** done

- [x] The catalog validates a version and rejects a credential-looking source.
- [x] The fake Magpie reports an empty `loaded` list, and the apply installs the
      pinned `npm:` reference once.
- [x] A present plugin is not installed or updated again.
- [x] `status` reports the plugin state, and `docs/MAGPIE.md` says the sign-in
      is `magpie plugin login zed` or the app's Plugins page.
- [x] The live host already has 0.1.19 loaded, so the first live apply is a no-op
      for this step.

## Comments

- `deployment/magpie/plugins.tsv` ships
  `zed|@magpie-community/opencode-zed-auth|0.1.19|yes`, with the matching
  `{{ include }}` wrapper for the managed command.
- The apply reads `magpie plugin list --json` once and maps `.loaded[].spec`
  and `.plugins[].spec` to the package name, so a version drift still counts
  as present and is never reinstalled or updated. Absent →
  `magpie plugin add npm:<source>@<version>`; installed but off →
  `magpie plugin on <name>`. The step runs before the providers.
- `status` prints `plugin|zed|loaded`, `off`, or `missing`; `off` and `missing`
  are a failing status.
- No sign-in is attempted. `docs/MAGPIE.md` names `magpie plugin login zed`
  and the app's Plugins page as the operator's step.

Checks:

```
bash /tmp/plugin-check.sh        # read-only, against the live gateway
loaded|@magpie-community/opencode-zed-auth@0.1.19
package of pinned: @magpie-community/opencode-zed-auth
state of pinned: loaded
state of absent: (nothing)

DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest tests.test_magpie
Ran 97 tests ... OK

simulated t9k and linux applies: exit 0, no catalog in the home
```
