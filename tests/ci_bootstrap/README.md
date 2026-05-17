# tests/ci_bootstrap/

SQL files in this directory create the **empty bronze tables** that
`.github/workflows/ci.yml` needs before running `dbt build`. They are NOT
pgTAP tests — pg_prove only globs `tests/sql/*.sql`. These files are run by
`psql -f` in CI, in alphabetical order.

## Convention

One file per data-source family: `bronze_<source>.sql` (e.g. `bronze_sce.sql`,
`bronze_cadastro.sql`). Each file:

- Creates the bronze schema (`CREATE SCHEMA IF NOT EXISTS bronze_<area>`).
- Creates the source tables that `dbt sources` references, **matching the
  live warehouse schema column-for-column** (so dbt build catches type
  mismatches against the real upstream).
- Stays empty (no INSERTs). Tier 1 catches structural bugs only; Tier 2
  (sprint-10) adds seed-based fixture data.

## Adding a new bronze source

When a sprint-09 PR introduces a silver/gold model that depends on a new
bronze table, **add an empty CREATE TABLE statement here** in the same PR.
This keeps CI's `dbt build --select <new_model>` step honest as the project
grows.

The pattern is additive: each PR contributes the bronze stubs it needs.
By end of sprint-09 the full v1 wedge path is structurally-validated in CI.
