# 08: DSH Magpie route with the official DeepSeek row preserved

**What to build:** The apply calls `magpie dsh group/workhorse` after the provider and group steps. This adds Magpie's route among DSH's custom providers and starts new sessions on it. DSH's `llm-deepseek` row (`~/.dsh/profiles/*/cordis.patch.yml`) must remain intact with its own settings, so selecting the DeepSeek row in DSH's Models page switches back. Add a verification step that reads the patched YAML and fails if `llm-deepseek` changed from the backup.

`dsh-tui` needs no wiring; it reads the DSH profile. `~/.dsh-tui/settings.json` stays device-owned and is never written.

**Blocked by:** 02, 07.

**Status:** ready-for-agent

- [ ] The apply calls `magpie dsh group/workhorse` exactly once.
- [ ] The fake-magpie test asserts no `magpie codex` and no direct write to `~/.dsh`.
- [ ] Backup and post-check compare the `llm-deepseek` entry and fail on change.
- [ ] `dotfiles-magpie status` reports DSH's group and the official-row preservation.

## Comments
