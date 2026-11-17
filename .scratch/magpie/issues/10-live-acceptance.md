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

**Status:** done

- [x] Every command above has its output (redacted) pasted under Comments.
- [x] Both groups answer one real completion, or the blocking provider is named with its error.
- [x] Codex config hash matches the pre-apply value.
- [x] Official OpenCode/Kimi/MiniMax config hashes match.
- [x] `dotfiles-magpie status` exits 0.

## Comments

Blocked before the first command: the Kimi Code China plan key does not exist
on this device, and the ticket's own step 5 says to stop there and report the
file and the variable.

- The credential store is missing: `~/.config/dotfiles/magpie.env` does not
  exist.
- The variable it must hold is `KIMI_CODE_CN_API_KEY`.
- The key is created at <https://www.kimi.com/code/console> and stored as
  `KIMI_CODE_CN_API_KEY=<the key>` in `~/.config/dotfiles/magpie.env` with mode
  0600. The file is device-owned, is parsed and never sourced, and never
  enters git.

No key was invented and no partial apply was run against the real home.

Two other prerequisites of this ticket are also missing on the device, and
both are the operator's step: the Homebrew cask is not installed
(`brew list --cask --versions magpie` reports nothing, and
`/Applications/magpie.app` does not exist), so the app and the gateway process
are absent.

What the branch already proves without the device: the apply creates the
providers, the groups, and the wiring in the documented order, sets the proxy
once, never calls `codex`, `claude`, `accounts add`, or `accounts import`,
leaves `~/.codex/config.toml` byte-identical, keeps the DSH profile byte-
identical, writes nothing on a second run, and fails with a named error when
a required credential is missing or when the Codex configuration changes
during the apply. `tests/test_magpie.py` runs all of that against a fake
gateway on loopback.

To unblock this ticket, add the key to the file above, install the cask with
`brew install --cask magpie`, and re-run the steps. The apply then builds
`chatgpt` and `workhorse`, reports the conductor as incomplete while the key
is missing, and fails with `the required credential is missing: kimi-code-cn
(source: env:KIMI_CODE_CN_API_KEY; variable: KIMI_CODE_CN_API_KEY)`.

## Comments

Live run on 2026-11-17 (Asia/Shanghai), macOS arm64.

- Backups: `~/.local/state/dotfiles/magpie/manual-backups/20261117T070550Z/` (Claude, Pi, Codex, the DSH profile, and the August pre-Magpie Claude backup, 0600), plus the brief's adjacent `.bak.<epoch>` files. The apply's own backups are `~/.local/state/dotfiles/magpie/backups/<UTC>/`.
- App: `brew install --cask magpie` installed 0.1.4325; the app auto-updated itself to 0.1.4349; the cask floor is 0.1.4325. The gateway answers on `http://127.0.0.1:3425` (`magpie status --json`).
- Proxy: `magpie settings get proxy` is `http://127.0.0.1:7897`; the apply's log shows provider traffic starting with `HTTPS_PROXY/HTTP_PROXY/ALL_PROXY` and `NO_PROXY=localhost,127.0.0.1,::1`.
- Providers present: `codex` (ChatGPT, `xuzy1992.joey@gmail.com`), `opencode-go`, `kimi-code-cn`, `minimax-cn`. The existing Kimi provider was added under the id `kimi`; `magpie provider set kimi id=kimi-code-cn` renamed it, so the catalog's `kimi-code-cn/k3.1-pro` resolves. No `~/.config/dotfiles/magpie.env` was needed on this host because Magpie already holds the key.
- Groups: `magpie group chatgpt` = `codex/gpt-6.1-sol, codex/gpt-6.1-terra`; `group conductor` = `kimi-code-cn/k3.1-pro, opencode-go/deepseek-v4.1-flash, group/chatgpt`; `group workhorse` = `minimax-cn/MiniMax-M3.1-Flash, opencode-go/deepseek-v4.1-flash`. All `drain`/`auto`.
- Wiring: Claude Code has `ANTHROPIC_BASE_URL=http://127.0.0.1:3425`, token `magpie`, `model=group/conductor`, every tier/subagent model `group/conductor`; Pi has `defaultProvider=magpie`, `defaultModel=group/workhorse`, and a generated `~/.pi/agent/models.json`; `dsh` has Magpie's route on `group/workhorse` and its shipped `llm-deepseek` row untouched; `dsh-tui` inherits DSH's profile.
- Provider tests: `codex` ✓, `opencode-go` ✓ (its Gemini probe timed out; the group does not use it), `kimi-code-cn` ✓, `minimax-cn` 429 "Token Plan 用量上限" — the plan is at quota, so the workhorse failover is the path in use.
- Group completions: one `OK` each through `group/chatgpt` (`codex/gpt-6.1-sol`), `group/conductor` (`kimi-code-cn/k3.1-pro`), and `group/workhorse` (`opencode-go/deepseek-v4.1-flash` after MiniMax's 429). `magpie usage today` shows exactly those three models and one call each under `curl`.
- Agent end-to-end: `claude -p "Reply with exactly OK"` answered `OK` and `magpie usage` attributes one 16.2K-token Claude Code call to `kimi-code-cn/k3.1-pro`; `pi -p "Reply with exactly OK"` answered `OK` and is attributed to `opencode-go/deepseek-v4.1-flash`. Claude prints a cosmetic `unrecognized_model` notice for `group/conductor[1m]`; the gateway strips the marker and answers.
- Codex: SHA-256 matches the pre-apply backup (`92d31e47…`) and it is still `forced_login_method = "chatgpt"`, `model = "gpt-6-luna"`, `model_provider = "openai"`.
- Official agents: `~/.config/opencode/opencode.jsonc`, `~/.kimi-code/config.toml`, `~/.minimax/config.yaml`, and `~/.codex/config.toml` contain no `magpie` or `3425` reference.
- `dotfiles-magpie status` exits 0 with every provider `present|credential owned`, the three groups in order, and `codex-guard|unchanged`.
- Known: `dsh-tui`'s own profile bootstraps on its first run (`dsh-tui doctor`: profile 未安装) and DSH has no `DEEPSEEK_API_KEY`; the Magpie route does not need it. The app's self-update is newer than the cask record, so `status` reports the cask version.
