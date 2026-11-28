# Caveman skills

Caveman is deployed only as standalone skills. The repository does not install,
configure, start, stop, or health-check the Caveman CLI or gateway.

Fresh homes receive no `.caveman` directory, gateway configuration, merge
baseline, hook, MCP server, or generated plugin. Existing device-side
`~/.caveman` state and old client settings remain device-owned; source cleanup
does not delete or rewrite them.

## Selection

The skill catalog keeps `caveman` and `caveman-compress` in the automatic core.
The other Caveman-branded skills use the `caveman` selection tag, except the
generic engineering workflows that remain automatic or optional under their own
selection. A host opts in with `DOTFILES_SKILLS=caveman` or a named skill.

Codex, Kimi Code, Pi, OpenCode, and Qoder read the shared skill tree. Claude Code
and MiniMax Code receive regular-file copies. See
[skill selection](SKILL_REVIEW.md) and [agent payloads](AGENT_PAYLOAD.md) for the
client matrix and ownership rules.

## Voice activation

Installing the skill makes it available; it does not activate the voice. The
pinned `caveman` skill starts on `/caveman` or a matching request and persists
for that session until `stop caveman` or `normal mode`. No CLI, gateway, hook, or
MCP server is needed.

Voice activation remains opt-in. The shared instruction block does not force a
repository-wide default mode. Persisted code, comments, commits, documentation,
and tickets keep normal prose even while the chat voice is active.

## Legacy device state

Older hosts may still contain Caveman binaries, configuration, runtime databases,
integration journals, provider routes, hooks, or generated plugins. They are not
part of this repository's deployment surface. Do not add them to Chezmoi source
or remove them as a side effect of skill cleanup.

An operator who deliberately retires or rolls back an old installation must use
the upstream CLI separately, preserve private backups and unrelated client
settings, and verify direct provider configuration with new client processes.
The repository provides no gateway lifecycle commands or supervision.

`tests/test_caveman.py` protects the current boundary: fresh applies create no
gateway configuration, repeated applies preserve existing gateway files without
executing their binaries, and the standalone `caveman` skill still deploys.
