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

**Status:** done

- [x] Commands and redacted output are in the Comments.
- [x] The three pickers show the groups only.
- [x] OpenAI API is in the chain and tested.
- [x] The Zed plugin is loaded; its sign-in is named as the only human step.
- [x] Codex and the official agents are unchanged.

## Comments

### Tests

```
DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest tests.test_magpie
Ran 104 tests ... OK

# the simulated applies, hermetic skill library (see the network note below)
DOTFILES_SKILLS_DIR=$PWD/tests/fixtures/skill-library DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) \
  bash bootstrap.sh --source "$PWD" --home "$sim" --class t9k --apply-only    # exit 0
DOTFILES_SKILLS_DIR=$PWD/tests/fixtures/skill-library DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) \
  bash bootstrap.sh --source "$PWD" --home "$sim" --class linux --apply-only  # exit 0
```

Both simulated homes render no gateway value, and no catalog reaches them.

Network note: the same applies without `DOTFILES_SKILLS_DIR` now fail in
`apply-source.skills`, because this host cannot reach github.com
(`LibreSSL SSL_connect: SSL_ERROR_SYSCALL`) for the upstream skill bytes.
The same outage made `python3 tests/native_macos.py --arch aarch64 --role
workstation` fail in `install-agents.dsh-tui.install`
(`UNKNOWN_CERTIFICATE_VERIFICATION_ERROR downloading tarball wrap-ansi@7.0.0`).
Both failures are network scope, not code scope; the branch touches no agent
installer and no skill catalog.

`tests/test_deployment.py` has two failures on this macOS host
(`test_privileged_options_*`): they are the documented Linux-suite scope, and
they fail the same way on `main`.

### Docs

- `docs/MAGPIE.md`: the catalogs section now covers the six catalogs, the
  `role:<effort>` grammar, the visibility narrowing, the pinned plugin and its
  sign-in, the new apply steps, and `dotfiles-magpie test`.
- `README.md`: the model gateway section names the six catalogs, the
  conductor's new chain, the plugin pin and the `test` command.
- `AGENTS.md`: the Magpie invariant names the six catalogs, the narrowing
  rule (no `--only-picked`, no stars) and the plugin sign-in.
- `.scratch/magpie/spec.md`: a cross-reference note records what the router
  refresh changed (groups, `visible.tsv`, `plugins.tsv`, `test`), and the Zed
  plugin's out-of-scope bullet points at the pin.

### Live acceptance

Source re-applied to the real home, then the gateway applied:

```
bash bootstrap.sh --apply-only          # exit 0; six catalogs in ~/.config/dotfiles/magpie
dotfiles-magpie apply                   # exit 0
```

`dotfiles-magpie apply` created `openai-stack`, updated `conductor` to hold
it, and narrowed the three agents. It changed no provider (all five are
present), installed no plugin (0.1.19 is loaded), and reported the Codex
configuration unchanged.

`dotfiles-magpie status` (exit 0):

```
gateway|http://127.0.0.1:3425|answers
proxy|http://127.0.0.1:7897
cask|magpie|0.1.4325
provider|chatgpt|present|credential owned
provider|opencode-go|present|credential owned
provider|kimi-code-cn|present|credential owned
provider|minimax-cn|present|credential owned
provider|openai|present|credential owned
plugin|zed|loaded
group|chatgpt|codex/gpt-6.1-sol,codex/gpt-6.1-terra
group|openai-stack|group/chatgpt,openai/gpt-6.1-sol,openai/gpt-6.1-terra,kimi-code-cn/k3.1-pro:max
group|conductor|group/openai-stack
group|workhorse|minimax-cn/MiniMax-M3.1-Flash,opencode-go/deepseek-v4.1-flash
wiring|claude|group/conductor
wiring|pi|group/workhorse
wiring|dsh|group/workhorse
wiring|dsh-tui|-
visible|claude|conductor,openai-stack
visible|pi|workhorse
visible|dsh|workhorse
dsh-official-row|desktop|absent
dsh-official-row|dsh-tui|absent
codex-guard|unchanged
```

The groups, live:

