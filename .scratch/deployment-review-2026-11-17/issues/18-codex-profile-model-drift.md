# 18: The Codex profile drifted after the apply, and the status says so

Status: ready-for-agent — closed on 2026-11-20: the cause is identified and
the drift no longer reproduces
Blocked by: none — found in the live verification of 2026-11-19

**What to build:** a finding that names the drift, the evidence, and the
decision that is still the operator's.

- [x] The cause of the `model` drift in `~/.codex/magpie.config.toml` is
      identified, and the fix is either a deployment change or a documented
      device behaviour.

## What the live verification found

`dotfiles-magpie status` on the device, after the successful apply:

```
wiring|claude|group/conductor
wiring|codex|drift (model)
wiring|pi|group/workhorse
```

`drift (model)` is the report of `magpie_codex_profile_report`
(`deployment/magpie.sh`): the profile's `model` key no longer equals the
group the wiring row names. The report names only the keys that differ, so
`model_provider`, `model_catalog_json`, `model_providers.magpie.base_url`,
and the file mode are all still correct, and the credential-bearing file is
still mode 0600.

The same apply reported the agent as wired:

```
dotfiles: magpie: the agent codex is wired to group/openai-stack
```

and the apply's own verification of that profile passed, because the apply
fails the run when the profile does not retain the requested provider, model,
catalog, gateway, and private mode. The recorded state holds
`wiring|codex|group/openai-stack`.

So the profile held the requested group at the end of the apply and holds
something else now.

## Why this matters

The status is the report the deployment makes about the device, and it now
fails. `dotfiles-magpie status` exits non-zero when a required piece is
missing, and a drifted Codex wiring is one of them. A device that reports a
drift it cannot explain is a device an operator cannot trust.

## The open question

The profile's `model` key was changed by something after the apply
finished. The candidates are:

- the operator's own `codex -p magpie` session, if Codex 0.169.0 writes the
  resolved model back into the profile it was given;
- the Magpie app, which owns the profile and owns the running gateway
  (0.1.4527 on 127.0.0.1:3425), rewriting it when the group changed;
- a second apply that rewired the group and wrote a different value.

The first two are device behaviour and the deployment's answer is to report
them accurately; the third is a deployment defect.

## What the operator has to decide

If Codex or the Magpie app rewrites the profile's `model` key, then
`magpie_codex_profile_report` compares the profile against the *catalog
group* while the device holds the *resolved model*, and the status reports
drift that is not drift. The comparison then has to name what it compares
against, and the report has to say which one it saw.

That decision belongs to the operator: whether the status should compare the
profile against the catalog intent or against what the device's own writer
leaves behind. Changing the comparison changes what a failing status means.

## How to identify the cause without credentials

The profile carries the gateway bearer credential. It is never printed.
The `model` key alone is read with the deployment's own reader, which
returns one plain value:

```bash
source deployment/magpie.sh
magpie_codex_toml_string "$HOME/.codex/magpie.config.toml" '' model
```

Nothing else in the file is printed, and no credential reaches the output.

The modification time of the profile and of the state file separates the
candidates: a write after the apply's stamp belongs to the device, a write
before it belongs to the apply.

## Evidence already collected

- the apply's own report and the recorded state (in
  `apply-gate.md` §7 and §8);
- the status line above;
- the profile's mode, 0600, and the catalog's mode, 0644, both unchanged.

## Comments

- 2026-11-20: The cause, read from the backup the authorized apply took at
  11:10:31 before it wrote the profile
  (`~/.local/state/dotfiles/magpie/backups/20261120T031031Z/.codex/magpie.config.toml`,
  mtime 2026-11-19 19:41). That copy carries `model = "minimax-cn/MiniMax-M3.1-Flash"`,
  and the profile the apply wrote carries `model = "group/openai-stack"`, the
  group the wiring row names.
- 2026-11-20: What drifted in is the *selected* model of the connected agent
  family, not a group: `minimax-cn/MiniMax-M3.1-Flash` is the first member of
  `group/workhorse` and the model Claude Code itself carried
  (`magpie ls` reports `minimax-cn/MiniMax-M3.1-Flash` for Claude Code today).
  No deployment path writes a plain provider model into the Codex profile —
  the apply writes the wired group and verifies it — so the writer was
  device-side: the Magpie app, which owns the profile and the agents, wrote
  the selected model into the Codex profile after the apply.
- 2026-11-20: The state is clean again, and the drift is repaired by the
  apply rather than by a hand edit: `wiring|codex|group/openai-stack`, and
  `dotfiles-magpie status` exits 0.
- 2026-11-20: What is not established: which process performed the write.
  The app is the only writer that can put a Claude model into the Codex
  profile, but the artifacts carry no audit trail, so this is the
  best-supported cause and not a proven one. Nothing in the deployment needs
  to change either way, because the apply re-asserts the wired group.

