# 05: Claude Code template moves to the Magpie gateway

**What to build:** Rewrite `deployment/client-settings/claude-settings.json.tmpl` so Claude Code uses Magpie: base URL `http://127.0.0.1:3425`, token `magpie`, `model` `group/conductor`, no `ANTHROPIC_MODEL`, no `ANTHROPIC_DEFAULT_*_MODEL`, no `ANTHROPIC_SMALL_FAST_MODEL`, no `CLAUDE_CODE_SUBAGENT_MODEL`. Keep `alwaysThinkingEnabled`, `ignorePatterns`, `enabledPlugins.serena`, and `DISABLE_AUTOUPDATER` as they are.

Determine the exact shape by running `magpie claude group/conductor` against a throwaway `CLAUDE_CONFIG_DIR` (with the real Magpie store) and transcribing its settings, so the template and Magpie agree field for field. Remove `glmBaseUrl`/`glmToken` from the template and from `.chezmoi.toml.tmpl`, and update the README/AGENTS references to them.

**Blocked by:** 02.

**Status:** done

- [x] Rendered settings contain the four Magpie fields and no `glm-` value.
- [x] `policies.json` still owns only `env.DISABLE_AUTOUPDATER` and `enabledPlugins.serena`.
- [x] `.chezmoi.toml.tmpl` no longer defines `glmBaseUrl`/`glmToken`; no template references them.
- [x] `tests/test_claude_model_preservation.py` and client-settings tests pass.

## Comments

`deployment/client-settings/claude-settings.json.tmpl` now names the gateway
only: `ANTHROPIC_BASE_URL` is `http://127.0.0.1:3425`, `ANTHROPIC_AUTH_TOKEN`
is `magpie`, and `model` is `group/conductor`. Every model-selecting variable
is gone — `ANTHROPIC_MODEL`, the four `ANTHROPIC_DEFAULT_*_MODEL` variables and
their names, `ANTHROPIC_SMALL_FAST_MODEL`, and `CLAUDE_CODE_SUBAGENT_MODEL` —
so the gateway picks the model from the group. `alwaysThinkingEnabled`,
`ignorePatterns`, `enabledPlugins.serena`, `DISABLE_AUTOUPDATER`,
`API_TIMEOUT_MS` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` stay as they
were. The template carries no template variable any more, so the rendered
settings are the same bytes on every host.

The template was not transcribed from a live `magpie claude` run: the Magpie
app is not installed on this device, and the spec forbids running
`magpie claude` from the deployment. The field list comes from the spec's
Claude Code section instead.

`glmBaseUrl` and `glmToken` are gone from `.chezmoi.toml.tmpl`, from the
template, from `README.md`, and from the template-data list in `AGENTS.md`.
The legacy T9K adapters keep their own GLM wiring; this change does not touch
them. `deployment/update_versions.py` still scrubs `GLM_API_TOKEN` from the
environment it passes on, which is harmless and stays.

Two existing tests changed with the template: the Windows apply test now
expects the rendered `ANTHROPIC_AUTH_TOKEN` to be `magpie`, and the literal
credential test expects the Claude token and base URL to be the gateway
values. The kimi assertions in the literal test still prove that a value with
quotes, a backslash, a newline and a command substitution is rendered as
data.

The merge never removes a device key, so a host whose Claude environment still
names the GLM models keeps them. Clearing those keys once is the operator's
step; `docs/MAGPIE.md` says so.

Tests run:

- `python3 -m unittest test_magpie -v` — 42 tests, all pass, including the
  new client-settings checks: the template carries the four Magpie fields and
  no `glm-` value, the policy still owns only its two paths, no template
  carries the GLM data, and a simulated macOS apply renders the gateway
  values.
- `python3 -m unittest test_agent_payload test_claude_model_preservation test_codegraph` —
  31 tests, 6 skipped (the skips need PowerShell or a runtime this host does
  not have), all pass.
