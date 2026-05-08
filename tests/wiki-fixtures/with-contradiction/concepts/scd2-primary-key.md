---
title: SCD2 primary-key policy
type: concept
last_verified: 2026-05-08
tags: [fixture, scd2]
---

# SCD2 primary-key policy

## What it is

In House4House's bronze layer, all SCD2 tables **deduplicate by primary key** (the source-side ID). When the same primary key appears with different content, a new SCD2 version is written.

## Why

Primary-key-based dedup is the textbook SCD2 pattern and matches what dlt does by default.

## How

Each SCD2 sink uses `primary_key=<id_field>` and dlt detects content changes on subsequent loads.

> **Intentional contradiction** with `scd2-row-hash.md` for `/wiki-lint` integration testing. Real wiki should never have both pages.
