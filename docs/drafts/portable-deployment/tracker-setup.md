# Tracker setup proposal

**Status:** Draft only. Tracker choice, triage vocabulary, and setup review are
pending; this document does not activate configuration or publish issues.

The recommended tracker is GitHub Issues in `JoJoTsui/dotfiles`, matching the
remote. Local Markdown is also supported; choosing it changes the tracker
instructions and requires a source-state exclusion for its scratch directory.
The repo is single-context and already has a glossary and five ADRs.

## Proposed addition to the existing AGENTS.md

```markdown
## Agent skills

### Issue tracker

Specs and tickets use GitHub Issues in JoJoTsui/dotfiles. Before tracker
operations, read `docs/agents/issue-tracker.md`.

### Triage labels

Use the five canonical triage labels. Before applying labels, read
`docs/agents/triage-labels.md`.

### Domain docs

This repo has one domain context. Before domain exploration, read
`docs/agents/domain.md` for the glossary and relevant ADRs.
```

## Proposed docs/agents/issue-tracker.md

```markdown
# Issue tracker: GitHub

Specs and tickets live in GitHub Issues in JoJoTsui/dotfiles. Use the gh CLI
with this repository selected explicitly for tracker operations.

Read an issue's full body and comments before using it as task context. Write
multiline issue bodies to a temporary file and pass --body-file; preserve real
newlines. Publish the spec as the parent issue and approved tickets as its
sub-issues in dependency order. Do not close or otherwise rewrite the parent
when converting it to tickets.

Use native issue dependencies for blocking edges when available, referencing
database IDs rather than issue numbers. If that capability is unavailable,
record Blocked by references to the actual blocking issues in each child body.
A ticket is actionable when every listed blocker is completed.

Use the configured triage vocabulary. Add missing configured labels during
approved setup, and apply ready-for-agent to published reviewed specs/tickets.

PRs as a request surface: no.
```

## Proposed docs/agents/triage-labels.md

```markdown
# Triage labels

| Canonical role | Tracker label | Meaning |
| --- | --- | --- |
| needs-triage | needs-triage | Maintainer evaluation needed |
| needs-info | needs-info | Information needed from the reporter |
| ready-for-agent | ready-for-agent | Fully specified for an agent |
| ready-for-human | ready-for-human | Human implementation required |
| wontfix | wontfix | Will not be actioned |
```

## Proposed docs/agents/domain.md

```markdown
# Domain docs

This repository has one context: the root GLOSSARY.md and docs/adr/.

Before domain exploration, read the glossary and ADRs relevant to the work.
Use the glossary's vocabulary in specs, tickets, test names, and explanations.
If an ADR conflicts with a proposal, identify the conflict explicitly instead
of silently overriding it. Missing domain documents do not block exploration;
create terms or decisions only when the domain-modeling workflow resolves them.
```

## If local Markdown is selected

The tracker document instead records one feature per `.scratch/<feature-slug>/`,
its spec as `spec.md`, and one ticket per `issues/<NN>-<slug>.md`. Each ticket
records status and its numbered blocking edges, and comments append to the
ticket. Publication creates local files only. Scratch tracker content is
excluded from chezmoi target homes; the triage vocabulary and domain layout
remain the same.
