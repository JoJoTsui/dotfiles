# Agent caching and context budget

The installed clients rebuild the request on every turn, and caching generally
matches a prefix. Details differ by provider and model, so treat the following as
ranges and verify against current documentation:

- Claude, OpenAI, Gemini, and DeepSeek expose prefix caching. Claude places
  tools, then system, then messages; a change at one level invalidates that level
  and everything after it. DeepSeek caches on disk best-effort.
- Minimum cacheable sizes, retention windows, and write prices are model-specific.
  OpenAI documents different retention and write pricing across model
  generations, including longer retention options on newer models and no write
  surcharge on some older ones. Claude exposes multiple breakpoint lifetimes.
  There is no universal minimum, retention period, or multiplier.
- Static content first and volatile content last remains good practice, but
  request ordering, tool selection, and cache breakpoints are mostly harness
  controls, not actions a coding agent can take mid-task.
- Client compaction can rewrite history. Treat it as allowed; continue from the
  summary instead of replaying context.

The shared instructions carry only the actionable rules (bounded output,
batching, warm-session reuse). This note records evidence, not policy.

Sources:

- <https://platform.claude.com/docs/en/build-with-claude/prompt-caching>
- <https://developers.openai.com/api/docs/guides/prompt-caching>
- <https://ai.google.dev/gemini-api/docs/caching>
- <https://api-docs.deepseek.com/guides/kv_cache>
- <https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/>
- <https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/prompt-caching.md>
