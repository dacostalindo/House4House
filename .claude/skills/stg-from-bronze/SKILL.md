---
name: stg-from-bronze
description: Bootstrap a dbt staging model from a bronze table — type casts, NULL guards, CRS reprojection for geom columns, dbt-utils tests. Mirrors the existing pattern across 21+ staging models in 6 domains. Skill reads the bronze YAML declaration + a canonical sibling stg model + the source's wiki page, then proposes the SQL + YAML.
---

Use the stg-from-bronze skill. Execute `/stg-from-bronze $ARGUMENTS`:

The argument is the bronze table name (e.g. `bronze_listings.raw_idealista`, `bronze_regulatory.raw_srup_ran`). If not provided, list candidate bronze tables (from the dbt source YAMLs) for the user to pick from.

1. Read `dbt/CLAUDE.md` first — staging model conventions (no `SELECT *`, explicit casts, NULL guards in WHERE, dbt-utils tests), domain folder layout, naming convention `stg_<source>_<entity>.sql`. Read `wiki/concepts/medallion-layering.md` for the bronze→silver semantics.

2. Determine the target file path:
   - Bronze table `bronze_<domain>.raw_<source>_<entity>` → silver staging at `dbt/models/staging/<domain>/stg_<source>_<entity>.sql` + sibling `stg_<source>_<entity>.yml` (dbt-utils tests).
   - If the source name and entity name are the same (e.g. `bronze_listings.raw_idealista` is one-table-one-source), drop the entity suffix: `stg_idealista.sql`.

3. Spawn parallel subagents:
   - **Source-schema agent**: read the bronze source's dbt YAML declaration in `dbt/models/staging/<domain>/_staging_<domain>__sources.yml`. Identify column names, types, geom columns, JSONB columns. If the bronze table is not declared in any dbt source YAML, abort with: "Bronze table <name> is not declared in any dbt source YAML. Add the declaration first, then re-run this skill."
   - **Wiki-source agent**: read `wiki/sources/<source>.md` to understand the source's quirks (CRS convention, NULL conventions, schema drift patterns, JSONB shapes if the bronze stores raw JSON).
   - **Existing-stg agent**: read 2-3 sibling `stg_*.sql` files in the same domain folder to learn the project's specific patterns (alias conventions, WHERE guards, dbt_utils.surrogate_key usage, ST_Transform target CRS, JSONB extract idioms).

4. Propose the staging model. Show the user the proposed SQL + YAML before writing; user approves per file.
   - **`dbt/models/staging/<domain>/stg_<source>_<entity>.sql`**:
     - `SELECT` aliasing bronze columns to silver-friendly names (e.g. `property_price AS price_eur`, `freguesia_dicofre AS freguesia_code`)
     - Explicit type casts (`::TEXT`, `::NUMERIC`, `::DATE`, `::INTEGER`, `::BOOLEAN`)
     - JSONB extracts: `->>` for scalars (returns TEXT), `->` for nested objects (returns JSONB)
     - For geom columns: `ST_Transform(geom, <target_epsg>) AS geom` — typically target `3763` (PT national grid for distance/area in meters) per [[2026-05-10-dual-crs-storage]]
     - NULL guards in WHERE on the primary key column(s): `WHERE <pk_column> IS NOT NULL`
     - NO `SELECT *`; every column listed explicitly
   - **`dbt/models/staging/<domain>/stg_<source>_<entity>.yml`** (sibling tests):
     - `dbt_utils.unique_combination_of_columns` on the primary key (or `unique` test on a single-column PK)
     - `not_null` tests on required columns (PK + business-critical fields)
     - `accepted_values` tests where the source has known-enum columns

5. Write the files (user-approved per file).

6. Propagate per the wiki Write rules:
   - If this is the FIRST staging model for the source (i.e. no prior `stg_<source>_*.sql` files exist), append a line to `wiki/sources/<source>.md` `## Schema` section noting that silver lands at `<domain>.stg_<source>_<entity>`. If subsequent staging models for the same source land, the line gets extended (don't create a duplicate Schema section).
   - Append a one-line entry to `wiki/log.md`: `## [YYYY-MM-DD] stg-from-bronze | <domain>.stg_<source>_<entity>`.

7. Report back:
   - **Files created** (SQL + YAML paths, full relative paths from repo root)
   - **Tests defined** (list each: e.g., "unique on `listing_id`", "not_null on `price_eur`, `freguesia_code`")
   - **Geom handling** (if applicable: "ST_Transform to EPSG 3763; original SRID was <X>")
   - **Next steps for the user** — (a) run `dbt build --select stg_<source>_<entity>` against the local warehouse; (b) review row count vs bronze row count (expect within 1-2% if any NULL-PK rows were dropped); (c) review null distribution per column; (d) if downstream silver/gold marts depend on this staging model, surface them as separate work.

---

**AI-first rule:** The generated SQL MUST follow `dbt/CLAUDE.md` conventions — alias bronze columns to silver names, cast types explicitly, guard NULLs in WHERE, never `SELECT *`. dbt-utils tests are mandatory at minimum (unique + not_null on PK). Geom columns MUST go through `ST_Transform(geom, 3763)` for the metric-meaningful PT national grid (per [[2026-05-10-dual-crs-storage]]) unless the source's wiki page documents an explicit reason for a different target CRS.
