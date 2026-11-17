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

**Status:** ready-for-agent

- [ ] The four catalogs validate; `openai` is an accepted preset.
- [ ] `:effort` resolves to `kimi-code-cn/k3.1-pro:max` in `openai-stack`.
- [ ] A bad effort fails by name; a `group/<id>:effort` member is rejected.
- [ ] Existing groups still resolve; the simulated t9k apply is unchanged.
- [ ] `tests/test_magpie.py` covers the new rows and the effort grammar.

## Comments
