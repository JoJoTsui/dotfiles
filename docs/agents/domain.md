# Domain Docs

How the engineering skills should consume this repo's domain documentation when
exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in.

Use the glossary's vocabulary when naming a concept in a ticket, test, or
commit. If a concept is missing, note it for domain modeling rather than
inventing a synonym.

## File structure

Single-context repo: one `GLOSSARY.md` and one `docs/adr/` at the root. This
repo is single-context.

## Flag ADR conflicts

If a change contradicts an existing ADR, surface it explicitly rather than
silently overriding it, and say whether the ADR should be reopened.
