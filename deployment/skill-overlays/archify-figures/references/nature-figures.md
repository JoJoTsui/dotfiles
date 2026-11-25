# Nature-style workflow figures

Nature Portfolio's figure guide applies to *Nature* and *Nature Methods*. The
official requirements are the authority; this page turns them into a workflow
recipe for the bundled renderer.

## Official requirements

- Main figures are vector files with editable layers. PDF, EPS, and AI are
  preferred; plain SVG is accepted.
- Use RGB, standard sans-serif fonts (Arial or Helvetica), and editable text.
  Do not outline text. Embed TrueType 2 or 42 fonts in the final PDF/EPS.
- Text must be 5–7 pt at final printed size. Panel labels are 8 pt, bold,
  upright, lowercase.
- Printed widths are 89 mm (single column) and 183 mm (double column). Maximum
  height is 170 mm.
- Avoid background grids, drop shadows, patterns, decorative icons, coloured
  text, and text over busy backgrounds. Use an accessible colour palette and
  keep essential distinctions available through labels or keylines.
- Keep the figure simple. Move explanatory prose and non-essential detail to
  the legend.

Sources:

- [Preparing figures — specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)
- [Building and exporting figure panels](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)
- [Nature formatting guide](https://www.nature.com/nature/for-authors/formatting-guide)

## Renderer recipe

Archify's presentation defaults target screens, not print. A wide showcase with
7 px fine text becomes about 3.3 pt at 183 mm and is not suitable for a main
figure. Use this recipe instead:

1. Use schema v2 and `meta.quality_profile: "showcase"`.
2. Use `meta.visual_preset: "editorial"`, `meta.feedback_links: false`, and
   `meta.legend.mode: "hidden"`.
3. Use a compact three-lane, four-column composition for a six-step method.
   Set node widths to 180 px. The bundled example measures 888 × 440 units.
4. Keep node and lane labels only. Omit sublabels, tags, cards, phases, groups,
   and non-essential edge labels. Their 7–8 px type does not survive journal
   reduction.
5. Use short, specific labels. Explain inputs, outputs, and conditions in the
   figure legend rather than adding fine print to the drawing.
6. Export at 183 mm. The bundled example projects to 183 × 90.7 mm with
   5.84–6.43 pt text and passes the wrapper's checks.
7. Use 89 mm only when a simpler vertical flow still projects to 5–7 pt and
   stays within 170 mm height. The wrapper refuses the export otherwise.

## What the wrapper changes

`bin/archify-figure.mjs export`:

- runs Archify's workflow validation and artifact checks;
- exports the light editorial SVG;
- removes embedded JetBrains Mono WOFF2 data and selects Arial/Helvetica;
- forces black text and removes filter effects such as drop shadows;
- sets physical width and height while preserving the viewBox;
- rejects raster images, external resource references, text outside 5–7 pt,
  and figures taller than 170 mm;
- writes the SVG atomically and returns a JSON receipt.

The SVG keeps `<text>` elements editable. It does not embed Arial/Helvetica
font bytes. For submission, open it in Illustrator or Inkscape and save PDF or
EPS with the fonts embedded and text retained. That final conversion is a
deliberate operator step; the skill does not redistribute proprietary fonts.

## presentations

For slides and talks, use the `presentation` command. It keeps Archify's
embedded presentation font and produces interactive HTML plus light/dark SVG.
The journal checks apply only to `export`, not to presentation assets.
