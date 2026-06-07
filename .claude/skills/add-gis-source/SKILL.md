---
name: add-gis-source
description: Bootstrap a new GIS data source — Pydantic config + Airflow DAG (factory-built) + wiki/sources page + dbt source YAML entry. Mirrors the existing pattern across 17 GIS sources (bgri, caop, crus, srup, osm, cos, etc.). Skill walks Claude through reading the canonical template, asking for the params that vary, and generating the file skeleton.
---

Use the add-gis-source skill. Execute `/add-gis-source $ARGUMENTS`:

The argument is the short kebab-case name of the new source (e.g. `lneg-aquifers`, `apa-floodplains`). If not provided, ask the user.

1. Read `wiki/CLAUDE.md` first — sources/ page conventions, P0/P1/P2 priority tiers, required frontmatter (`title`, `type: source`, `last_verified`, `tags`, `priority`), required sections (`## For future Claude`, `## Source`, `## Schema`, `## Quirks`, `## Last verified`). Read `wiki/CLAUDE.md` "Write rules" section so the propagation step in step 6 follows the triad (Search before write / Update-not-duplicate / Propagation).

2. Read the canonical GIS template at `pipelines/gis/bgri/{__init__.py, bgri_config.py, bgri_ingestion_dag.py}` to lock the file shape. Read `wiki/sources/bgri.md` for the wiki page template. Read `pipelines/gis/template/gis_ingestion_template.py` to confirm the `GISIngestionConfig` Pydantic fields the new source must populate.

3. Spawn parallel subagents to gather context:
   - **Existing-sources agent**: read `wiki/sources/{caop,crus,srup,osm,cos}.md` quickly to understand variation across GIS sources (schedule cadence, CRS conventions, format diversity, license patterns). Spot collisions: does the proposed name already exist under any spelling variant?
   - **Domain agent**: determine which dbt staging domain folder the new source belongs in (`geo/`, `regulatory/`, `terrain/`, `hydrology/`, `geology/`, `location/`, `tourism/`, `ine/`). Read `dbt/models/staging/<domain>/_staging_<domain>__sources.yml` to see existing entries the new YAML entry must mirror.
   - **Collision agent**: verify `wiki/sources/<name>.md` and `pipelines/gis/<name>/` do NOT already exist. If either exists, abort the skill with a clear message: "A source named <name> already exists at <path>. Use `/wiki-reconcile` if you want to update it, or pick a different name."

4. Ask the user for the parameters that vary, one at a time (AskUserQuestion):
   - Source full name + 1-line description
   - Download URL or WFS endpoint
   - Expected format (`GeoJSON` / `GPKG` / `Shapefile` / `WFS-GetFeature`)
   - Expected CRS EPSG (commonly `3763` for PT national grid; `4326` for WGS84)
   - Expected layer names (if multi-layer file; comma-separated)
   - Min/max feature count for sanity check
   - Schedule (`@monthly`, `@yearly`, `0 6 * * 1`, etc.)
   - Priority tier: `P0` (foundation) / `P1` (use-case-enabling) / `P2` (specialty)
   - dbt domain folder (from the Domain agent's options)
   - License + source URL for wiki page

5. Generate the files. Show each proposed file to the user before writing; user approves per file.
   - `pipelines/gis/<name>/__init__.py` (empty)
   - `pipelines/gis/<name>/<name>_config.py` — `GISIngestionConfig` instance populated with the user's params
   - `pipelines/gis/<name>/<name>_ingestion_dag.py` — 3-line `from pipelines.gis.<name>.<name>_config import <NAME>_CONFIG` + `from pipelines.gis.template.gis_ingestion_template import create_gis_ingestion_dag` + `dag = create_gis_ingestion_dag(<NAME>_CONFIG)`
   - `wiki/sources/<name>.md` — full frontmatter + `## For future Claude` 2-3-sentence preamble + `## Source` (URL, license, CRS, distributor) + `## Schema` (placeholder for table/layer descriptions; user fills in after first ingest run) + `## Quirks` (placeholder for known gotchas) + `## Last verified` (today's date)
   - dbt source YAML entry appended to `dbt/models/staging/<domain>/_staging_<domain>__sources.yml` — **every column must carry a `description:`** per [[dbt-source-column-descriptions]]. After load, verify `information_schema.columns` count for the bronze table equals the YAML column count equals the dbt manifest column count.

6. Propagate per the wiki Write rules:
   - Add the new source to `wiki/index.md` Sources section (alphabetical position).
   - Append a one-line entry to `wiki/log.md`: `## [YYYY-MM-DD] add-gis-source | <name> (<P0|P1|P2>)`.
   - If the new source crosses a P0/P1/P2 boundary that affects load-order or data-volume estimates, propose an update to `wiki/planning/resources.md` data-volume table. User reviews before write.

7. Report back:
   - **Files created** (path list)
   - **Wiki propagation done** (index entry, log entry, any planning updates)
   - **Next steps for the user** — typically: (a) implement source-specific ingestion logic if the factory skeleton doesn't fit (rare; most GIS sources work with `gis_ingestion_template`); (b) run the DAG locally via `airflow dags trigger <dag_id>`; (c) validate bronze rows land in `bronze_<domain>.raw_<name>`; (d) refine `## Schema` + `## Quirks` in the wiki page after first ingest.

---

**AI-first rule:** Every page created by this skill MUST follow `wiki/CLAUDE.md` schema — `## For future Claude` preamble, required frontmatter (with `priority:` field), mandatory `[[wikilinks]]` on first mention of cross-referenced concepts/decisions/sibling-sources. Skeleton code follows `pipelines/gis/template/gis_ingestion_template.py` exactly; the user iterates on source-specific quirks after the skeleton lands. The skill is the bootstrap mechanism; it does not replace user judgment on the source's downstream silver/gold modeling.
