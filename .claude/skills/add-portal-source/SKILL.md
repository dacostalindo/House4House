---
name: add-portal-source
description: Bootstrap a new property portal source — dlt resources + Airflow DAG (audit/load_facts/load_refs/validate) + tests + README + wiki/sources page + dbt source YAML entry. Mirrors the existing pattern across 6 portals (idealista, jll, remax, zome, sce). Skill walks Claude through reading the canonical template, asking for the portal-specific params, and generating the file skeleton.
---

Use the add-portal-source skill. Execute `/add-portal-source $ARGUMENTS`:

The argument is the short kebab-case name of the new portal (e.g. `era`, `casa-yes`, `keller-williams-pt`). If not provided, ask the user.

1. Read `wiki/CLAUDE.md` first — sources/ page conventions, P0/P1/P2 priority tiers, required frontmatter, required sections. Read `pipelines/CLAUDE.md` for portal-specific patterns (ZenRows config, SCD2 + heartbeat sidecar, two-pass enrichment).

2. Read the canonical portal template at `pipelines/portals/zome/{__init__.py, source.py, zome_dlt_dag.py}` (the simplest dlt-driven portal — best skeleton to mirror). Read `wiki/sources/zome.md` for the wiki page template. Also read `pipelines/portals/idealista/source.py` to understand the richer pattern (ZenRows two-pass + SCD2 + heartbeat sidecar) — the new portal may need this if it's a scraped portal.

3. Spawn parallel subagents to gather context:
   - **Existing-portals agent**: read `wiki/sources/{idealista,jll,remax,zome,sce}.md` to understand variation across portals (API type, schema, license, crawl scope). Spot collisions: does the proposed name already exist?
   - **Architecture agent**: read [[2026-05-08-idealista-enrichment-architecture]] + [[zenrows-universal-vs-re-api]] + [[scd2-row-hash]] + [[heartbeat-sidecar]] + [[payload-cache-lifecycle]] to understand the architectural choices the new portal must align with.
   - **Collision agent**: verify `wiki/sources/<name>.md` and `pipelines/portals/<name>/` do NOT already exist. If either exists, abort with: "A portal named <name> already exists at <path>. Use `/wiki-reconcile` to update it, or pick a different name."

4. Ask the user for the portal-specific parameters, one at a time (AskUserQuestion):
   - Portal full name + 1-line description
   - Base URL + listing search URL pattern
   - API type:
     - `ZenRows Universal Scraper` (for portals without a public API; HTML scraping)
     - `ZenRows RE API` (for ZenRows Real Estate API integrations — Idealista pattern)
     - `Direct REST` (for portals with a public REST API — Zome pattern)
     - `Pure scraping` (no ZenRows; use nodriver/Playwright — rare)
   - Expected schema: listings? developments? plots? all three?
   - Rate limit (req/sec or req/min)
   - Auto-split logic — how to break the crawl into chunks (`concelho`, `distrito`, `district`, none)
   - SCD2 + heartbeat sidecar needed? (Yes if the portal returns stub-shaped rows that need staleness signal; no for pure REST APIs that return full records)
   - License terms (ToS, robots.txt compliance, scraping legality in Portugal)
   - Priority tier: `P0` (primary listing portal) / `P1` (secondary portal) / `P2` (specialty)

5. Generate the files. Show each proposed file to the user before writing; user approves per file.
   - `pipelines/portals/<name>/__init__.py` (empty)
   - `pipelines/portals/<name>/source.py` — dlt `@dlt.resource` functions (one per entity: listings / developments / plots). Include row_hash logic if SCD2 + heartbeat sidecar selected. Stub the actual API calls — user fills in source-specific URL patterns + JSON paths after the skeleton lands.
   - `pipelines/portals/<name>/<name>_dlt_dag.py` — Airflow DAG with `audit_to_minio` → `load_facts` → `load_refs` (`trigger_rule="all_done"`) → `validate_facts` task chain
   - `pipelines/portals/<name>/tests/__init__.py` (empty)
   - `pipelines/portals/<name>/tests/test_source.py` — stub test for one dlt resource (smoke test that the resource yields valid dicts)
   - `pipelines/portals/<name>/README.md` — short orientation: API type, crawl scope, key files
   - `wiki/sources/<name>.md` — full frontmatter (with `priority:`) + `## For future Claude` preamble + `## Source` (URL, license, API type, crawl scope) + `## Schema` (placeholder for SCD2 tables, heartbeat sidecars, refs) + `## Quirks` (rate limits, auto-split logic, stub handling) + `## Last verified` (today)
   - dbt source YAML entry appended to `dbt/models/staging/listings/_staging_listings__sources.yml` (declares `bronze_listings.raw_<name>` + sidecar tables if applicable)

6. Propagate per the wiki Write rules:
   - Add the new portal to `wiki/index.md` Sources section (alphabetical).
   - Append a one-line entry to `wiki/log.md`: `## [YYYY-MM-DD] add-portal-source | <name> (<P0|P1|P2>) — API: <api-type>`.
   - If the new portal introduces a NEW architectural pattern not covered by existing concepts (e.g. a new scraping technique, new payload-cache lifecycle), draft a `wiki/decisions/<date>-<name>-onboarded.md` ADR proposal. User approves before write.
   - If priority is P0 or P1, propose an update to `wiki/planning/resources.md` data-volume table.

7. Report back:
   - **Files created** (path list)
   - **Wiki propagation done** (index entry, log entry, ADR if drafted, planning updates)
   - **Architectural alignment** (which concepts/decisions the portal aligns with: [[scd2-row-hash]], [[heartbeat-sidecar]], [[zenrows-universal-vs-re-api]], etc.)
   - **Next steps for the user** — (a) fill in source-specific URL patterns + JSON paths in `source.py`; (b) populate ZenRows API key in env if applicable; (c) run the DAG locally via `airflow dags trigger`; (d) validate bronze rows; (e) refine `## Schema` + `## Quirks` after first ingest.

---

**AI-first rule:** Every page created MUST follow `wiki/CLAUDE.md` schema — `## For future Claude` preamble, required frontmatter (with `priority:`), mandatory `[[wikilinks]]` on first mention of cross-referenced concepts/decisions. Skeleton code follows the canonical zome (simple) or idealista (rich) patterns; the user iterates on portal-specific quirks. The skill MUST NOT auto-write a new ADR — if the portal introduces a new pattern, the skill PROPOSES the ADR and the user reviews before write.
