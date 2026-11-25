---
name: archify-figures
description: Create polished workflow diagrams for presentations and Nature-style journal figures, with validated SVG/HTML output, physical sizing, editable text, and publication checks.
disable-model-invocation: true
---

# Archify Figures

Create a workflow diagram when the user asks for a presentation graphic or a
journal figure. Use `show-me` instead for a quick terminal explanation.

This skill carries only Archify's workflow renderer and delivery tools. Code
Analysis, explainer pages, stories, video, PR tooling, and the other diagram
renderers are not installed.

## Choose the output

- **Presentation:** interactive HTML plus light/dark SVG exports.
- **Journal figure:** a physically sized, vector SVG that passes the checks in
  [Nature figures](references/nature-figures.md). Nature prefers PDF or EPS for
  final submission; the SVG is the editable source.

Read [Nature figures](references/nature-figures.md) before any journal request.
It records the official size, typography, colour, and file-format rules and the
layout recipe that passes the bundled checker.

## Author the workflow

1. For a real codebase or method, read the relevant source and record exact
   paths and inclusive line ranges. Follow
   [Repository authoring](references/repository-authoring.md); do not infer a
   step from a filename or package description.
2. Read `schemas/workflow.schema.json`, `schemas/common.schema.json`, and
   `examples/nature-workflow.json`. Examples teach shape, not facts.
3. Write schema-v2 JSON under the requested output folder. Use fresh IDs and
   wording. Keep every requested responsibility, branch, condition, and
   direction.
4. For a journal figure, use a compact double-column layout by default. Reserve
   the 89 mm single-column width for a genuinely small vertical flow. Omit
   sublabels, tags, cards, phases, groups, and the legend unless removing them
   would change the scientific meaning. Put explanations in the figure legend.
5. Set `meta.visual_preset` to `editorial`, `meta.quality_profile` to
   `showcase`, `meta.feedback_links` to `false`, and
   `meta.legend.mode` to `hidden` for the journal recipe. Use `meta.locale` for
   the reader's language.

The wrapper refuses a journal SVG whose projected text falls outside 5–7 pt or
whose height exceeds 170 mm. Repair the composition; do not silently shrink the
type.

## Deliver

Run commands from the working directory and replace `<skill>` with this
skill's absolute path.

### Journal SVG

```bash
node <skill>/bin/archify-figure.mjs export candidate.json figure.svg --width 183 --json
```

Use `--width 89` only for a compact single-column figure. A non-zero exit is not
success: read the diagnostics, repair the candidate, and rerun.

The wrapper validates the workflow, exports the canonical SVG, removes the
embedded presentation font, selects Arial/Helvetica, forces black text, removes
filter effects, sets physical dimensions, and checks text size, vector content,
and external references.

For final journal submission, open the SVG in Illustrator or Inkscape, confirm
Arial/Helvetica and editable text, and save PDF or EPS with fonts embedded. Do
not outline text. Report the SVG as the editable source unless the user asks
for the final submission conversion.

### Presentation package

```bash
node <skill>/bin/archify-figure.mjs presentation candidate.json figure --theme both --preset editorial --json
```

This writes `figure.html` and light/dark SVGs. It does not require a browser.
Open the HTML for interactive presentation; use the SVGs for slide insertion.

## Verification

The export receipt records the artifact SHA-256, physical dimensions, projected
font range, and automated checks. It does not claim perceptual review. Inspect
the delivered figure at its intended reading size and follow every requested
branch before reporting success.

Do not install packages, fetch updates, or modify the skill directory. The
deployment owns these bytes and refreshes them from the pinned Archify commit.
