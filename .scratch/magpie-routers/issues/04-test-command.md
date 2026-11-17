# 04: dotfiles-magpie test by model role

**What to build:** Add `test [role…]` to `dotfiles-magpie`. For each requested
role (default: every role in `models.tsv`), resolve the first candidate that
`/v1/models` serves, send one `max_tokens: 16` completion to
`/v1/chat/completions` with `Authorization: Bearer magpie`, and print
`role|model|ok|<ms>` or `role|model|error|<message>`. This tests OpenCode Go
through `opencode-go/deepseek-v4.1-flash`, never through its Gemini API.
`jq` is already a common tool. Exit non-zero if any role fails.

**Blocked by:** 01.

**Status:** done

- [x] `dotfiles-magpie test conductor.deepseek` sends
      `opencode-go/deepseek-v4.1-flash` and reports ok.
- [x] A missing role or a role with no live candidate fails by name.
- [x] The command never calls `magpie provider test`.
- [x] `docs/MAGPIE.md` describes the command and its small token cost.
- [x] A fake completion endpoint test covers ok, error and an unknown role.

## Comments

- `magpie_test` and `magpie_test_role` live in the engine, so the managed
  command and the deployment run the same probe. `dotfiles-magpie test
  [role…]` resolves each role against `GET /v1/models`, takes the first
  candidate the gateway serves, and sends one `max_tokens: 16` turn to
  `/v1/chat/completions` with `Authorization: Bearer magpie`.
- The report starts with `role|model|state|detail`; a success is
  `role|model|ok|<ms>`, a failure `role|model|error|<message>` with the
  gateway's own message, and a role with no live candidate
  `role|-|error|no candidate the gateway serves`. Any failure exits non-zero.
- `magpie provider test` is never called: it reports a provider's own
  endpoints, not the model the routers hold, which is how OpenCode Go's Gemini
  endpoint was probed before.

Checks:

```
bash /tmp/test-check.sh          # the engine probe against the live gateway
role|model|state|detail
conductor.deepseek|opencode-go/deepseek-v4.1-flash|ok|53708
exit=0

DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest tests.test_magpie
Ran 102 tests ... OK

simulated t9k and linux applies: exit 0
```
