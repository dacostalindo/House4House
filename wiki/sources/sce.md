---
title: SCE — Sistema de Certificação Energética
type: source
last_verified: 2026-05-08
tags: [scraper, regulatory, government, energy, nodriver]
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

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; current scope is Aveiro distrito only).
