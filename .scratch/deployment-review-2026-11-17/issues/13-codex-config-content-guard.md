# 13: Compare the Codex configuration guard by content, not by bytes

Status: ready-for-agent
Blocked by: none — found while executing ticket 12's authorized apply

**What to build:** the guard that proves the deployment did not change the
device's Codex configuration must compare the *content* of
`~/.codex/config.toml` and `~/.codex/auth.json`, not their raw bytes. A
re-serialization by Codex itself is not a change to the configuration, and it
must not abort the apply.

- [x] A content digest helper in `deployment/magpie.sh` computes a stable
      digest of a parsed file: TOML through `tomllib`, JSON through `json`,
      each canonicalized and hashed. A missing file yields an empty digest; a
      file that cannot be parsed yields its byte digest, and that byte digest
      can never equal a content digest.
- [x] The TOML digest needs an interpreter with the standard-library
      `tomllib`. Resolve it the way `dot_local/bin/executable_dotfiles-codex-resume`
      resolves its own: the same candidate order as `magpie_python()`, skipping
      a candidate that cannot `import tomllib`. When no candidate qualifies,
      fall back to the byte digest and say so once per run. The fallback stays
      strictly conservative — it reports every real change and may report a
      re-serialization — so it never weakens the guarantee.
- [x] Every guard site compares the content digest: the scope preflight, the
      baseline capture, the provider add, the profile wiring, and the final
      guard. The guard messages, the failure behaviour, and the kept backup
      are unchanged; only the comparison changes.
- [x] The helper works in the bootstrap context and in the standalone
      `dotfiles-magpie` engine context. The engine has no `DEPLOY_CHEZMOI`,
      so nothing in the digest may depend on chezmoi.
- [x] `tests/test_magpie.py`: the fixtures that append a comment to the Codex
      configuration become real content changes, and a new fixture
      re-serializes the configuration into a different byte layout with the
      same content. The apply must succeed for that fixture and must still
      fail for every real change.
- [x] `AGENTS.md` and `docs/MAGPIE.md` describe the guard as a content
      comparison instead of a hash comparison, in the same task as the code.
- [x] The full deterministic suite, `/bin/bash -n deployment/magpie.sh`, and
      `git diff --check` pass. Nothing is pushed.

## Comments

The authorized apply of ticket 12 stopped at `magpie-apply.wiring`:

```
dotfiles: magpie: the Codex configuration changed during profile wiring
dotfiles: step magpie-apply.wiring failed (exit 1)
```

The change it caught is real in the bytes and absent in the configuration.
The backup taken at 10:17:30 and the file at 10:17:32 differ in exactly one
table:

```diff
 [marketplaces.openai-bundled]
 source_type = "local"
 source = "/Users/joey/.codex/.tmp/bundled-marketplaces/openai-bundled"
-
-[marketplaces.openai-primary-runtime]
-source_type = "local"
-source = "/Users/joey/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime"
+  [marketplaces.openai-primary-runtime]
+    source = "/Users/joey/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime"
+    source_type = "local"
```

Codex rewrote its own marketplace entry into its own layout. Parsed with
`tomllib`, the two files are the same configuration:

```
backup  content digest: 982a5fad3d558c421576f9a0d5e84354df6e4d5cd4cc7fdba28eb7c5702f3858
current content digest: 982a5fad3d558c421576f9a0d5e84354df6e4d5cd4cc7fdba28eb7c5702f3858
content equal: True
```

The guard exists to prove that the deployment did not change the device's
Codex configuration. It is a byte comparison, so it cannot tell that
difference from a real one, and it aborts an apply that changed nothing.

## Supervisor notes (2026-11-19)

### Where the byte change came from

Two writers re-serialize `~/.codex/config.toml`, and neither changes the
configuration:

1. **The deployment's own client-settings merge.** `deployment/client-settings/merge.tmpl`
   renders the TOML branch as `{{ $host | toToml }}`, which always
   re-serializes. `deployment/client-settings.sh:104` writes the staged file
   whenever the bytes differ from the device file, so the merge rewrites the
   device's Codex configuration on every apply. The rendered merge and the
   device file differ by 47 diff lines — key order inside
   `[mcp_servers.node_repl.env]` and the layout of the marketplace tables —
   with the same parsed content:

   ```
   merged digest : 982a5fad3d558c421576f9a0d5e84354df6e4d5cd4cc7fdba28eb7c5702f3858
   device digest : 982a5fad3d558c421576f9a0d5e84354df6e4d5cd4cc7fdba28eb7c5702f3858
   ```

2. **Codex itself**, which rewrote `[marketplaces.openai-primary-runtime]`
   during the apply window, between the backup at 10:17:30 and the guard at
   10:17:32.

The first is a separate defect with its own ticket (14). This ticket fixes
the guard, which must hold under both.

### The shape of the fix

The guard has five comparison sites, all in `deployment/magpie.sh`:

| line | site |
| --- | --- |
| 2476 | `magpie_codex_scope_preflight` — around the scope selection |
| 2509 | `magpie_apply` — the baseline capture |
| 2706 | after the provider add |
| 3033 | after the profile wiring — the site that fired |
| 3091 | the final `DEPLOY_STEP=magpie-apply.codex-guard` |

