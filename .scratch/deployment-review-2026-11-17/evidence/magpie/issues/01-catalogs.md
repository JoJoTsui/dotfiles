# 01: Magpie model catalogs and validator

**What to build:** Four declarative catalogs under `deployment/magpie/` and one validator that rejects a bad catalog before any file is written: `providers.tsv` (role, Magpie provider, key source, required), `models.tsv` (role, ordered candidate ids, required, `?` for optional), `groups.tsv` (id, members, routing, stays, listed, purpose), and `wiring.tsv` (agent, group, owner, enabled). The validator must reject unknown providers, duplicate group ids, a member role that does not exist, a `group/` member that is not declared, a required group with no model role, and any value that looks like a key. Header comments state the field contract, matching the other catalogs in `deployment/`.

Add `tests/test_magpie.py` with catalog-only tests: the shipped catalogs validate, and synthetic bad rows fail by name.

**Blocked by:** none.

**Status:** done

- [x] `deployment/magpie/{providers,models,groups,wiring}.tsv` exist with documented headers and the contents from the spec.
- [x] `deployment/magpie.sh` exposes `magpie_catalog_validate` and fails with a named error for each invalid case.
- [x] No catalog value contains a credential; `env:` and `json:` sources name a variable or path only.
- [x] `tests/test_magpie.py` covers each rejection and passes.
- [x] `python3 -m unittest tests.test_magpie` passes.

## Comments

The four catalogs carry the spec's rows unchanged, with a header that states the
field contract the way the other catalogs in `deployment/` do. A group member is
a model role or `group/<id>`; a model candidate is `provider/model`, where the
provider is one of the four Magpie presets; a `?` suffix marks a candidate
optional.

`deployment/magpie.sh` holds the validator and nothing else yet, so sourcing it
never mutates a file. `magpie_catalog_validate` reads the four catalogs,
rejects a row with the wrong field count, an unknown Magpie provider preset, a
duplicate provider role or group id, a member role that no model role declares,
a `group/` member that no group declares, a group without a model role, a
wired group that no group declares, and a model candidate that names a provider
no provider row declares. The credential scan runs before the shape checks, so a
pasted key is reported as `catalog value looks like a credential` rather than as
a malformed field. The known presets are one constant in the file, because
Magpie owns that list and a catalog may not invent one.

Tests run:

- `bash -n deployment/magpie.sh` — passes.
- `python3 -m unittest tests.test_magpie -v` — 12 tests, all pass. The suite
  validates the shipped catalogs and drives one synthetic catalog per
  rejection, asserting the named error.
- `shellcheck deployment/magpie.sh` — not run: shellcheck is not installed on
  this device (it belongs to the optional developer bundle).
