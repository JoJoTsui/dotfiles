---
status: accepted
---

# One catalog owns the shared skill library

The shared skill tree had two writers. The repository catalog pinned 94 skills
and copied them into `~/.agents/skills`; the `bunx skills` CLI kept a second
lockfile at `~/.agents/.skill-lock.json` with 130 entries and wrote into the
same root. Verified on one device: 93 names overlapped, 37 CLI entries were the
DeepMind skills the deployment deliberately disables, six skills existed only
in the CLI's record, and `impeccable` was in neither. The tree held 100 skills,
every agent saw a different subset, Claude's root mixed 33 device symlinks with
managed copies, and MiniMax and Qoder carried stale copies of 66 and 61.

The repository catalog is now the sole owner. Skill bytes still come from
upstream and stay hash-pinned; `bunx skills` is not run against a managed root.
The CLI's lockfile is device state: the deployment reads it, reports every
uncatalogued or disabled skill it names, and prints the `bunx skills remove`
commands that tidy the device. It never edits the third-party lockfile. The six
skills that only the CLI knew are adopted as catalog rows seeded from their
recorded source, path, and folder hash, which is what makes them reviewable and
prunable.

Selection becomes explicit. The catalog's selection column keeps `auto` for the
reviewed default set and uses tags for groups a host opts into with
`DOTFILES_SKILLS`: `lark` for the non-documentation Feishu skills and `caveman`
for the Caveman-branded skills other than the mode and its compress skill. The
four diagram, slide-deck, PPT, and front-end design skills were initially tagged
but are now part of `auto`; `docs/AGENT_PAYLOAD.md` records the current selection.
The six generic engineering skills from the Caveman repository stay in `auto`;
they are general workflows, not Caveman voice. Mattpocock, Herdr, Worktrunk, and
RTK guidance are named as preferred workflows in the shared instructions so
their priority is visible to every client.

Per-client sets apply only where the deployment controls discovery. Claude and
MiniMax receive filtered copies; Pi and OpenCode receive a profile root through
the `skills` path already present in their merged settings. Codex, Kimi, and
Qoder keep the reviewed global set because they have no supported persistent
filter, and the per-client matrix records that limit. The deployment records
the skill directories it deployed per root in device state
(`~/.local/state/dotfiles/managed-skills.tsv`) and prunes only those when they
leave a profile. Device-created skills are never removed. A generated skill and
a symlinked entry are preserved as well: the prune never follows a link and
never deletes through it.

A copy root is inspected before a selected skill is written there. A device
entry with the same name — a symlink or a file — is preserved and reported,
and the deployment never writes through it. A directory the inventory does not
record is adopted when it already holds the selected bytes, and preserved and
reported when its bytes differ, so the stale copy a device carried before the
inventory is never deleted silently. A directory the inventory records belongs
to the deployment, so the staged copy replaces it. The generated skill reaches
every managed root, and each root is recorded in `generated-skills.tsv` so the
prune leaves it alone everywhere.

The review is guarded, not just documented. New or changed catalog rows must
have a description of 240 characters or fewer and a root document of 200 lines
or fewer unless it ships a reference file. The measured library holds 15
over-budget descriptions and 3 long root documents, 17 rows in all; they are
listed as reviewed exceptions in `deployment/skill-budget-exceptions.tsv` with
their measured description length, their measured root lines, whether the
skill ships a reference file, and the reason the row stays. A row above a
budget without such an exception fails the check by name, and a row whose
measurements no longer match its exception fails as well, because updating an
exception is a review action. The check reports the per-client inventory, the
budget findings, and the ratchet failures, and a library it cannot read is
reported as not measured rather than as a pass. The per-client matrix is
`deployment/agent-payload/skill-clients.tsv`, and the review reference is
`docs/SKILL_REVIEW.md`. Upstream prose is not rewritten, because the lock's
value is that the bytes are upstream's.

RTK remains instruction-only: an always-applicable rule belongs in the shared
instructions, not in a skill a client may or may not select. Herdr's own skill
is generated from `herdr --skill` when the multiplexer is present and is
included in every profile; it is not vendored, and it is not a catalog pin.
Instruction files stay one shared block deployed to all seven clients, with
per-client caveats in the documented delta table rather than seven forks.

Consequences: enabling `bunx skills add` on a managed root breaks the ownership
model and is reported as drift. A host that wants the design or caveman groups
must select them. Pruning makes tags real but deletes only managed entries. The
existing exceptions stay until they are reviewed, and any new skill above the
budget fails the check before it ships.
