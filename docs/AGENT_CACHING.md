# Agent caching and context budget

The installed clients all rebuild the full request on every turn, so the provider
matches an exact prefix. Facts checked 2026-10-28:

- Claude, OpenAI, Gemini, and DeepSeek match prefixes. Claude places tools,
  then system, then messages, and a change at one level invalidates that level
  and everything after it. OpenAI caches implicitly from 1,024 tokens on current
  models and offers explicit breakpoints on newer ones. DeepSeek caches on disk
  on a best-effort basis.
- Minimum cacheable sizes differ: 512 to 4,096 tokens on Claude models, 1,024
  tokens on current OpenAI models. Below the minimum nothing is cached.
- Cache writes cost about 1.25x normal input; reads are much cheaper. A prefix
  that changes every request costs more than no caching at all.
- Entries stay reusable for at least 30 minutes after the last write or read on
  OpenAI; Claude exposes five-minute and one-hour breakpoints.
- Harnesses converged on the same rule: static content first, volatile content
  last, and append-only history. A timestamp in the system prompt or a reordered
  tool list destroys reuse for every later turn.

The shared instructions carry the operational rules. This note records the
evidence so a future edit does not reintroduce a moving prefix.

Sources:

- <https://platform.claude.com/docs/en/build-with-claude/prompt-caching>
- <https://developers.openai.com/api/docs/guides/prompt-caching>
- <https://ai.google.dev/gemini-api/docs/caching>
- <https://api-docs.deepseek.com/guides/kv_cache>
- <https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/>
- <https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/prompt-caching.md>
