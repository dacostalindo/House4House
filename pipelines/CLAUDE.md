# pipelines/ — Claude Code rules

## Schema for Claude Code (read this first)

Before editing files in this area, **read the wiki/concepts/ page(s) mapped to your task type below**. Don't read every page on every edit — read the ones relevant to what you're touching. The wiki is the project's source of truth for rules and patterns; this file routes you.

If you violate a rule because you didn't read its wiki page, that's a schema-compliance failure. The pointer-following is an obligation, not a hope.

## Task → concepts routing

| If you're editing… | Read |
|---|---|
| A dlt resource (`source.py`, `*_dlt.py`, `*_dlt_dag.py`) | [wiki/concepts/pydantic-not-in-dlt.md](../wiki/concepts/pydantic-not-in-dlt.md) + [bronze-permissive.md](../wiki/concepts/bronze-permissive.md) |
| A scraper (idealista / jll / remax / zome / sce / etc.) | [wiki/concepts/zenrows-universal-vs-re-api.md](../wiki/concepts/zenrows-universal-vs-re-api.md) + [payload-cache-lifecycle.md](../wiki/concepts/payload-cache-lifecycle.md) |
| Adding or modifying an SCD2 sink | [wiki/concepts/scd2-row-hash.md](../wiki/concepts/scd2-row-hash.md) + [heartbeat-sidecar.md](../wiki/concepts/heartbeat-sidecar.md) |
| A `*_config.py` (any pipeline config) | [wiki/concepts/pydantic-not-in-dlt.md](../wiki/concepts/pydantic-not-in-dlt.md) — configs are Pydantic; dlt resources are not |
| GIS WFS/OGC plumbing (srup, crus, cadastro, etc.) | The relevant [wiki/sources/](../wiki/sources/) page + [wiki/concepts/medallion-layering.md](../wiki/concepts/medallion-layering.md) |
| Anything that runs in the Airflow container locally | [wiki/concepts/airflow-home-isolation.md](../wiki/concepts/airflow-home-isolation.md) — explains the `~/airflow/airflow.cfg` bleed gotcha |

> **Note**: PR 1 of Phase 3 ships this index BEFORE the wiki/concepts/ pages exist. Pointers will resolve once PR 2 lands. This is intentional per the eng-review A3 two-PR pattern.

## Source of truth

The wiki at [`../wiki/`](../wiki/) is the single source of truth for project rules. This file is just a routing index — it must NOT contain the rule content itself. If you find yourself adding a rule explanation here, move it to a `wiki/concepts/<name>.md` page and replace it with a pointer.
