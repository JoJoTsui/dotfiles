# 14: Keep the device's Codex configuration bytes when the merge changes nothing

Status: ready-for-agent
Blocked by: none — found while diagnosing ticket 13

**What to build:** the client-settings merge must leave a client's file
untouched when the merge changes nothing, for the TOML target as well as for
the YAML and JSONC targets. The device's Codex configuration is device-owned;
a merge that adds no value must not rewrite it.

- [x] `deployment/client-settings/merge.tmpl`: the TOML branch keeps the
      device's bytes when the merged table and the device's table are equal,
      exactly as the YAML branch keeps them for YAML and the `codex-hooks`
      branch keeps them for JSONC. When the merge does change something, the
      file is written as it is today.
- [x] The comparison uses the parsed tables, not the bytes. The device file is
      already parsed once (`fromToml`, merge.tmpl line 67); the equality check
      reuses that reading.
- [x] The write rule in `deployment/client-settings.sh` stays as it is: the
      staged file replaces the device file only when the bytes differ. With
      the device bytes preserved, an unchanged configuration keeps its
      modification time, which is what the comment above that rule already
      promises.
- [x] `tests/test_client_settings.py` (or the file that owns the client
      settings merge) covers the new case: a device TOML whose merge changes
      nothing keeps its bytes, and a device TOML whose merge changes
      something is still written.
- [x] `docs/AGENT_SETTINGS.md` describes the rule for every format, in the
      same task as the code. `AGENTS.md` was left alone on purpose: its
      client-settings section does not say which targets keep their bytes,
      so the rule belongs to the document that does.

## Comments

`deployment/client-settings.sh:102` already states the intent:

> An unchanged configuration keeps its device file untouched, so file times
> stay meaningful for the services that read them.

The TOML branch does not honour it. `merge.tmpl` renders it as
`{{ $host | toToml }}`, which always re-serializes, and the write rule then
replaces the device file because the bytes differ.

Measured on the device, the deployment's own merge of
`~/.codex/config.toml` differs from the device's file by 47 diff lines — key
order inside `[mcp_servers.node_repl.env]` and the layout of the marketplace
tables — while the parsed content is identical:

```
merged digest : 982a5fad3d558c421576f9a0d5e84354df6e4d5cd4cc7fdba28eb7c5702f3858
device digest : 982a5fad3d558c421576f9a0d5e84354df6e4d5cd4cc7fdba28eb7c5702f3858
```

So every apply rewrites a device-owned file, in a layout the device never
chose, and the rewrite is one of the two events that made the byte-based
guard fire during ticket 12's apply.

This is not the cause of that failure — Codex's own re-serialization is, and
ticket 13 fixes the guard — but it is the deployment churning a file it
claims to leave alone, and it belongs to the same incident.

## Supervisor notes (2026-11-19)

### The branch to mirror

The YAML branch already does exactly this:

```
{{- else if eq $format "yaml" -}}
{{- /* Preserve device bytes and mtime when no settings changed: the gateway
       publishes configuration changes by restarting after a newer file. */ -}}
{{- if and (lstat $target) (deepEqual $host (include $target | fromYaml)) -}}
{{ include $target }}
{{- else -}}
{{ $host | toYaml }}
{{- end -}}
```

and the JSONC branch keeps the bytes for the `codex-hooks` policy:

```
{{- if and (eq $policy "codex-hooks") (lstat $target) (deepEqual $host (include $target | fromJsonc)) -}}
{{ include $target }}
{{- else -}}
{{ $host | toPrettyJson }}
{{- end -}}
```

The TOML branch becomes the same shape with `fromToml`.

### The device file is already parsed

`merge.tmpl` line 67 reads the device file for the TOML format:

```
{{- if lstat $target -}}{{- $host = include $target | fromToml -}}{{- end -}}
```

So a device configuration that cannot be parsed already fails the merge
today, before this change. The equality check reuses that parsing and adds
no new failure mode. The device's file is never read with a parser it cannot
use.

### What this does not change

When the merge really does change something — a new key the device lacks, a
managed value the deployment owns — the file is still written in the
deployment's canonical layout. That is the existing behaviour for every
format, and preserving the device's layout while editing it would need a
TOML-aware editor the deployment does not have. This ticket only removes the
rewrite of a file that did not change.

### The change (2026-11-19)

The implementer worked in `~/SHELL/dotfiles.fix-client-settings-toml-bytes`
(branch `fix/client-settings-toml-bytes`, base `0472305`) and changed three
files:

| file | change |
| --- | --- |
| `deployment/client-settings/merge.tmpl` | the TOML branch keeps the device's bytes when the merged table and the device's table are equal |
| `docs/AGENT_SETTINGS.md` | the unchanged-target rule now covers the TOML targets |
| `tests/test_magpie.py` | `CodexTomlBytesTests`: two tests |

The device's parsed table is copied with `deepCopy` at the moment it is read,
because the merge mutates `$host` in place. The comparison is `deepEqual` on
the two parsed tables — the same shape as the YAML branch.

`AGENTS.md` is unchanged on purpose: its client-settings section does not
describe which targets keep their bytes, so the rule belongs to
`docs/AGENT_SETTINGS.md` alone.

The branch is shared by all three TOML targets (`codex`, `kimi`, `kimi-tui`),
so the device's Kimi configurations stop being rewritten as well.

### The supervisor's checks

- The new class on its own: 2 tests, OK.
- The implementer's own run of `test_magpie.py`: 290 tests, 0 failures, 0
  errors.
- The regression claim, re-measured here rather than taken on trust: the
  pre-change template **rewrites** the seeded device file, the changed
  template **keeps its bytes** — rendered against the test's own seed with
  the real chezmoi:

  ```
  merge-old.tmpl   -> device file REWRITTEN
  merge.tmpl       -> device bytes kept
  ```

- The live device, read-only: rendering the changed template against the
  real `~/.codex/config.toml` produces a file byte-for-byte identical to the
  device's, so the deployment will not rewrite it and its modification time
  will survive. A scratch copy with the policy-owned
  `check_for_update_on_startup` removed is still written, and the value
  comes back.
- A simulated home applies cleanly: `bootstrap.sh --class t9k --apply-only`
  exits 0. The `--class linux` run was interrupted by a transient file in
  the implementer's worktree and is re-run on the merged state.

Merged as `cb880df` on `fix/client-settings-toml-bytes` and integrated as
`78ffcc7` on `fix/deployment-review`.

