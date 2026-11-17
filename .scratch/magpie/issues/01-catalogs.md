# 01: Magpie model catalogs and validator

**What to build:** Four declarative catalogs under `deployment/magpie/` and one validator that rejects a bad catalog before any file is written: `providers.tsv` (role, Magpie provider, key source, required), `models.tsv` (role, ordered candidate ids, required, `?` for optional), `groups.tsv` (id, members, routing, stays, listed, purpose), and `wiring.tsv` (agent, group, owner, enabled). The validator must reject unknown providers, duplicate group ids, a member role that does not exist, a `group/` member that is not declared, a required group with no model role, and any value that looks like a key. Header comments state the field contract, matching the other catalogs in `deployment/`.

Add `tests/test_magpie.py` with catalog-only tests: the shipped catalogs validate, and synthetic bad rows fail by name.

**Blocked by:** none.

**Status:** ready-for-agent

- [ ] `deployment/magpie/{providers,models,groups,wiring}.tsv` exist with documented headers and the contents from the spec.
- [ ] `deployment/magpie.sh` exposes `magpie_catalog_validate` and fails with a named error for each invalid case.
- [ ] No catalog value contains a credential; `env:` and `json:` sources name a variable or path only.
- [ ] `tests/test_magpie.py` covers each rejection and passes.
- [ ] `python3 -m unittest tests.test_magpie` passes.

## Comments