```
$ magpie group openai-stack
  openai-stack  group/openai-stack
  routing   drain
  stays     auto
  models    1 group/chatgpt  routing group chatgpt · drain · codex/gpt-6.1-sol, codex/gpt-6.1-terra
            2 openai/gpt-6.1-sol  OpenAI · GPT-6.1 Sol
            3 openai/gpt-6.1-terra  OpenAI · GPT-6.1 Terra
            4 kimi-code-cn/k3.1-pro:max  Kimi Code · K3.1 Pro · max reasoning, whatever the agent asks

$ magpie group conductor
  conductor  group/conductor
  routing   drain
  stays     auto
  models    1 group/openai-stack  routing group openai-stack · drain · group/chatgpt, openai/gpt-6.1-sol, openai/gpt-6.1-terra, kimi-code-cn/k3.1-pro:max
  used by   Claude Code
```

The visibility, live:

```
$ magpie visible
  claude        conductor, openai-stack  2 shown, 54 not
  dsh           workhorse  1 shown, 55 not
  pi            workhorse  1 shown, 55 not
```

`magpie models claude|pi|dsh` shows only the routing groups of each agent
(`group/conductor` and `group/openai-stack` for Claude, `group/workhorse` for
Pi and DSH) and lists every other model as "kept … in none of those". The
three pickers show the groups only.

The role probe, live (`dotfiles-magpie test`, exit 0, 17.9 s):

```
role|model|state|detail
chatgpt.sol|codex/gpt-6.1-sol|ok|3180
chatgpt.terra|codex/gpt-6.1-terra|ok|1583
openai.sol|openai/gpt-6.1-sol|ok|5321
openai.terra|openai/gpt-6.1-terra|ok|3176
conductor.kimi|kimi-code-cn/k3.1-pro|ok|1696
conductor.deepseek|opencode-go/deepseek-v4.1-flash|ok|1282
workhorse.minimax|minimax-cn/MiniMax-M3.1-Flash|ok|1209
```

OpenCode Go is probed through `opencode-go/deepseek-v4.1-flash`, never
through its Gemini endpoint. The OpenAI API is in the chain and answers.

The provider-level probe, live:

```
$ magpie provider test openai
  ✓ chat       2559 ms · gpt-5-search-api
  ✗ responses  400 · The requested model 'gpt-5-search-api' is not supported with the Responses API.
```

The chat half passes; the responses half fails because the probe picked
`gpt-5-search-api`, a search model the Responses API does not serve. That is
a property of the model the probe chose, not of the key or the gateway: the
models the router uses (`openai/gpt-6.1-sol`, `openai/gpt-6.1-terra`) pass
through `/v1/chat/completions` in the role probe above. The probe takes no
model argument, which is why `dotfiles-magpie test` exists.

The plugin and the sign-in:

```
$ magpie plugin list --json | jq '.loaded[] | select(.spec|test("zed"))'
{"spec":"@magpie-community/opencode-zed-auth@0.1.19","provides":["zed"]}

$ magpie accounts zed --json | jq '.[0] | {agent, user, plan, active, on}'
{"agent":"plugin:zed","user":"JoJoTsui","plan":"Student","active":true,"on":true}
```

The plugin is loaded and on, and this host is already signed in: Magpie's
`plugin-auth.json` holds an oauth token for `zed`, and the account is
reported as active. The brief called the sign-in pending; the live device
says otherwise, and no sign-in was attempted by the deployment or by me. On a
host without it, the single human step is:

```bash
magpie plugin login zed     # or the app's Plugins page
```

Codex and the official agents, live:

```
$ shasum -a 256 ~/.codex/config.toml
92d31e478306c72ce7813cc5ff4aba36586ff3f989fe2f9ba6fc5e2efe32df2a  /Users/joey/.codex/config.toml
# unchanged before and after the apply

~/.config/opencode/opencode.json    clean
~/.config/opencode/opencode.jsonc   clean
~/.kimi-code/config.toml            clean
~/.minimax/config.yaml              clean
~/.minimax/channel-routes.yaml      clean
```

No official agent configuration carries a Magpie reference, and the DSH
profiles' official DeepSeek row is unchanged (`dsh-official-row|*|absent`,
absent before the apply as well).

A second `dotfiles-magpie apply` is a no-op: the plugin is loaded, the groups
hold, the agents are shown, and the recorded state is current — nothing was
written.

One guard was added after the review: an unreadable plugin list is not an
absent plugin, so the apply now fails by name instead of installing on a
guess. `magpie plugin add` was never run on this device — the plugin was
already loaded, and the deployment never signs in.
