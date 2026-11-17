# 01: OpenAI provider, openai-stack group and member effort

**What to build:** Add `openai` to `providers.tsv` (`env:OPENAI_API_KEY`), add
`openai.sol`/`openai.terra` to `models.tsv`, and replace the group catalog with
the four rows in the spec. `conductor` nests `group/openai-stack`; the stack
drains `group/chatgpt`, then the OpenAI API models, then
`conductor.kimi:max`. Teach `magpie_group_models_for` the `role:<effort>`
grammar: strip the suffix for the role lookup, validate it against
`none|minimal|low|medium|high|xhigh|max`, and append it to the resolved model
id. A bare role keeps Magpie's default.

**Blocked by:** none.

**Status:** done

- [x] The four catalogs validate; `openai` is an accepted preset.
- [x] `:effort` resolves to `kimi-code-cn/k3.1-pro:max` in `openai-stack`.
- [x] A bad effort fails by name; a `group/<id>:effort` member is rejected.
- [x] Existing groups still resolve; the simulated t9k apply is unchanged.
- [x] `tests/test_magpie.py` covers the new rows and the effort grammar.

## Comments

Implemented on branch `magpie-routers`.

- `providers.tsv` gains `openai|openai|env:OPENAI_API_KEY|yes`;
  `MAGPIE_PROVIDER_PRESETS` gains `openai`.
- `models.tsv` gains `openai.sol`/`openai.terra`; both ids are served by the
  live gateway (`/v1/models` shows `openai/gpt-6.1-sol`, `openai/gpt-6.1-terra`).
- `groups.tsv` becomes the four rows of the spec. `conductor` nests
  `group/openai-stack`, which drains `group/chatgpt`, then the OpenAI API
  models, then `conductor.kimi:max`.
- `magpie_member_split` owns the `role:<effort>` grammar: the effort must be
  one of `none|minimal|low|medium|high|xhigh|max`, is stripped for the role
  lookup and appended to every resolved model id. A `group/<id>:<effort>`
  member is rejected because a group keeps its own routing.
- The "a group holds a model role" rule became "a group reaches a model role"
  (`magpie_group_reaches_role`), because `conductor` now holds only a group.
  A cycle of group references reaches no role and is rejected.

Checks:

```
bash /tmp/magpie-check.sh            # validate + resolve the shipped catalogs
validate: ok
chatgpt -> codex/gpt-6.1-sol,codex/gpt-6.1-terra
openai-stack -> group/chatgpt,openai/gpt-6.1-sol,openai/gpt-6.1-terra,kimi-code-cn/k3.1-pro:max
conductor -> group/openai-stack
workhorse -> minimax-cn/MiniMax-M3.1-Flash,opencode-go/deepseek-v4.1-flash

DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest tests.test_magpie
Ran 77 tests ... OK

DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh --source "$PWD" \
  --home "$sim" --class t9k --apply-only   # exit 0
DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh --source "$PWD" \
  --home "$sim" --class linux --apply-only # exit 0
```
