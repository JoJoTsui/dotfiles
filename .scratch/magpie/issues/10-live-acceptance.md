# 10: Live acceptance on this Mac

**What to build:** Run the deployment against this device and record the evidence in this ticket:

1. Back up `~/.claude/settings.json`, `~/.codex/config.toml`, `~/.pi/agent/settings.json`, `~/.pi/agent/models.json`, and every `~/.dsh/profiles/*/cordis.patch.yml` with a UTC timestamp; mode 0600.
2. `brew install --cask magpie` (adopt, do not reinstall if present), install the repo launcher, and run `magpie --version`.
3. Open the app once; confirm `magpie status --json` reports the gateway on `127.0.0.1:3425`.
4. Set the proxy to the resolved Clash URL and confirm `magpie settings get proxy`.
5. Add the four providers. Kimi requires `KIMI_CODE_CN_API_KEY` in `~/.config/dotfiles/magpie.env`; if absent, stop at this step and report the exact file and variable.
6. Create `chatgpt`, `conductor`, and `workhorse`; confirm the member order with `magpie group <id>`.
7. Apply the client settings so Claude Code uses `group/conductor`; let Magpie generate Pi's `models.json`; let Magpie add the DSH route.
8. Verify: `magpie provider test` for each provider; `curl --noproxy '*' -H 'Authorization: Bearer magpie' http://127.0.0.1:3425/v1/models`; one tiny completion through each group; `magpie group <id>` order.
9. Verify untouched: `~/.codex/config.toml` SHA-256 unchanged, `codex` still on ChatGPT `gpt-6-luna`; `~/.config/opencode/opencode.jsonc`, `~/.kimi-code/config.toml`, `~/.minimax/config.yaml` unchanged.
10. `git status` shows no credential file and no `REPLACE_ME` became a token.

**Blocked by:** 09.

**Status:** ready-for-agent

- [ ] Every command above has its output (redacted) pasted under Comments.
- [ ] Both groups answer one real completion, or the blocking provider is named with its error.
- [ ] Codex config hash matches the pre-apply value.
- [ ] Official OpenCode/Kimi/MiniMax config hashes match.
- [ ] `dotfiles-magpie status` exits 0.

## Comments
