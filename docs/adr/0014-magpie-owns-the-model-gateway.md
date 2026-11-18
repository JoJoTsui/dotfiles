# Magpie owns the model gateway

The deployment adopts Magpie as the single model gateway at
`127.0.0.1:3425` and splits ownership three ways: the repo owns the *intent*
(model-provider catalog, model ids, group membership, which agent uses which
group, and Claude Code's hand-written settings), Magpie owns *credentials and
generated state* (provider keys, accounts, usage, Pi's `models.json`, DSH's
Magpie route), and Codex's configuration belongs to neither. We rejected
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
- Codex is structurally protected: no code path calls `magpie codex`, and each
  apply hashes `~/.codex/config.toml` before and after.
