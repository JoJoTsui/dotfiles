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

**Status:** done

- [x] Every new file path and command in the docs exists and runs.
- [x] `GLOSSARY.md` never uses "provider" alone where the meaning matters.
- [x] The ADR is one paragraph plus the rejected option, numbered 0014.
- [x] `rg -n 'glmToken|glmBaseUrl'` returns only intentional historical references.
- [x] Docs mention that Codex is never written and how to verify it.

## Comments

`docs/MAGPIE.md` is the new home of the gateway's contract: the ownership
table, the cask adoption and the two managed commands, the switch and its
default, the field contract of the four catalogs, the apply order, the three
credential sources, the Kimi Code China key procedure, the proxy behaviour,
the group semantics, the rollback with the timestamped backups, and the story
for the platforms that cannot run Magpie.

`docs/adr/0014-magpie-owns-the-model-gateway.md` already carried the decision
with the spec and matches the implementation: the repository owns the intent,
Magpie owns the credentials and the generated state, and Codex's configuration
belongs to neither. The rejected option — letting Magpie's agent adapters
write every client config — and the two other rejected options stay in the
record, and the consequences name the Codex hash guard.

`GLOSSARY.md` already carried the terms the spec introduced: model gateway,
model provider, routing group, drain, agent wiring, model catalog, and
installation provider, each with the "provider" ambiguity named in its avoid
list. No term needed a change, and the two meanings of "provider" stay
separate.

`AGENTS.md` gains one invariant: the Magpie model gateway owns the credentials
and the generated agent files, the deployment owns the catalogs and the
hand-written settings, and Codex's configuration belongs to neither — no code
path calls `magpie codex`, and every apply hashes the Codex configuration
before and after its changes. The secrets section names the device-owned
credential store and the rule that a credential never enters a log, a report,
or a ticket comment.

`README.md` lists `deployment/magpie/` in the layout, adds the `dsh` and
`dsh-tui` rows to the coding agent table with their pins and their local-only
state, points the Claude Code and pi rows at the gateway, names
`KIMI_CODE_CN_API_KEY` and the device file that holds it, and adds a short
model gateway section.

`docs/AGENT_INSTALLATION.md` names the two new agents with their packages,
versions, Node floors, and commands, and says why they have no Herdr kind and
why `pnpm` is a pinned common tool. `docs/AGENT_SETTINGS.md` records that
Claude Code and pi use the gateway, that Pi's `models.json` is Magpie-owned,
and that the official OpenCode, Kimi Code, MiniMax Code, and Codex
configurations stay byte for byte alone.

Checks run:

- `rg -n 'glmToken|glmBaseUrl'` — only the test assertions that require the
  data to be gone; the templates, the config, the README, and `AGENTS.md`
  carry no GLM data.
- Every path and command named in the new docs exists: `docs/MAGPIE.md`,
  `deployment/magpie/`, `deployment/agents/{dsh,dsh-tui}/`,
  `dot_local/bin/executable_dotfiles-magpie`,
  `dot_local/bin/executable_magpie`, `~/.config/dotfiles/magpie.env`, and the
  `magpie` cask, which `brew info --cask magpie` reports at 0.1.4325.
