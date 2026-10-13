# 05: Deploy portable instructions and skills to every agent

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** Each supported coding agent discovers the user's global
instructions and portable skill library after an ordinary deployment. The
library has one repo-owned source and real-file client adapters; its deployment
does not provision external accounts or execute skill payloads.

**Blocked by:** 04 — Install selectable coding agents through Bun.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] Import the agreed portable library and common instruction sources, preserving the 105-skill baseline unless an explicit documented portability issue requires an adaptation.
- [ ] All five clients discover their global instructions and supported shared or client-specific skill adapters through documented mechanisms.
- [ ] Common operating rules, portable RTK guidance, and conditional CodeGraph-first guidance have one source; host-specific paths are removed.
- [ ] Outputs are real files, with skill directory relationships, resources, intended permissions, and explicit-invocation metadata preserved.
- [ ] Applying the skill payload does not execute skill scripts, import credentials, activate account services, or index repositories.
- [ ] Specialist prerequisites and external account capabilities remain setup-on-use; client-specific tool differences are explained rather than promised away.
- [ ] Built-in client skills, unrelated user content, and host-local credentials/trust/runtime state remain outside the owned portable payload.
- [ ] Fresh-home client discovery/configuration checks and repeat deployment verify usable instructions and skills without model requests or real account access.
