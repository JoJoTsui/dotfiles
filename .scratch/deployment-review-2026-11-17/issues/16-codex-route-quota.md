# 16: The Codex route through the gateway stopped answering after the apply

Status: needs-info
Blocked by: none — found while executing the authorized apply of 2026-11-19

**What to build:** the deployment must be able to tell, before it wires an
agent to a group that drains the ChatGPT account, that the account can still
serve. Right now nothing in the apply measures the account's remaining
quota, and the only symptom is that every request for that route times out.

## What was observed

The apply of 2026-11-19 completed with exit 0 at 14:16. From 14:17 onward
every command that needed Claude Code's safety classifier failed with:

```
codex/gpt-6.1-terra is temporarily unavailable (timed out), so auto mode
cannot determine the safety of Bash right now.
```

Commands on the read-only fast path (`git rev-parse`, `git ls-files`,
`git grep`, `echo`) kept working, and the session's own model route
(`minimax-cn/MiniMax-M3.1-Flash`) kept answering, because that route does not
use the codex provider. The local gateway itself was healthy: the apply had
just used it, and it answered on `127.0.0.1:3425` for every step.

`CLAUDE_CODE_AUTO_MODE_MODEL` and `CLAUDE_CODE_SMALL_FAST_MODEL` are both
`codex/gpt-6.1-terra` (`deployment/client-settings/claude-settings.json.tmpl`),
and `ANTHROPIC_BASE_URL` is the local gateway, so the classifier's traffic
goes to the codex provider and to the ChatGPT account behind it.

## Why it matters beyond the classifier

The apply wired the codex agent to `group/openai-stack`, whose first member
is `group/chatgpt` and whose routing mode is `drain`: the group's members are
tried in order and a member's accounts are spent until they are used up. So
every Magpie-routed Codex session now spends the ChatGPT account first. When
that account cannot serve, the whole chain times out, and the deployment
reports nothing: the apply says "the provider chatgpt is present", which is
a statement about the account's existence, not about its remaining quota.

The plain Codex path is untouched. `~/.codex/config.toml` still names the
subscription provider, and the Magpie profile is a separate file, so the
subscription configuration is still available — but the *gateway's* codex
route is the one that stopped answering.

## What is not measured

- Whether the ChatGPT account's weekly quota is spent, or whether the
  upstream (the account, or the proxy at `127.0.0.1:7897`) is failing. The
  measurement needs a command against the gateway, and the tool that would
  run it is the tool the outage blocks.
- Whether the outage predates the apply and only appeared next to it.

## The candidate change

Before the apply wires an agent to a group whose first member drains a
subscription account, ask the gateway for that account's remaining quota and
report it. The apply already talks to the gateway for the model list
(`GET /v1/models`); the quota is the same kind of question. A group whose
accounts cannot serve is a routing decision the operator should see, not a
silent timeout.

This is a proposal, not a decision: the gateway's own account status
interface has not been read yet, and the deployment must not guess a field
name.
