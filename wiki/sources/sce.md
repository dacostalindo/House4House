---
title: SCE — Sistema de Certificação Energética
type: source
last_verified: 2026-05-17
tags: [scraper, regulatory, government, energy, nodriver, geocoding, buildings-clustering]
priority: P1
---

## For future Claude

This is a source page about SCE (Energy Certificate Registry), the only nodriver-based scraper in our stack. It documents the Cloudflare-Turnstile-protected scrape strategy, the per-distrito Airflow task topology, and the deliberate scope-narrowing to 1 distrito (Aveiro) until full-country coverage is justified. Read this page before editing [pipelines/scraping/sce/sce_config.py](../../pipelines/scraping/sce/sce_config.py) or its DAG.

## Source

- **Official name**: SCE — Sistema de Certificação Energética dos Edifícios
- **Owner**: government agency (ADENE — Agência para a Energia, on behalf of regulator)
- **Protocol**: HTML scrape via nodriver (undetected Chrome) — Cloudflare Turnstile challenge in path
- **Base endpoint**: `https://www.sce.pt/wp-content/plugins/sce-pesquisa-certificados/functions.php` (form-POST endpoint behind WordPress plugin)
- **License**: public registry (energy certificates are mandatory and publicly searchable; no API offered)
- **Schedule**: manual trigger only — scope-narrow + brittle scraper, run on demand

## Schema

Bronze table: `bronze_regulatory.raw_sce_certificates` — 22 fields per certificate row.

- **PK / dedup**: `(doc_number, _batch_id)` UNIQUE constraint (per [[scd2-row-hash]] philosophy applied to scraper output)
- **Address fields**: `morada`, `fracao`, `localidade`, `concelho` (links to [[caop]] municipalities)
- **Certificate state**: `estado` (active/expired), `clase_energetica` (A+ down to F), `data_emissao`, `data_validade`
- **Query metadata**: `query_distrito`, `query_concelho`, `query_freguesia` (records which crawl-axis produced the row, for backfill traceability), `_scrape_date`

## Quirks

- **Only nodriver scraper in the stack**: Cloudflare Turnstile protection requires undetected Chrome with real rendering. Headed mode required (Xvfb on the Airflow worker provides the display). The `BROWSER_RESTART_EVERY=500_REQUESTS` setting recycles Chrome to prevent fingerprint accumulation — required for sustained Cloudflare evasion.
- **Cloudflare Turnstile**: nodriver's 15-second wait window handles the challenge; failures are transient (re-run the task).
- **Full-country backfill estimate**: ~680k records, 1-2 days of crawl time across all 22 distritos. Current Aveiro-only scope is ~30-50k records.
- **Currently scoped to 1 distrito (Aveiro)**: the docstring lists 22 distritos commented out in the config. Uncomment them when ready for full-country coverage; each adds ~10-30 minutes of crawl time. Per the original docstring: "3 distritos (Aveiro, Coimbra, Leiria) — initial scope matching core coverage area" (note: scope was further narrowed to Aveiro only post-config edit).
- **Concelhos fetched dynamically**: the SCE search form's distrito dropdown returns the concelho list at scrape-time. We don't hardcode the concelho mapping — saves us from drift when ADENE adds/renames municipalities.
- **Per-distrito Airflow task** topology: each distrito = 1 task, iterating all concelhos within. Distrito-level parallelism keeps task duration bounded.
- **No incremental fetch**: every run re-scrapes the full active-certificate set within scope. Dedup happens on the UNIQUE constraint at insert time.
- **Cross-source role**: SCE is the only authoritative source for PT energy-certificate data (mandatory pre-listing, but portals like [[idealista]] only sometimes show the rating). Joining SCE on (concelho, address) lets us validate listing-claimed energy ratings against the registry.

## Geocoding (Sprint-08 Activity 7, 2026-05-15)

SCE bronze rows carry `morada` + `fracao` + `localidade` + `concelho` as **text only — no coordinates**. The [[sprint-08]] Activity 7 pipeline (`pipelines/enrichment/sce_geocode_dag.py`) inserts itself into the SCE chain to add them:

```
sce_ingestion → sce_bronze_load → sce_geocode → dbt_sce_build
```

