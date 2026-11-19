# Magpie owns the model gateway

The deployment adopts Magpie as the single model gateway at
`127.0.0.1:3425` and splits ownership three ways: the repo owns the *intent*
(model-provider catalog, model ids, group membership, which agent uses which
group, and Claude Code's hand-written settings), Magpie owns *credentials and
generated state* (provider keys, accounts, usage, Pi's `models.json`, DSH's
Magpie route, and Codex's separate Magpie profile/catalog), and Codex's base
configuration and authentication remain device-owned. We rejected
letting Magpie's agent adapters write every client config because that would
put a second writer beside `deployment/client-settings/` and let a gateway
upgrade silently change an agent; we also rejected templating Pi's generated
`models.json` because it carries vendor metadata (context windows, prices,
thinking levels) that would drift from Magpie's catalog.

## Considered Options

- **Magpie writes every agent config** (`magpie claude`, `magpie pi`,
  `magpie dsh` for all): one less hand-written template, but the repo's
  client-settings merge would fight it on every bootstrap and a Magpie upgrade
  could change a working agent without a repo commit.
- **The repo templates every agent file, including Pi's `models.json`**: no
  runtime dependency during bootstrap, but duplicates Magpie's generated model
  metadata and breaks when a vendor changes a window or a price.
- **Wrapper launchers only** (`claude-magpie`, `pi-magpie`): the least
  invasive, but leaves the default commands on their old endpoints and does not
  satisfy "Claude Code on `group/conductor`, Pi on `group/workhorse`".

## Consequences

- A fresh Mac reaches the same wiring after the operator provisions missing
  key-based providers in Magpie's masked TUI; apply never passes keys in argv.
  Existing providers are adopted without rewriting credentials.
- `dotfiles-magpie status` is the only supported way to see drift; opening the
  app is not part of verification.
- Codex's base `config.toml` and `auth.json` remain protected by before/after
  content guards and private backups. The selected separate-profile exception
  permits only `magpie codex scope profile` followed by a profile model
  selection. The scope selection is read with the read-only getter and made
  before the gateway changes, because the pinned CLI refuses it while the
  ordinary Codex integration is connected; the deployment disconnects and
  retags nothing. The getter has to succeed: an answer printed by a command
  that failed is not a scope. The base configuration and authentication are
  compared by content after the selection whether the command succeeded or
  failed, so the run never claims a preservation it did not observe. The
  comparison is by content because a client re-serializes its own file
  without changing it; a real change still aborts the run.
  Magpie generates `magpie.config.toml` and `magpie-models.json`;
  the credential-bearing profile stays 0600, and a device without a Codex home
  gets a private one. Collision checks preserve unrecorded device files, a
  linked or non-directory Codex home, a linked or non-regular profile path, a
  generated file with another name, which the pinned writer would change
  through the alias, and a profile path whose link count cannot be read.
  An interrupted write can retry only against exact recorded fingerprints.
- Plain `codex` keeps the subscription configuration; `codex -p magpie`
  starts new gateway sessions. Resume must restore the saved provider, not
  migrate thread metadata. A combined in-session model picker was rejected
  because it changes the base configuration; a provider-definitions-only
  resume layer still needs isolated runtime verification. See
  [the Codex verification boundary](../MAGPIE.md#resume-without-switching-a-threads-provider)
  before application; synthetic profile tests do not establish live resume.
  Amended by
  [the neutral resume layer ADR](0015-neutral-codex-resume-layer.md): the
  provider-definitions-only layer is a managed command, and its isolated
  runtime verification against two fake providers is recorded there and in
  `docs/MAGPIE.md`.
