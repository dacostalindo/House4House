---
title: SCD2 row-hash policy
type: concept
last_verified: 2026-05-08
tags: [fixture, scd2]
---

# SCD2 row-hash policy

## What it is

In House4House's bronze layer, all SCD2 tables **deduplicate by `row_hash`** — a SHA256 over a curated subset of columns excluding timestamps and load-id metadata.

## Why

Source-side primary keys are unreliable across portals (some sources reuse IDs, others change them on republish). Row-hash dedup is content-based and survives upstream ID drift.

## How

Each SCD2 sink computes `row_hash = sha256(col1 || col2 || ...)` over the curated subset. New row written when `row_hash` changes; otherwise no-op.
