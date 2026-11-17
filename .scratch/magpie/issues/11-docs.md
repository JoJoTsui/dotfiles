# 11: Docs, ADR and glossary

**What to build:**

- `docs/MAGPIE.md`: ownership table, install/adopt, the switch and its default, the four catalogs, the apply order, provider credential sources, the Kimi key procedure, proxy behaviour, group semantics, rollback, and the non-macOS story.
- `docs/adr/0014-magpie-owns-the-model-gateway.md`: the ownership split — deployment owns intent and hand-written config, Magpie owns credentials, usage and generated agent artifacts. Include the rejected alternative (letting Magpie write every agent config) and why.
- `GLOSSARY.md`: model gateway, model provider, routing group, drain, agent wiring, installation provider. Keep the two "provider" meanings explicitly separate.
- `AGENTS.md`: one invariant for Magpie ownership and the Codex no-write rule.
- `README.md`: catalog table entries for `deployment/magpie/*` and `deployment/agents/{dsh,dsh-tui}`, and the `KIMI_CODE_CN_API_KEY` variable.
- `docs/AGENT_INSTALLATION.md`: the two new agents, their pins and commands.
- `docs/AGENT_SETTINGS.md`: Claude Code and Pi now use the Magpie gateway; models.json is Magpie-owned.

**Blocked by:** 03, 04, 05, 06, 07, 08.

**Status:** ready-for-agent

- [ ] Every new file path and command in the docs exists and runs.
- [ ] `GLOSSARY.md` never uses "provider" alone where the meaning matters.
- [ ] The ADR is one paragraph plus the rejected option, numbered 0014.
- [ ] `rg -n 'glmToken|glmBaseUrl'` returns only intentional historical references.
- [ ] Docs mention that Codex is never written and how to verify it.

## Comments
