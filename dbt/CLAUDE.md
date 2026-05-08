# dbt/ — Claude Code rules

## Schema for Claude Code (read this first)

Before editing dbt models, macros, or source YAMLs, **read the wiki/concepts/ page(s) mapped to your task below**. The wiki is the source of truth; this file routes you.

## Task → concepts routing

| If you're editing… | Read |
|---|---|
| A staging model (`models/staging/*`) | [wiki/concepts/medallion-layering.md](../wiki/concepts/medallion-layering.md) + [wiki/concepts/staging-yaml-conventions.md](../wiki/concepts/staging-yaml-conventions.md) |
| A silver or gold model | [wiki/concepts/medallion-layering.md](../wiki/concepts/medallion-layering.md) |
| A source YAML (`_*__sources.yml`) | [wiki/concepts/staging-yaml-conventions.md](../wiki/concepts/staging-yaml-conventions.md) |

> Pointers resolve once Phase 3 PR 2 lands.

## Source of truth

The wiki at [`../wiki/`](../wiki/) is the single source of truth.