`magpie_sha256` (line 241) also serves the release-digest check and the
Magpie-owned profile fingerprint (line 2178). Those stay byte-based: they
verify bytes the deployment downloaded or wrote itself, not a configuration.

`magpie_python` (line 519) resolves an interpreter without requiring
`tomllib`. The digest needs a parser it can trust, so it gets its own
resolver with the `tomllib` check, mirroring `resolve_python` in
`dot_local/bin/executable_dotfiles-codex-resume`:

```bash
"$candidate" -c 'import tomllib' >/dev/null 2>&1 || continue
```

The deployment already guarantees the interpreter: `deployment/common-tools.tsv`
pins `python==3.15.2` for every platform, and the common-tools step runs
before the Magpie step. On the device, `~/.local/bin/python3` is 3.15.2 and
`import tomllib` succeeds.

The fallback is not a guess. A byte comparison is strictly stronger than a
content comparison: it reports every real change and reports some changes
that are not real. A fallback that reports too much is safe; a fallback that
reports too little is not. That is the opposite of the resume command's
situation, where a guessed provider definition reroutes a thread.

### The message vocabulary does not change

"The Codex configuration changed during profile wiring" stays true under a
content comparison: the configuration is what the guard compares. The tests
assert these strings, and the operator reads them. What changes is what
"changed" means — the configuration, not its bytes.

### The fixtures in `tests/test_magpie.py`

Three fixtures currently append `\n# changed\n` to the Codex configuration:
`FAKE_MAGPIE_TOUCH_CODEX` (line 55), `FAKE_MAGPIE_TOUCH_CODEX_ON_COMPACT`
(line 128), and `FAKE_MAGPIE_TOUCH_CODEX_ON_SCOPE_SET` (line 167). A comment
is not a configuration change, so under a content comparison these three
fixtures would stop firing and their tests would fail. They become real
changes — a new top-level key, which never contains the `model_provider =
"magpie"` string the fake's scope-set branch looks for.

`FAKE_MAGPIE_TOUCH_CODEX_AUTH_ON_SCOPE_SET` (line 172) and
`FAKE_MAGPIE_TOUCH_CODEX_AUTH` (line 190) write `{"changed":true}`, which is
already a real change and stays as it is.

The harness `PATH` is `self.tools:/usr/bin:/bin:/usr/sbin:/sbin`. The
system `python3` on this host is older than 3.11 and has no `tomllib`, so the
harness needs a qualifying interpreter for the new path to be exercised at
all: `tests/test_codex_resume.py` already solves this by symlinking
`sys.executable` into its fake bin directory.

### The change (2026-11-19)

The implementer worked in `~/SHELL/dotfiles.fix-codex-content-guard` (branch
`fix/codex-content-guard`, base `0472305`). Its run hit the 2400-second
timeout with the code, the tests, and the docs complete, so the supervisor
reviewed the diff, refined it, and ran the checks.

| file | change |
| --- | --- |
| `deployment/magpie.sh` | `magpie_content_python`, `magpie_content_digest_prepare`, `magpie_content_digest`; the five guard sites compare content digests |
| `tests/test_magpie.py` | the three comment fixtures became real content changes; a re-serialization fixture; the digest helper's own tests |
| `docs/MAGPIE.md` | the guard is described as a content comparison |
| `docs/adr/0014-…md`, `docs/adr/0015-…md` | the same |
| `AGENTS.md` | "the Codex content guard" |

### The hole the supervisor closed

The implementer's `magpie_content_digest` read the resolved interpreter from
`MAGPIE_CONTENT_PYTHON` only. A call that skipped `magpie_content_digest_prepare`
therefore found no interpreter and fell back to the byte digest — silently,
because the fallback is not an error. The measured consequence on this device:
without the preparation, the backup and the current file produced two
*different* byte digests and the guard fired exactly as before.

The fix resolves the interpreter in the shell that owns the comparison when
the prepared one is absent, so the fallback is reached only when no candidate
qualifies. The supervisor's own reference implementation, run against the
device's backup and current file, produced the same content digest
(`c:982a5fad…`) for both, and the device file unchanged.

### The digest's kind is part of its value

The digest carries a prefix: `c:` for a parsed content digest, `b:` for a
byte digest, and the empty string for a missing file. A file that parses at
one point and stops parsing at another therefore never compares as equal, and
a byte digest never equals a content digest. Nothing of the file leaves the
helper but its digest: the authentication holds a credential, and its digest
is compared in memory.

### The supervisor's checks

- The digest helper's own class: 2 tests, OK.
- `tests/test_magpie.py` on the implementer's branch: 292 tests, 0 failures,
  0 errors.
- The merged state on `fix/deployment-review`: 294 tests, 0 failures,
  0 errors.
- `/bin/bash -n deployment/magpie.sh`: clean. `git diff --check`: clean.

Committed as `7b8bd31` on `fix/codex-content-guard` and integrated as
`2386c99` on `fix/deployment-review`. The merge touched one file,
`tests/test_magpie.py`, where the two branches each imported `tomllib`; the
resolution keeps both spellings (`tomllib = None` and `HAS_TOMLLIB`).

