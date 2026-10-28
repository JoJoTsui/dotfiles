# Cross-agent collaboration

The shared instructions let any installed client start another one for a bounded
task. The rules follow current provider guidance rather than a role playbook.

Findings that shaped the rules (checked 2026-10-28):

- **Context-centric decomposition wins.** Anthropic reports that splitting one
  feature by role - planner, implementer, tester, reviewer - spends more tokens
  on coordination than on work, because every handoff loses context. Split only
  where context can truly be isolated: parallel research, components with a
  clean interface, or a verifier that needs nothing but test commands.
- **Delegation has a fixed cost.** Every call is a round trip plus a re-briefing.
  A small single-step task is cheaper and more accurate in the current agent.
- **A child sees none of the parent conversation.** Each brief must carry paths,
  constraints, and the report shape. This is also why a short brief beats a pasted
  transcript: the child starts its own prompt cache.
- **Depth is one.** Provider orchestration layers enforce one level of
  delegation; nested fan-out multiplies cost and coordination without adding
  context.
- **Sequential phases stay together.** Planning, implementation, and testing of
  the same feature share too much state to split.
- **Progressive disclosure beats permanent specialists.** Skills and tool search
  load detail on demand; a standing roster of agents loads its descriptions into
  every prompt.
- **Shared filesystem, isolated context.** Child agents can read the same tree,
  so restrict them by path and treat their output as evidence. Two agents on one
  working tree collide unless each has a worktree.
- **Provider health is part of the contract.** A client whose provider cannot be
  reached fails at invocation. Codex on this network needs the local proxy:
  `with-proxy codex exec ...` succeeds where the direct call times out. Fall back
  to a healthy client rather than retrying blindly.

Operational commands and the free-model defaults live in the shared instructions.
This note records why they look the way they do.

## Transports

The one-shot CLI is the default because it needs no session, works over SSH, and
returns status. Other transports exist for the cases it cannot cover:

| transport | use when | cost |
| --- | --- | --- |
| one-shot CLI | bounded task, CI, remote host | none beyond the client |
| background job (`&`, `wait`) | several bounded tasks from one shell | log files, exit-status collection |
| tmux / zellij | client must stay interactive or a human watches | a session to clean up |
| Herdr | already inside it; pane and agent state are useful | guarded by `HERDR_ENV=1` |
| `ssh host '<cmd>'` | work lives on another machine | host-local credentials and PATH |

All of them keep the same contract: one bounded brief, depth one, no credential
forwarding, verify the output, one worktree per concurrent agent, and cleanup of
every worktree the task created (merge, or archive-tag then remove). Herdr's
command set is in [herdr](HERDR.md); tmux needs no more than `new-session`,
`send-keys`, and `capture-pane`.

Sources:

- <https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them>
- <https://claude.com/resources/articles/multi-agent-coordination-patterns>
- <https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration>
- <https://www.anthropic.com/engineering/multi-agent-research-system>
- <https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop>
