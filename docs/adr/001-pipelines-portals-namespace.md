# ADR 001 — `pipelines/portals/` namespace + dbt-sources-as-canonical column docs

**Status:** Accepted (Sprint 4.4, Week 8.5, 2026-04-30)
**Decision-makers:** Sprint 4.4 prep work, in service of Sprint 4.5 cross-portal dedup.

## Context

Three real-estate listing portals (RE/MAX, Idealista, Zome) lived under `pipelines/api/{remax,idealista,zome}/` alongside macroeconomic API pipelines (bpstat, ecb, eurostat, ine). They shared neither domain nor implementation pattern:

- Portals use `dlt` for SCD2 ingestion; macro APIs use the `BronzeTableConfig` pattern (mostly) plus custom DAGs.
- Portals produce `bronze_listings.*` tables; macros produce `bronze_economic.*`, `bronze_regulatory.*`, etc.
- Portals will share a matching framework (forthcoming, Sprint 4.5) and canonical silver models (`developments_canonical`, `unified_listings`); the macro APIs are mostly independent silver models.

In addition, the three portal bronze tables (10 SCD2 fact tables — `*_developments`, `*_listings`, `*_plots`) had no dbt source declarations except for legacy `raw_idealista`. Sprint 4.5's staging models can't reference them via `{{ source(...) }}` until they're declared.

Finally, READMEs covered system architecture (SCD2 mechanics, lifecycle rules) but not column-by-column meanings. Anyone writing a silver model had to reverse-engineer from `source.py`.

This ADR captures the conventions adopted in Sprint 4.4 to address all three gaps.

## Decisions

### 1. Folder rename: `pipelines/api/{remax,idealista,zome}/` → `pipelines/portals/`

Domain-named directory disambiguates listing portals from macroeconomic APIs.

**Rejected alternatives:**
- `pipelines/listings/` — collides with the `bronze_listings` schema name. Misleading because the directory contains developments and plots too, not only listings.
- `pipelines/scrapers/` — `pipelines/scraping/` already exists for the SCE Selenium-based scraper. Two scraping folders is worse than the current split.
- `pipelines/realestate/` — too generic; future-proofs for non-portal sources but not needed yet.

**Consequences:**
- Future portal additions (ERA, C21, KW in Sprint 4.6) land at `pipelines/portals/{name}/` from day one.
- The matching framework (Sprint 4.5) imports from `pipelines.portals.X` — clean import path matches the domain.
- Two existing user worktrees (`dacostalindo/senior-code-review`, `dacostalindo/explore-viking-agents`) still hold pre-rename `pipelines/api/` paths. If those branches are rebased onto post-rename main, the user resolves the merge conflict manually.

### 2. dbt sources YAML is the canonical column-documentation store

Column-level descriptions, source-path mappings, and gotchas live in `dbt/models/staging/listings/_staging_listings__sources.yml` under each source's `columns:` block. Markdown READMEs and dbt-docs renderings are derived from this YAML.

**Why YAML primary instead of markdown:**
- Single source of truth — no drift between formats.
- Renders automatically in dbt-docs UI (the panel users open to navigate the catalog).
- dbt schema tests can attach directly to documented columns (e.g., `not_null`, `unique`, custom tests).
- Source declarations are discoverable via `dbt ls --select source:bronze_listings.X`.

**Rejected alternatives:**
- Markdown READMEs as primary, YAML auto-generated. Markdown would have to be parsed back to YAML for dbt-docs/tests — more drift risk.
- Both maintained separately. Higher upkeep cost; drift was the original problem.

**Consequences:**
- Anyone updating column documentation edits the YAML.
- The cross-pipeline column-dictionary generator (`pipelines/common/tools/generate_column_dictionary.py`) emits YAML by default, with markdown as a derived format.
- Adding a new portal = new bronze tables → declare in YAML → run generator → curate descriptions, source paths, notes.

### 3. `pipelines/common/tools/` is the new home for cross-pipeline Python utilities

Up to Sprint 4.4, `pipelines/common/` was deliberately doc-only — convention-reference markdowns (`NAMING_CONVENTIONS.md`, `SCD2_RULES.md`, `PLOTS_RULES.md`, `README_DLT_TEMPLATE.md`), not importable code. Those convention docs were migrated to `wiki/concepts/{portal-naming-conventions,scd2-row-hash,portal-plot-conventions,portal-field-map}.md` in 2026-05-12 so the wiki is the single source of truth.

Workstream C (column-dictionary generator) introduced the first cross-pipeline Python utility. The convention now is:

