# 04: dotfiles-magpie test by model role

**What to build:** Add `test [role…]` to `dotfiles-magpie`. For each requested
role (default: every role in `models.tsv`), resolve the first candidate that
`/v1/models` serves, send one `max_tokens: 16` completion to
`/v1/chat/completions` with `Authorization: Bearer magpie`, and print
`role|model|ok|<ms>` or `role|model|error|<message>`. This tests OpenCode Go
through `opencode-go/deepseek-v4.1-flash`, never through its Gemini API.
`jq` is already a common tool. Exit non-zero if any role fails.

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] `dotfiles-magpie test conductor.deepseek` sends
      `opencode-go/deepseek-v4.1-flash` and reports ok.
- [ ] A missing role or a role with no live candidate fails by name.
- [ ] The command never calls `magpie provider test`.
- [ ] `docs/MAGPIE.md` describes the command and its small token cost.
- [ ] A fake completion endpoint test covers ok, error and an unknown role.

## Comments
