# Wiki Index (with-contradiction fixture)

Last lint run: never

## Sources

- [idealista](sources/idealista.md) — Idealista listings via SCD2 row-hash dedup.

## Concepts

- [scd2-row-hash](concepts/scd2-row-hash.md) — SCD2 deduplicates by row_hash.
- [scd2-primary-key](concepts/scd2-primary-key.md) — SCD2 deduplicates by primary key. (Intentional contradiction with scd2-row-hash for lint testing.)

## Pipelines

- [idealista-pipeline](pipelines/idealista-pipeline.md) — claims SCD2 dedup is by primary key (contradicts scd2-row-hash).
