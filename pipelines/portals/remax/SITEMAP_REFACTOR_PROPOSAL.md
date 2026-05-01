# Proposal: REMAX housing via sitemap+Next.js (12× coverage gain)

> Status: investigation only — NOT implemented. Decision needed before proceeding.

## What we discovered (during plot ingestion work)

The plot ingestion path (`/sitemap.xml` → 4 detail sitemaps → Next.js
`_next/data/.../imoveis/{slug}/{title}.json`) returns the **exact same
162-field payload** for housing listings as it does for plots — including
`listingRooms` (the per-room breakdown with sizes, types, descriptions),
`marketDays`, `previousPrice`, `lotSize`, agency info, all 30+ fields the
existing pipeline assembles from Pass 1+2.

## Coverage comparison

Probe results (2026-04-28):

| Source | Total listings exposed |
|---|---|
| Current `/api/Development/PaginatedSearch` Pass 1 (housing only) | 654 developments → ~3,900 listings |
| **REMAX sitemap.xml (4 PT detail sitemaps)** | **47,205 listings** (15,296 apt + 11,655 villa + 12,493 plot + 7,761 other) |

The current pipeline systematically misses **~30,000 standalone housing
listings** (apartments and villas not part of a development complex).
Plots are also undercounted (656 from PaginatedSearch vs 12,493 in sitemap),
which is why the new plot ingestion uses sitemap.

## Migration would consolidate two approaches into one

```
                Current                          Proposed
              ┌────────────────┐               ┌────────────────┐
  Housing    │ PaginatedSearch │              │   sitemap.xml  │
              └────────┬───────┘               └────────┬───────┘
                       │                                │
                       v                                v
              ┌────────────────┐               ┌────────────────┐
              │  Next.js Pass2 │              │  Next.js Pass2 │
              └────────┬───────┘               └────────┬───────┘
                       v                                │
       ┌───────────────┴───────┐               ┌────────┴───────┐
       v                       v               v                v
remax_developments    remax_listings    (all 47k listings) (all 12k plots)
       │                       │               │                │
                        Plots: NEW: sitemap     │                │
                                v               v                v
                        remax_plots          remax_listings  remax_plots
                                              (housing only)   (filter listingTypeID=21)
```

## Pros

- **12× coverage gain**: 3,900 → 47,205 listings.
- **Single discovery primitive**: sitemap drives both housing and plot ingestion;
  one fetch path, one rate-limit profile, one failure mode.
- **No more development↔listing 1:N modelling**. `remax_developments` becomes
  derivable from `remax_listings.development_id` — could either keep both
  tables (current) or denormalize into `remax_listings` only.
- **Same per-listing data quality** (162 fields, including `listingRooms`).
- **Free** — no API cost change.

## Cons

- **Big change**. ~50k listings × Pass 2 fetch at ~1 req/s × 4 workers
  = ~3.5 hours per run. Current pipeline runs ~30 min. Acceptable for weekly
  cadence but not daily.
- **Loses the rich `developments` payload** from PaginatedSearch — the dev-level
  fields (`buildingPictures`, `descriptionBodies`, `developmentPicture`) only
  appear in PaginatedSearch responses. Would need to keep BOTH paths if
  developments are needed as a separate grain.
- **Sitemap throttling unknown.** REMAX may rate-limit if we hit all 4 sitemaps
  (~5MB each) every weekly run. Could mitigate with `If-Modified-Since`.
- **SCD2 churn**: existing `remax_listings` has 19 version columns tuned to
  the PaginatedSearch unit schema. Sitemap-discovered listings may have NULL
  in some of those columns (e.g. `typology_id` for plots), which could
  introduce phantom SCD2 versions on the first migration cutover.
- **Migration complexity**: existing rows would need to be matched by
  `listing_id` between the two paths. Listings present in PaginatedSearch
  but not in sitemap (or vice versa) would create gaps/duplicates during cutover.

## Recommended path (if we proceed)

1. **Don't replace the PaginatedSearch path yet.** Instead, add a parallel
   `remax_listings_sitemap` table fed by sitemap+Next.js. Keep the current
   `remax_listings` and `remax_developments` untouched.
2. **Run both for ~4 weeks** to compare:
   - Field-by-field coverage on overlapping listing_ids
   - Coverage gap (count of listing_ids exclusive to each path)
   - SCD2 transition rate (how often does each path open new versions)
3. **Migration decision** based on data:
   - If sitemap covers ≥99% of PaginatedSearch + adds the ~30k delta cleanly,
     deprecate PaginatedSearch (keeping only `remax_developments` from it for
     dev-level analytics).
   - Otherwise, ship sitemap as a parallel `remax_listings_sitemap` table and
     let dbt union them.

## Estimated scope

- ~150 lines of code in `remax/source.py` (new `_fetch_all_listings_sitemap`,
  `_normalize_listing_from_sitemap`, parallel resources).
- New table `remax_listings_sitemap` + heartbeat sidecar.
- ~80 lines in DAG validation.
- Updates to `CUTOVER.md` + `PLOTS_RULES.md` + new `SITEMAP_RULES.md`.
- 4-week shadow-run phase before any deprecation.

## Decision required

Pick one:
- **(A)** Proceed now with the parallel-table approach (no risk to existing pipeline).
- **(B)** Ship plots first (already done), monitor for 1-2 weeks, then decide.
- **(C)** Defer indefinitely — the current housing pipeline is sufficient.

I'd recommend **(B)**: plots are in production (this PR), and the same sitemap
infrastructure I just shipped (`_fetch_all_plots`) is the foundation for any
future housing-via-sitemap work. Two weeks of plot-pipeline operational data
will inform whether the same approach scales to 12× the volume.