- `wiki/concepts/*.md` — conventions, design docs, cross-pipeline rules (single source of truth).
- `pipelines/common/tools/` — reusable Python utilities for cross-pipeline use. Importable as `pipelines.common.tools.X`.
- `pipelines/common/*.py` — cross-pipeline Python helpers (e.g. `minio_upload.py`).
- `scripts/` (repo root) — one-off operational tooling, scratch analysis, throwaway scripts.

**Rejected alternative:** put the generator in `scripts/` (repo root). Scripts there have a "throwaway tooling" vibe (look at the contents: `am48_scrape_results.json`, `analyze_survey.py`, etc.). A reusable utility called from multiple pipelines deserves a proper home in the package layout.

**Consequences:**
- Future shared utilities go in `pipelines/common/tools/`.
- ERA/C21/KW (Sprint 4.6) and the SCE/INE/BPStat backfill (Sprint 9) use the generator from this location.

### 4. Manual cadence for column-dictionary generation

The generator is a **shipping-checklist tool, not an always-on pipeline.** It's invoked manually:

- When a new bronze table ships (one-time per table).
- When a schema change happens on an existing bronze table.
- When adding a new portal.
- During sprint backfills (e.g., Sprint 9 for SCE/INE).
- Quarterly stats-drift sanity check (ad hoc).

**Why not automate:**
- Auto-running on every bronze load is wasteful — the output is mostly stable; column meanings don't change every run.
- The valuable layer is human-curated (`description`, `source_path`, `notes`). Auto-running doesn't help with that — it'd regenerate auto-stats and either overwrite curation or require complex merge logic.
- Premature automation here is a bigger sin than slight friction.

**Future consideration:** if cadence becomes painful after Sprint 4.6, a monthly drift-detection CI job could compare auto-stats against committed YAML and surface diffs (without auto-editing).

**Pipeline ship checklist** (documented as Sprint 4.4 outcome):

```
□ Bronze DAG runs end-to-end successfully
□ Source declared in dbt sources YAML
□ Run column-dictionary generator → curate descriptions, source paths, notes
□ Append rendered markdown to portal README (if README exists)
□ Generate fixture file for tests/fixtures/ (if test surface needs it)
□ Verify dbt parse + dbt docs generate succeed
```

### 5. `archive/` at repo root for retired-but-kept-for-history files

Workstream A moved the dlt cutover artifacts (`CUTOVER.md` and `rollback_*.sql` per portal) out of the active pipeline directories into `archive/portal_dlt_cutover_2026/`. This establishes a convention.

**Convention:** completed migrations, deprecated configs, sunset implementations move to `archive/{topic}_{year}/` rather than living indefinitely in active source trees. Path references inside archived files are NOT updated — they capture the layout at the time the work was done.

**Consequences:**
- Future migrations follow the same pattern.
- Engineers searching for "where's the rollback SQL?" learn to look in `archive/` if not in the portal directory.
- Cleaner mental model when navigating active source trees.

### 6. Test fixtures committed without anonymization (private-repo contingency)

`tests/fixtures/portals/{portal}/{table}.jsonl` — 5 representative rows per bronze table, generated by the column-dictionary generator with `--format fixtures`. PII (agent names, phones, emails) committed as-is.

**Acceptable only if the repo stays private.** If repo visibility ever changes, fixtures must be scrubbed via `git filter-repo` (which rewrites SHAs and breaks every clone — not a casual fix).

This was a deliberate trade-off: iteration speed and test reproducibility weighed against PII liability, with private-repo status as the safety belt.

## Out-of-scope (deferred to future sprints)

- **Backfilled ADRs for past major decisions** — `docs/adr/_backlog.md` enumerates 6 stubs (002–007) for Sprint 9 production-hardening backfill.
- **dbt source freshness configuration** — sources declared without `loaded_at_field`. Freshness gates will attach in Sprint 4.5 silver work where lifecycle metadata gets surfaced.
- **Auto-running column-dictionary drift detection** — not implemented; revisit if manual cadence becomes painful in Sprint 4.6+.

## References

- Sprint 4.4 plan: see `## Sprint 4.4` section in repo-root [README.md](../../README.md).
- Cross-portal field map: [`wiki/concepts/portal-field-map.md`](../../wiki/concepts/portal-field-map.md).
- Column-dictionary generator: [`pipelines/common/tools/generate_column_dictionary.py`](../../pipelines/common/tools/generate_column_dictionary.py).
- Portal source declarations: [`dbt/models/staging/listings/_staging_listings__sources.yml`](../../dbt/models/staging/listings/_staging_listings__sources.yml).
- Archive of pre-rename migration docs: [`archive/portal_dlt_cutover_2026/README.md`](../../archive/portal_dlt_cutover_2026/README.md).
- ADR backlog: [`_backlog.md`](_backlog.md).
