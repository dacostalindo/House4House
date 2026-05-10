---
title: Metabase + Streamlit + Kepler.gl — not Superset
type: decision
last_verified: 2026-05-10
tags: [bi, viz, metabase, streamlit, kepler, decision]
confidence: medium
---

## For future Claude

This is a decision record about using Metabase for traditional BI + Streamlit (with embedded Kepler.gl) for custom apps + spatial viz, rejecting Superset and dbt-cloud-style BI. Read this before adding a new dashboard, considering a BI-tool migration, or scoping the analyst-surface.

## Decision

Two analyst surfaces:

- **Metabase 0.48+** (Docker, port `3000`) — traditional BI dashboards. Hosts the **Investment Board** (UC-1) and **Pricing Board** (UC-2) per the README serving-layer plan.
- **Streamlit 1.30+** (Docker, port `8501`) — custom apps + spatial viz. Hosts the property valuator + pricing simulator + site analyzer + Kepler.gl maps via `streamlit-keplergl`. Spatial visualization integrates Kepler.gl directly into Streamlit pages.

`confidence: medium` because the analyst-surface choice may shift if usage patterns surface different needs (e.g., heavy ad-hoc analysis might pull toward Superset's SQL Lab; heavy spatial-first might pull toward a dedicated Kepler.gl viewer).

## Why

1. **Two surfaces beat one.** Metabase is best-in-class for "click-to-build dashboard" workflows. Streamlit is best-in-class for "Python-driven custom UIs with maps + interactive widgets." Trying to use one tool for both surfaces compromises somewhere — Superset's custom-app story is weaker than Streamlit; Streamlit's quick-dashboard story is weaker than Metabase.
2. **Metabase's curve is gentle.** A Director can self-serve a dashboard against PostGIS in minutes — "drag column X, group by Y, line chart, save." That non-technical-self-service property is load-bearing for the Pricing Board (UC-2 commercial directors).
3. **Streamlit + Kepler.gl is the spatial path.** Kepler.gl is the strongest WebGL spatial-viz library (Uber-built, mature, performant for ~100k features). Streamlit-keplergl wraps it cleanly. Embedding Kepler.gl in Streamlit pages handles the UC-1 Property Map + UC-3 Site Analyzer flows where map interactivity is the primary UX.
4. **Both are Docker-friendly self-hosted.** Metabase image runs out of the box; Streamlit is built from `apps/Dockerfile`. Both fit the [[2026-05-10-single-server-self-hosted]] posture.

## Options considered

1. **Metabase + Streamlit + Kepler.gl** (chosen) — two surfaces, complementary.
2. **Apache Superset only** — open-source BI with strong SQL Lab + ad-hoc charting. Rejected because (a) custom apps with map interactivity require Superset to host iframes / external apps anyway, (b) Superset's UI has steeper curve than Metabase for non-technical Directors, (c) Superset's spatial story is thinner than Streamlit + Kepler.gl.
3. **Looker / Tableau / PowerBI** — commercial BI. Rejected on cost (per-seat licenses) + lock-in concerns + over-featured for solo-dev needs.
4. **dbt Cloud + dbt-explorer** — dbt's own visualization. Useful for model-graph visualization but not for end-user dashboards.
5. **Custom dashboarding from scratch (React + d3)** — rejected as infinite scope creep for solo-dev. Use existing tools.
6. **Just Streamlit (no Metabase)** — would force every dashboard to be a Streamlit page. Rejected because non-technical Directors can't self-serve in Streamlit; they'd need a developer to build every dashboard.
7. **Just Metabase (no Streamlit)** — would force the property valuator + pricing simulator + site analyzer to be Metabase Question + Card hacks. Rejected because those are interactive Python apps with custom widgets, not dashboards.

## Consequences

- Metabase serves traditional dashboards; Streamlit serves custom apps. The boundary is "is this a dashboard (drag-and-drop config) or an app (Python-driven UI)?"
- UC-1 Investment Board lives in Metabase; UC-1 Property Map lives in Streamlit (Kepler.gl).
- UC-2 Pricing Board lives in Metabase; UC-2 Pricing Simulator lives in Streamlit.
- UC-3 Site Analyzer lives entirely in Streamlit (interactive parcel selection + Kepler.gl visualization).
- Future migration paths: if Metabase fails to scale or licensing changes, swap to Superset (similar dashboards, more SQL-power). If Streamlit fails to scale or perf degrades, swap to FastAPI + React custom UIs (more work but more flexible).
- Confidence is `medium` rather than `high` because the analyst-surface workflow hasn't been battle-tested at scale yet; UC-1 hasn't shipped, so dashboard usage patterns are projections.

## Status

`accepted` — UC-1 + UC-2 + UC-3 sprint plans assume this analyst-surface architecture. Operational stability TBD (Metabase + Streamlit not yet hosting production dashboards). Will revisit confidence to `high` after UC-1 MVP ships at sprint-06.

## See also

- [[2026-05-10-single-server-self-hosted]] — both run on the same self-hosted box
- [[UC-1]] — Investment Board (Metabase) + Property Map (Streamlit) + Hedonic Explorer (Streamlit)
- [[UC-2]] — Pricing Board (Metabase) + Pricing Simulator (Streamlit)
- [[UC-3]] — Site Analyzer (Streamlit)
- [[infra]] — Docker Compose service map for Metabase + Streamlit
- [[tech-stack]] — primary stack table
- README §3.1 + §17 (Serving Layer) — the canonical source for this content
