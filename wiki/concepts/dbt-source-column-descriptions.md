---
title: dbt source column descriptions — every column documented
type: concept
last_verified: 2026-06-06
tags: [dbt, conventions, documentation, dbt-docs, bronze]
---

## For future Claude

This concept page documents the convention: **every column in every
`dbt/models/staging/<domain>/_staging_<domain>__sources.yml` source table MUST
carry a `description:` string**. Read this before adding a new bronze source
or modifying an existing one. The rule is enforced manually today; a future
mechanical lint may add a BLOCKING check.

## What it is

For every `sources.tables[].columns[]` entry in a dbt source YAML, write a
single-line Portuguese-or-English `description:` that explains what the column
represents to a future reader who has only the column name.

Concretely: if the bronze table `bronze_<domain>.raw_<source>` has 95
columns, then `_staging_<domain>__sources.yml` lists 95 column entries — and
each entry has a `description:` populated.

## Why

Three load-bearing reasons:

1. **dbt-docs is the warehouse's discovery surface.** The local dbt-docs
   container (`house4house-dbt-docs-1`) serves the catalog with hover-text on
   every column. Without descriptions, every column appears as a bare name in
   the lineage graph — readers can't tell `mma` from `nimm` from `rsma` until
   they grep the legend page or read the source script. The descriptions
   appear as tooltips and as long-form text on the column-detail page.

2. **Cryptic source names become a tax on every downstream silver model.**
   The Público rankings source ships 91 unique 1–6-character abbreviations
   (mt, rt, rs, mm, nipfl, rsmc, …) — without YAML descriptions, every
   silver model author must re-derive the meaning by reading the source
   script. Worse, two abbreviations can mean opposite things across
   sub-families (Público's 1-letter `ma` = Economia A, 2-letter `ma` = Mat A;
   see [[publico-rankings-column-legend]]). A description on the renamed
   bronze column explicitly disambiguates.

3. **Drift detection.** When the source publisher adds a new field or
   renames an existing one, the next bronze refresh logs a
   "schema-drift" warning. The reviewer's first question is "what was the old
   field supposed to mean?" — answerable from the YAML, without digging
   through git history.

## How

### The rule

Every column entry under
`sources.tables[].columns[]` MUST have a `description:` that:

- Explains the metric / identifier in one line (≤ 200 chars when possible).
- Names the unit / scale where applicable (e.g. `0–20 sec, 0–5 9ano`, `%`,
  `WGS84 latitude`, `null = absent or sample below threshold`).
- For renamed/translated columns: **cite the original source key** as
  `Source key: \`<original>\`` at the end.
- For ambiguous codings (codebook collisions, region letters, natureza
  codes), expand the dictionary inline or cite a `[[wikilink]]` to the
  concept page that has it.
- For permissive-JSONB columns: list the keys you'd promote in staging.

### Pattern by column category

**Partition keys / audit:** carry `tests: [not_null]`. Description names the
provenance of the value (path vs body).

```yaml
- name: year
  description: "Edition year (e.g. 2024). Promoted from the MinIO file path, not the JSON body."
  tests: [not_null]
```

**Renamed-from-cryptic source key:** description ends with
`Source key: \`<original>\``. If the rename resolves an abbreviation
collision, call it out.

```yaml
- name: media_economia_a
  description: "Média dos exames de Economia A (sec only). Source key: `mma` — 1-letter codebook where `ma`=Economia (NOT Mat A)."
```

**Code-letter encoding:** expand the dictionary inline.

```yaml
- name: contexto_agrupamento
  description: >
    Letter code for the agrupamento's socioeconomic context: D=Desfavorável,
    F=Favorável, I=Intermédio, PRI=privado sem contrato, PRI_CA=privado com
    contrato de associação, Açores, Madeira. Source key: `c`.
```

**Foreign-key column:** name the join target table + column + populated-rate.

```yaml
- name: codigo_uo_dgeec
  description: >
    DGEEC 6-digit agrupamento código (Unidade Orgânica). Populated for ~79%
    of 9ano rows; NULL for all sec rows. Primary join key to
    [[rede-escolar]].CODUOME. Source key: `coduo`.
```

**Permissive-JSONB blob:** enumerate the silver-promoted keys.

```yaml
- name: raw
  description: >
    JSONB blob — original source row, key-for-key. Staging promotes `e` (name),
    `id`, `coduo` (DGEEC agrupamento), `co`, `c`, `t`, `mt`, `rt`, `lt`/`ln`,
    per-disciplina averages. Full inventory in [[publico-rankings]] §Schema.
```

### Verification (pre-merge)

```bash
# 1. Column count matches the actual bronze table:
docker exec house4house-warehouse-1 psql -U warehouse -d house4house -c \
  "SELECT count(*) FROM information_schema.columns
   WHERE table_schema='bronze_<domain>' AND table_name='raw_<source>';"

# 2. YAML has the same column set:
uv run python -c "
import yaml
y = yaml.safe_load(open('dbt/models/staging/<domain>/_staging_<domain>__sources.yml'))
cols = y['sources'][0]['tables'][0]['columns']
no_desc = [c['name'] for c in cols if not c.get('description')]
print(f'columns: {len(cols)}, missing description: {no_desc or \"none\"}')
"

# 3. dbt manifest picks up the descriptions:
uv run --with dbt-postgres dbt parse --project-dir dbt --profiles-dir dbt
python3 -c "
import json
m = json.load(open('dbt/target/manifest.json'))
src = m['sources']['source.house4house.bronze_<domain>.raw_<source>']
print(f'manifest columns: {len(src[\"columns\"])}')
"
```

All three counts must agree: `information_schema` ≡ YAML ≡ manifest.

### What does NOT count as a description

- The column name re-spelled in title case.
- A stub like "TODO" or "TBD".
- A redirect to "see source script" without naming the script.

If the meaning isn't known yet, write the description as
`"⚠️ Semantics unverified; ground-truth via [provenance source]. See [[<legend page>]]."` —
treat it as a follow-up rather than silent missing-doc.

## When this rule does NOT apply

- **Bronze tables that mirror a flat single-purpose source 1:1** with already
  self-explanatory column names (e.g. `n_edificios_classicos`,
  `n_individuos_25_64` in [[bgri]]) can use a single-line per-column
  description that just expands the abbreviation. The rule is "describe
  every column", not "write 5 sentences per column".
- **One-off exploratory tables** under `bronze_<domain>.scratch_*` do not
  require descriptions; they aren't part of the maintained surface.
- **Generated columns** (e.g. `_load_timestamp`, `_dlt_id`, `_dlt_load_id`)
  whose meaning is platform-canonical (Airflow / dlt) — a single short
  description is enough; one per loader, not one per source.

## See also

- [[publico-rankings-column-legend]] — the legend page that ground-truthed
  the 95-column rename + description set for `bronze_education.raw_publico_rankings`
- [[publico-rankings]] — source page that points back to this rule
- [[bronze-permissive]] — the invariant; descriptions become MORE important
  when bronze relaxes typing
- [[medallion-layering]] — where bronze sits in the bronze/silver/gold flow
