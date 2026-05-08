---
title: Idealista pipeline (fixture)
type: pipeline
last_verified: 2026-05-08
tags: [fixture, idealista, pipeline]
---

# Idealista pipeline (fixture)

## What it does

Fetches Idealista listings and writes them to bronze with SCD2 versioning.

## SCD2 dedup

This pipeline writes SCD2 rows keyed by **primary_key** (the listing_id). See [scd2-primary-key.md](../concepts/scd2-primary-key.md).

> **Intentional contradiction** with `sources/idealista.md` (which says row_hash dedup) and `concepts/scd2-row-hash.md`. `/wiki-lint` integration test asserts that both `scd2-row-hash.md` and `scd2-primary-key.md` (or `idealista-pipeline.md`) are named in the lint output.
