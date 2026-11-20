# 08: DSH Magpie route with the official DeepSeek row preserved

**What to build:** The apply calls `magpie dsh group/workhorse` after the provider and group steps. This adds Magpie's route among DSH's custom providers and starts new sessions on it. DSH's `llm-deepseek` row (`~/.dsh/profiles/*/cordis.patch.yml`) must remain intact with its own settings, so selecting the DeepSeek row in DSH's Models page switches back. Add a verification step that reads the patched YAML and fails if `llm-deepseek` changed from the backup.

`dsh-tui` needs no wiring; it reads the DSH profile. `~/.dsh-tui/settings.json` stays device-owned and is never written.

**Blocked by:** 02, 07.

**Status:** done

- [x] The apply calls `magpie dsh group/workhorse` exactly once.
- [x] The fake-magpie test asserts no `magpie codex` and no direct write to `~/.dsh`.
- [x] Backup and post-check compare the `llm-deepseek` entry and fail on change.
- [x] `dotfiles-magpie status` reports DSH's group and the official-row preservation.

## Comments

The wiring step already ran `magpie dsh group/workhorse` after the providers
and the groups. This ticket adds the guard around it.

`magpie_dsh_official_row` reads the `llm-deepseek` entry of a DSH profile
patch. The patch is a YAML list of entries, and the entry is the one whose id
is `llm-deepseek`; the deployment reads it and never writes it. After the
wiring, `magpie_dsh_verify_official_row` compares that entry with the copy in
the backup the apply took before it changed anything, and a difference fails
the run with the profile named. Magpie's own route is a different entry, so
the official row keeps its own settings and the DeepSeek entry in DSH's
Models page still switches back.

`~/.dsh/profiles/*/cordis.patch.yml` is never written by the deployment: the
backup copies it, the verification reads it, and nothing else touches it.
`dsh-tui` needs no wiring because it reads the DSH profile, and
`~/.dsh-tui/settings.json` stays device-owned.

`dotfiles-magpie status` reports the DSH wiring from the catalog and the state
of the official row of every profile: `present`, `absent`, or `changed` when a
backup holds a different entry.

Tests run:

- `python3 -m unittest test_magpie -v` — 50 tests, all pass. The new checks
  assert that the apply leaves the DSH patch byte-identical and issues no
  `codex` command, that a fake Magpie which rewrites the official row makes
  the apply fail with the profile named, and that the status reports the DSH
  group and the official row.
