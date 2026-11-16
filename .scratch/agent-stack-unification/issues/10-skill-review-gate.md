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

**Status:** ready-for-agent

- [ ] The review document states the per-client matrix, including the clients that cannot be filtered.
- [ ] The check prints the per-client inventory and the budget findings.
- [ ] A synthetic new row above either budget fails the check and names the row and rule.
- [ ] A changed row above either budget fails; an unchanged grandfathered row does not.
- [ ] Every exception is listed with a reason.
- [ ] Tests cover a passing catalog, a new violation, a grandfathered row, and the inventory output.
