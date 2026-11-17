# 05: Claude Code template moves to the Magpie gateway

**What to build:** Rewrite `deployment/client-settings/claude-settings.json.tmpl` so Claude Code uses Magpie: base URL `http://127.0.0.1:3425`, token `magpie`, `model` `group/conductor`, no `ANTHROPIC_MODEL`, no `ANTHROPIC_DEFAULT_*_MODEL`, no `ANTHROPIC_SMALL_FAST_MODEL`, no `CLAUDE_CODE_SUBAGENT_MODEL`. Keep `alwaysThinkingEnabled`, `ignorePatterns`, `enabledPlugins.serena`, and `DISABLE_AUTOUPDATER` as they are.

Determine the exact shape by running `magpie claude group/conductor` against a throwaway `CLAUDE_CONFIG_DIR` (with the real Magpie store) and transcribing its settings, so the template and Magpie agree field for field. Remove `glmBaseUrl`/`glmToken` from the template and from `.chezmoi.toml.tmpl`, and update the README/AGENTS references to them.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] Rendered settings contain the four Magpie fields and no `glm-` value.
- [ ] `policies.json` still owns only `env.DISABLE_AUTOUPDATER` and `enabledPlugins.serena`.
- [ ] `.chezmoi.toml.tmpl` no longer defines `glmBaseUrl`/`glmToken`; no template references them.
- [ ] `tests/test_claude_model_preservation.py` and client-settings tests pass.

## Comments
