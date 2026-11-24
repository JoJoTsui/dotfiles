# Research analysis skills (filtered K-Dense subset)

The shared skill tree carries a deliberately small slice of
[K-Dense scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills):
17 skills out of 177, selected for three research axes. The other 160 stay out of
discovery on purpose — a package-level skill that never matches the user's work
still competes for selection on every task.

## Selection

| Axis | Skills |
| --- | --- |
| Single-cell | `scanpy`, `anndata`, `scvi-tools`, `cellxgene-census`, `scvelo`, `arboreto` |
| Variant calling and interpretation | `pysam`, `gtars`, `genomic-coordinates`, `alphagenome`, `genomic-intelligence`, `folklore-variant-evidence`, `gget`, `pacsomatic` |
| Bioinformatics × AI/deep learning | `scvi-tools`, `alphagenome`, `genomic-intelligence`, `pytorch-lightning`, `shap` |
| Local literature | `pyzotero` |

`scvi-tools` serves single-cell and deep learning at once: it is the probabilistic
model layer over AnnData. `pytorch-lightning` and `shap` are the framework and
attribution layer for models the user writes; they are not domain skills.

`pacsomatic` is the only calling-adjacent skill. It prepares and launches the
nf-core/pacsomatic tumor-normal workflow from unaligned BAMs; it is not a caller
and needs Nextflow, Java, and a container runtime outside the skill layer.

`pyzotero` is the library-access layer: Zotero items, collections, tags, and
attachments. Reference validation, citation formatting, and the citation gate
stay with the academic research skills.

Not selected, on purpose: `deepchem` (chemistry/ADMET), `tiledbvcf` (variant
storage), `pathogen-variant-surveillance` (viral epidemiology), `geniml`
(BED-interval embeddings), and the general literature/writing skills
(`literature-review`, `peer-review`, `scientific-writing`, `citation-management`,
`scholar-evaluation`, `paper-lookup`) that duplicate the academic research
skills. Duplicate function is what makes a unified loader route unpredictably.

The catalog pins one commit for all 17 rows. `deployment/skills.tsv` names
`main` and `deployment/skills.lock.tsv` holds the reviewed commit, so an update
is a deliberate lock refresh, not a moving target. The reviewed snapshot is
`c21d13b3cc2894680229ba9959a53281acb9200e` (2026-11-23).

`deployment/skill-budget-exceptions.tsv` records the 14 upstream descriptions
above the 240-character budget, with their measured values and the reason the
bytes are not rewritten.

## Environments

The three stacks are mutually incompatible, so each keeps its own environment
under `~/.venvs`. `deployment/kdense/ensure_envs.sh` creates or reconciles all
three from the pinned requirements files; it is idempotent and never installs
into the system Python or an agent host runtime. Run it after the first
deployment and after any lock refresh — the skill catalog deploys bytes, not
Python packages.

| Environment | Python | Requirements | Serves |
| --- | --- | --- | --- |
| `kdense-research` | 3.13 | `requirements-core.txt` | scanpy, anndata, scvi-tools, pysam, gtars, shap, lightning, gget, alphagenome, cellxgene-census, pyzotero |
| `kdense-scvelo` | 3.13 | `requirements-velocity.txt` | scVelo velocity stack |
| `kdense-arboreto` | 3.11 | `requirements-grn.txt` | Arboreto GRN stack |

Run a skill's helper with its environment's interpreter, never the ambient one:

```bash
~/.venvs/kdense-research/bin/python <skill>/scripts/<script>.py
~/.venvs/kdense-scvelo/bin/python    <skill>/scripts/<script>.py
~/.venvs/kdense-arboreto/bin/python  <skill>/scripts/<script>.py
```

Arboreto needs the legacy Dask dataframe backend selected before import; the
skill's bundled wrapper does it, and the environment check does the same:

```python
import dask
dask.config.set({"dataframe.query-planning": False})  # see requirements-grn.txt
```

Skills that need network or credentials say so in their own `compatibility:`
field: `alphagenome` needs `ALPHAGENOME_API_KEY`, `genomic-intelligence` accepts
`GI_API_KEY` (its demo tier is keyless), `folklore-variant-evidence` uses a
credential-free public MCP endpoint, and `pyzotero` needs a Zotero API key for
private libraries.

## Routing against the academic research skills

The two families are sequential, not alternatives. The analysis skills produce
artifacts — `.h5ad`, VCF/BAM derivatives, effect scores, cohort summaries — and
the academic research skills consume them for methods, results, review, and
submission.

- Analysis request → the package skill. Writing, review, citation, and journal
  fit → the academic research skills, always.
- Evidence about one variant → `folklore-variant-evidence`. Literature synthesis
  on a question → `deep-research`.
- A gene, disease, or Census fact → `gget` or `cellxgene-census`. What the
  literature says about it → the academic research skills.
- Variant effect prediction → `alphagenome` or `genomic-intelligence`; the
  write-up of that prediction → the academic research skills.

## Gaps

No raw read-to-VCF caller is in the catalog. `pacsomatic` launches a calling
workflow but is not a caller. DeepVariant, GATK, bcftools, or scDeepVariant run
outside the skill layer, and their VCF output feeds `pysam`,
`genomic-coordinates`, and `gtars`, then the annotation skills. Clinical-grade
annotation (VEP, ANNOVAR, ClinVar) and custom model research — fine-tuning
single-cell foundation models, designing variant-effect architectures — are also
outside the catalog.

## Changing the subset

Add a row to `deployment/skills.tsv` and refresh the lock with
`python3 deployment/update_skills.py refresh`; the refresh re-resolves every
row, so review the resulting diff before committing. Removing a skill is a
catalog deletion plus a lock refresh. A removed skill's directory is pruned from
each managed root on the next deployment because the inventory records it.