`sce_geocode` is incremental on `doc_number NOT IN bronze_enrichment.raw_sce_geocoded`. Cascade per row:

1. **Nominatim forward-geocode** of `geocode_query(morada, freguesia_detail, concelho)` against the local Nominatim Docker. Top hit → `geocode_source='nominatim'`, `geocode_confidence` = Nominatim's `importance` (0.0–1.0). Aveiro concelho hit rate ~46 %.
2. **Freguesia centroid** via `gold_analytics.dim_geography` keyed on the 6-digit DTMNFR reconstructed from `LPAD-2(query_distrito) || LPAD-2(query_concelho) || LPAD-2(query_freguesia)`. → `geocode_source='freguesia_centroid'`, `geocode_confidence=0.2`.
3. **Unresolved** → NULL coords, `geocode_source='none'`, `geocode_confidence=0`.

The result lands in `bronze_enrichment.raw_sce_geocoded(doc_number PK, address_lat, address_lng, geocode_source, geocode_confidence, normalized_address, nominatim_display, _geocoded_at)`. `dbt_sce_build` then LEFT-JOINs this into [`stg_sce_certificates`](../../dbt/models/staging/regulatory/stg_sce_certificates.sql), adding `geom_4326` / `geom_3763` derived columns for sprint-09 Slice B's `silver_sce_buildings` clustering.

The `normalized_address` column is the clustering key from [pipelines/enrichment/sce_address_norm.py](../../pipelines/enrichment/sce_address_norm.py) — the Appendix-A normalization rules (PT real-estate abbreviation expansion + fração-marker stripping + diacritic-fold + concelho disambiguator), validated against 6,000 rows at 0% leakage and a 44.2% function-attributable collapse rate. Sprint-09 Slice B consumes it for the within-cluster dedup step of `silver_sce_buildings` — see [[sce-buildings-clustering]] for the locked design (DBSCAN(30m) + exact-match GROUP BY; Levenshtein deferred to v1.5).

**Coverage (2026-05-15 first run on Aveiro distrito, 55,766 distinct doc_numbers):**

| Concelho | With coords | Nominatim (street-level) | Freguesia centroid (parish-level) |
|---|---|---|---|
| **AVEIRO** (v1 demo target) | **100.0%** | 46.3% | 53.7% |
| Anadia / Albergaria / Arouca / Ílhavo / Murtosa / Oliveira do Bairro / S. João da Madeira / Vale de Cambra | 100.0% | varies (35-60%) | balance |
| Estarreja | 81.6% | 49.3% | balance |
| Águeda / Sever do Vouga | 71-76% | ~30% | balance |
| Espinho / Ovar / Santa Maria da Feira / Mealhada / Vagos | 54-67% | ~35% | partial; **post-2013-union freguesias don't resolve** |
| Castelo de Paiva | 32.9% | 12.3% | partial — heavily affected by the union issue |
| **Distrito-wide** | **83.78%** | 37.6% | 46.1% (+16.2% NULL) |

**Known limitation — post-2013 union-of-freguesias**: `dim_geography` (CAOP 2025) still carries the pre-2013-reform separate freguesias (e.g. `Anta` 010707 + `Guetim` 010708), but the SCE scrape captures the post-2013 union codes (e.g. 010706 = "ANTA E GUETIM"). Affects 19 union freguesias across Aveiro distrito → 9,047 docs (16.2 %) at `geocode_source='none'`. **Aveiro concelho is not affected** (no union-reformed parishes there), so v1 demo coverage is unimpacted. National rollout will need a CAOP-union mapping table — tracked in [[sprint-09]] under "Deferred from Sprint-08 — freguesia-union mapping".

## Last verified

2026-05-17 (Sprint-09 Slice B — `silver_sce_buildings` body-fill consumed `normalized_address` for the clustering surface, validating end-to-end. See [[sce-buildings-clustering]] for the locked clustering design. Sprint-09 also queues an SCE-bronze refactor: replace-not-append via UPSERT-by-doc_number; the current `(doc_number, _batch_id)` UNIQUE will become `PRIMARY KEY (doc_number)` with `_last_seen_at` heartbeat. Scrape-history dedup will move from staging DISTINCT ON to bronze-level.)
