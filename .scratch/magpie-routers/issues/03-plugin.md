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

**Status:** ready-for-agent

- [ ] The catalog validates a version and rejects a credential-looking source.
- [ ] The fake Magpie reports an empty `loaded` list, and the apply installs the
      pinned `npm:` reference once.
- [ ] A present plugin is not installed or updated again.
- [ ] `status` reports the plugin state, and `docs/MAGPIE.md` says the sign-in
      is `magpie plugin login zed` or the app's Plugins page.
- [ ] The live host already has 0.1.19 loaded, so the first live apply is a no-op
      for this step.

## Comments
