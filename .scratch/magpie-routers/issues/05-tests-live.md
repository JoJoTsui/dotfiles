# 05: Tests, docs and live acceptance

**What to build:** Finish the test suite and run the live acceptance:

1. `python3 -m unittest tests.test_magpie` passes with the new catalogs, the
   fake `visible`/`plugin` commands, the `:effort` grammar and the `test`
   command. Update the existing fake expectations and the t9k simulated apply.
2. Update `docs/MAGPIE.md`, `README.md`, the AGENTS invariant if needed, and
   the original `.scratch/magpie/spec.md` cross-reference for the five-catalog
   shape, the openai-stack order, `:effort`, `visible.tsv`, `plugins.tsv` and
   `dotfiles-magpie test`.
3. Live: re-apply the source, run `dotfiles-magpie apply`, and confirm:
   - `magpie provider test openai` passes (chat/responses).
   - `magpie group openai-stack` lists `group/chatgpt`, `openai/gpt-6.1-sol`,
     `openai/gpt-6.1-terra`, `kimi-code-cn/k3.1-pro:max`; `conductor` nests it.
   - `magpie visible claude` is `conductor,openai-stack`; `pi` and `dsh` are
     `workhorse`; the three agent pickers show the groups only.
   - `dotfiles-magpie test` reports OpenCode Go via `deepseek-v4.1-flash`.
   - `magpie plugin list` shows `@magpie-community/opencode-zed-auth@0.1.19` on;
     `magpie accounts zed --json` is empty until the human browser sign-in, so
     record `magpie plugin login zed` as the pending operator step.
   - Codex config hash unchanged and the official OpenCode/Kimi/MiniMax
     configs have no Magpie reference.

**Blocked by:** 01, 02, 03, 04.

**Status:** ready-for-agent

- [ ] Commands and redacted output are in the Comments.
- [ ] The three pickers show the groups only.
- [ ] OpenAI API is in the chain and tested.
- [ ] The Zed plugin is loaded; its sign-in is named as the only human step.
- [ ] Codex and the official agents are unchanged.

## Comments
