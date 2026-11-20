# Ticket 12 — tooling round 1: the existing-device rehearsal could not project this device's Codex configuration

Branch: `fix/macos-application-gates` (base `6de16eb`, the integration tip with ticket 10 merged).
No commit was made.

## The supervisor's measurement (real device, read-only)

Default policy against the device home:

```
python3 deployment/rehearse_settings.py --source-home "$HOME" \
  --manifest deployment/rehearsal/existing-mac-inputs.tsv \
  --projection /private/tmp/dotfiles-rehearsal \
  --report /private/tmp/dotfiles-rehearsal-report.json
dotfiles: rehearsal refused: unknown credential-shaped value in .codex/config.toml; refusing to project it
```

Exit status 5 (the redaction failure) and no projection was written. The rehearsal is
the approved gate for the device application, so it has to run against this device with
its default policy.

The unknown values are the 24 fields of the device's `hooks.state` table: the
`trusted_hash` and `trusted_content_hash` entries that Codex keeps for each trusted
hook. Each one is a 71-character digest (`sha256:` followed by 64 hexadecimal
characters). A trust digest is an integrity value, not a credential: it carries no
secret, and it is exactly the device-local state the rehearsal has to carry into the
projection, because the projection is what proves that the deployment preserves it.

Scope confirmation by the supervisor under the alternative policy:

```
python3 deployment/rehearse_settings.py --source-home "$HOME" \
  --manifest deployment/rehearsal/existing-mac-inputs.tsv \
  --projection /private/tmp/dotfiles-rehearsal-omit \
  --report /private/tmp/dotfiles-rehearsal-omit.json \
  --unknown-credential-policy omit
```

It succeeds, `source_unchanged` is true, and the only unknown fields are those 24
digests — but the projected `.codex/config.toml` then holds 114 of the source's 138
records, because the omitted digests are exactly what the preservation check needs.

## The fix

`deployment/rehearse_settings.py` (helper version `3` → `4`):

1. A new name rule, `INTEGRITY_NAME_SEGMENTS` = `hash`, `digest`, `checksum`,
   `fingerprint`, `sha`, `sha256`, `sha512`, `comp_hash`, and the helper
   `name_is_integrity()`: the **last** segment of a field name decides, so
   `trusted_hash`, `trusted_content_hash`, and `trustedContentHash` name an integrity
   value.
2. In `redact_structure()`, a field whose value has a credential shape but whose name
   says it holds an integrity value is projected **as it is** and counted in the new
   `integrity` counter. The credential-name rule is checked first and wins: a
   credential-named field (`api_key_hash`, `token_hash`) is still redacted, whatever
   its value is.
3. `check_redacted()` accepts the same rule, so the post-projection self-check does
   not reject a projected integrity value.
4. Every other unknown credential-shaped value keeps the current behaviour: the
   default policy fails the rehearsal closed (exit 5, no artifacts), and
   `--unknown-credential-policy omit` drops the field and counts it. The detector
   itself (`CREDENTIAL_VALUE`, `URL_USERINFO`, `ASSIGNMENT`) is unchanged.
5. The value-free report gained `totals.integrity_fields`, a per-file
   `integrity_fields` count, and a `policy_notes` block that states the three rules
   in words. No value is ever printed or written to the report.

Documentation: `docs/MACOS_DEPLOYMENT.md` gained a paragraph describing the integrity
rule, and the reviewed manifest `deployment/rehearsal/existing-mac-inputs.tsv` gained
a comment saying the same thing.

## Tests

`tests/test_existing_settings_rehearsal.py` — synthetic home only, no real device file
is read:

* `test_a_digest_named_field_with_a_credential_shaped_value_is_projected` — a
  `trusted_hash` / `trusted_content_hash` pair with a 71-character digest is projected
  unchanged; the report counts 2 integrity fields and no unknown, omitted, or
  redacted field.
* `test_a_credential_named_field_is_redacted_even_when_it_is_hash_named` —
  `api_key_hash` and `token_hash` are `<redacted>`; `trusted_hash` is not; the report
  counts 2 redacted fields and 1 integrity field, and holds no digest.
* `test_an_unknown_credential_shaped_value_under_an_ordinary_name_still_fails_closed`
  — `device_note` with a credential-shaped value still fails closed by default, with
  no projection and no report.
* `test_an_unknown_credential_shaped_value_is_omitted_with_a_count_beside_digests` —
  the same field is omitted and counted under `omit`, and the digest beside it is
  still projected.
* `test_the_projected_record_count_of_a_file_with_digests_matches_the_source` — the
  projected record count equals the source record count.
* `test_the_hook_trust_digests_survive_the_public_bootstrap` — the projected digests
  survive the ordinary public bootstrap applied to the projection.

## Checks run

* Red/green on the finding, against a synthetic Codex configuration that carries a
  `trusted_hash` (no real device file was read):
  * pre-change helper (`git show HEAD:deployment/rehearse_settings.py`): exit 5,
    `dotfiles: rehearsal refused: unknown credential-shaped value in
    .codex/config.toml; refusing to project it`, no projection written;
  * post-change helper: exit 0, the digest is projected as it is, the report shows
    `integrity_fields: 2`, `unknown_credential_fields: 0`, `omitted_fields: 0`,
    `source_unchanged: true`, and the projected record count equals the source
    record count.
* `PYTHONPATH=tests python3 -m unittest tests.test_existing_settings_rehearsal -v` —
  38 tests, all pass (the module needs `PYTHONPATH=tests` for the `fixtures`
  package; the ticket's command form alone fails to import for that reason, also on
  the base commit).
* `PYTHONPATH=tests python3 -m unittest tests.test_deployment` — 2 failures
  (`test_privileged_options_are_rejected_for_native_windows_plans`,
  `test_privileged_options_reject_a_simulated_home_before_writing`). The same two
  failures occur on the unmodified base commit exported with `git archive HEAD` into
  the scratch directory: they are pre-existing and environmental (this sandbox
  reports the native platform differently), not caused by this change.
* `git diff --check` — clean.

## Checks skipped

* The rehearsal against the real `$HOME` was not run here: reading the device tree is
  the supervisor's step only. The red/green demonstration used a synthetic home in
  `TMPDIR`.
* `deployment/magpie.sh` was not checked: the ticket states it is unrelated.
* No install, download, push, reset, or stash was performed; no file outside this
  worktree and `TMPDIR` was written.

## Risks that remain

* The integrity rule trusts the field name. A secret that a client stores under a
  hash-named field (`*_hash`, `*_digest`, …) would be projected as it is, because
  the name is the only signal available. The rule is deliberately narrow (the last
  name segment must be one of the eight integrity names) and the credential-name
  rule still wins for `api_key_hash`-style names.
* The integrity rule applies to the value of the field only. A list of digests under
  an integrity-named key has no per-item name, so it still fails closed.
* The rule changes what the rehearsal projects: the projection now carries the
  device's hook trust digests, which is the point of the fix, but it means the
  projection holds device-local state rather than only device-independent values.
* The merge side is proven only by the fabricated bootstrap run
  (`test_the_hook_trust_digests_survive_the_public_bootstrap`). The supervisor's real
  device run still has to confirm that the 24 digests of this device survive the
  deployment, and that the projected `.codex/config.toml` holds all 138 source
  records.
