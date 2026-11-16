# 10: Skill review document and ratchet gate

**What to build:** A review document that records the per-client skill matrix,
the selection rules, the ownership rules, and the "is this worth the context?"
checklist derived from the upstream guidance. The skill check emits the
per-client inventory, the description and root-document findings, and the
ratchet result. A new or changed catalog row with a description over 240
characters, or a root document over 200 lines without a reference file, fails
the check by name. Today's over-budget rows are listed as reviewed exceptions
with a reason.

**Blocked by:** 05, 06, 07, 08.

**Status:** done

- [x] The review document states the per-client matrix, including the clients that cannot be filtered.
- [x] The check prints the per-client inventory and the budget findings.
- [x] A synthetic new row above either budget fails the check and names the row and rule.
- [x] A changed row above either budget fails; an unchanged grandfathered row does not.
- [x] Every exception is listed with a reason.
- [x] Tests cover a passing catalog, a new violation, a grandfathered row, and the inventory output.

## Comments

`docs/SKILL_REVIEW.md` is the review reference. It states the per-client
matrix, the selection rules, the ownership rules, and the checklist derived
from the upstream skill-authoring guidance: a short description, a root
document that routes instead of carrying the detail, instructions that are
specific without being over-specified, guidance written for the model that
reads it, and the context budget every skill spends. It is a review document,
not a second specification: the decisions stay in ADR 0013 and the deployment
behaviour stays in `docs/AGENT_PAYLOAD.md`.

The matrix is machine-readable in `deployment/agent-payload/skill-clients.tsv`:
the five shared-tree readers (Codex, Kimi, and Qoder read the whole tree
because they have no supported persistent filter; Pi and OpenCode read it as
their registered profile root), the two filtered copies (Claude Code and
MiniMax Code), and the two device roots the deployment never writes
(`~/.pi/agent/skills`, `~/.config/opencode/skills`).

`deployment/skill_review.py` measures a library and reports it.
`deployment/update_skills.py check` now emits the per-client inventory, the
budget findings, and the ratchet result, and `update_skills.py review` emits
the review alone. The check reads the deployed shared tree by default and
`--library` names another one, which the tests and the deployment use. A
library that cannot be read is reported as not measured; the check never
claims a budget it did not measure.

The budgets are 240 characters of description and 200 lines of root document,
and a root document above 200 lines passes when the skill ships a reference
file. A folded (`>`) or literal (`|`) frontmatter description is read as its
joined prose, so a block description is measured as the text a client reads.

The ratchet has three rules. A row above a budget without a reviewed
exception is new and fails by name. A row whose measurements no longer match
its exception changed and fails by name, in either direction: a longer
description and a shorter one both need a review. An exception for a row that
is now inside the budget fails as well, because the record is stale. Updating
an exception is a review action: the reviewer records the new measurements and
the reason, or brings the row back inside the budget.

`deployment/skill-budget-exceptions.tsv` records today's over-budget rows with
their measured description length, their measured root lines, whether the
skill ships a reference file, and the reason the row stays. The measured
library holds 15 over-budget descriptions and 3 long root documents, 17 rows
in all. ADR 0013 said 30 over-budget descriptions before the gate existed;
that figure is now the measured one.

The upstream bytes are not rewritten, because the lock's value is that the
deployed bytes are upstream's. A long description is therefore reviewed and
kept, and the reason says what the description carries.

The deployment reports the review of the library it is about to ship and never
fails on it: the gate is the explicit check, and a reviewer runs it against
the library that holds the changed row. The pin check and the CLI drift report
keep working unchanged.

Verified with hermetic fixture libraries: a passing catalog, a new row over
the description budget, a new row over the root budget, a grandfathered row, a
changed grandfathered row, a root over 200 lines with a reference file, the
per-client inventory, and the missing-library message. The skill and payload
suites pass. The three `test_agent_integrations` failures are the pre-existing
macOS host scope (`stat -c` is a GNU option), unchanged from the parent
commit. The pinned-client diagnostics skip without the installed clients.
