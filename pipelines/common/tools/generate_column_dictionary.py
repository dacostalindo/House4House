"""
Column-dictionary generator for bronze tables.

Cross-pipeline reusable utility. Introspects any Postgres table in the
warehouse and produces:
  - yaml      — dbt source column blocks (paste-ready under a source's columns:)
  - markdown  — README-friendly column tables
  - fixtures  — N-row JSONL samples for tests/fixtures/

Auto-discovered per column:
  - data type, nullability (information_schema)
  - null percentage and distinct count (active SCD2 versions only by default)
  - top-3 sample values for low-cardinality columns

Human-curated fields (left as TODO placeholders for follow-up edits):
  - business meaning (description)
  - source path (mapping back to upstream API field)
  - notes (gotchas, encoded IDs, sentinels, cross-portal naming differences)

Usage:
  python -m pipelines.common.tools.generate_column_dictionary \\
    --schema bronze_listings --table remax_developments --format yaml

  python -m pipelines.common.tools.generate_column_dictionary \\
    --schema bronze_listings --table remax_developments --format markdown

  python -m pipelines.common.tools.generate_column_dictionary \\
    --schema bronze_listings --table remax_developments \\
    --format fixtures --rows 5 \\
    --output tests/fixtures/portals/remax/developments.jsonl

Environment (defaults match the warehouse Docker service):
  WAREHOUSE_HOST       (default: warehouse, or localhost outside containers)
  WAREHOUSE_PORT       (default: 5432, or 5433 outside containers)
  WAREHOUSE_DB         (default: house4house)
  WAREHOUSE_USER       (default: warehouse)
  WAREHOUSE_PASSWORD   (required)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def _connect():
    """Connect to the warehouse using env vars. Compatible with Airflow."""
    return psycopg2.connect(
        host=os.environ.get("WAREHOUSE_HOST", "warehouse"),
        port=int(os.environ.get("WAREHOUSE_PORT", "5432")),
        dbname=os.environ.get("WAREHOUSE_DB", "house4house"),
        user=os.environ.get("WAREHOUSE_USER", "warehouse"),
        password=os.environ.get("WAREHOUSE_PASSWORD"),
    )


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    null_pct: float | None = None
    distinct_count: int | None = None
    top_values: list[tuple[Any, int]] = field(default_factory=list)


# Types where computing top-N grouping is meaningless or expensive.
_GROUPABLE_SKIP_TYPES = {"jsonb", "json", "ARRAY", "USER-DEFINED", "bytea"}


def _get_columns(conn, schema: str, table: str) -> list[ColumnInfo]:
    """Pull base column metadata from information_schema."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        rows = cur.fetchall()
    if not rows:
        raise ValueError(f"Table {schema}.{table} not found or has no columns")
    return [ColumnInfo(name=r[0], data_type=r[1], is_nullable=(r[2] == "YES")) for r in rows]


def _has_scd2_columns(columns: list[ColumnInfo]) -> bool:
    names = {c.name for c in columns}
    return "_dlt_valid_to" in names and "_dlt_valid_from" in names


def _enrich_with_stats(
    conn,
    schema: str,
    table: str,
    columns: list[ColumnInfo],
    active_only: bool,
    sample_cap: int,
    distinct_threshold: int,
) -> None:
    """Compute null %, distinct count, and top-3 sample values per column."""
    where = "WHERE _dlt_valid_to IS NULL" if active_only else ""
    quoted_tbl = f'"{schema}"."{table}"'

    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {quoted_tbl} {where}")
        total = cur.fetchone()[0]
        if total == 0:
            return

        for col in columns:
            quoted_col = f'"{col.name}"'

            # Null percentage
            cur.execute(f"SELECT COUNT(*) - COUNT({quoted_col}) FROM {quoted_tbl} {where}")
            nulls = cur.fetchone()[0]
            col.null_pct = round(100.0 * nulls / total, 1)

            # Distinct count (capped via LIMIT subquery so wide tables stay cheap)
            cur.execute(
                f"SELECT COUNT(DISTINCT {quoted_col}) FROM "
                f"(SELECT {quoted_col} FROM {quoted_tbl} {where} LIMIT %s) sub",
                (sample_cap,),
            )
            col.distinct_count = cur.fetchone()[0]

            # Top-3 sample values: only meaningful for low-cardinality columns
            if (
                col.distinct_count is not None
                and 0 < col.distinct_count <= distinct_threshold
                and col.data_type not in _GROUPABLE_SKIP_TYPES
            ):
                try:
                    cur.execute(
                        f"SELECT {quoted_col}::text, COUNT(*) "
                        f"FROM {quoted_tbl} {where} "
                        f"WHERE {quoted_col} IS NOT NULL "
                        f"GROUP BY {quoted_col} ORDER BY COUNT(*) DESC LIMIT 3"
                    )
                    col.top_values = [(r[0], r[1]) for r in cur.fetchall()]
                except psycopg2.Error:
                    conn.rollback()
                    col.top_values = []


# ---------------------------------------------------------------------------
# Fixtures (JSONL)
# ---------------------------------------------------------------------------


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Not JSON-serializable: {type(obj).__name__}")


def _generate_fixtures(conn, schema: str, table: str, n_rows: int, active_only: bool) -> str:
    where = "WHERE _dlt_valid_to IS NULL" if active_only else ""
    quoted_tbl = f'"{schema}"."{table}"'
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # ORDER BY 1 = first column (typically the PK / serial id) — gives
        # deterministic output across regenerations.
        cur.execute(f"SELECT * FROM {quoted_tbl} {where} ORDER BY 1 LIMIT %s", (n_rows,))
        rows = cur.fetchall()
    return "\n".join(json.dumps(dict(r), default=_json_default, ensure_ascii=False) for r in rows)


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------


def _format_meta_comment(col: ColumnInfo) -> str:
    """Concise machine-readable comment summarizing introspection results."""
    parts = [f"type={col.data_type}"]
    if not col.is_nullable:
        parts.append("not_null")
    if col.null_pct is not None:
        parts.append(f"null={col.null_pct}%")
    if col.distinct_count is not None:
        parts.append(f"distinct={col.distinct_count}")
    if col.top_values:
        samples = ", ".join(repr(v) for v, _ in col.top_values)
        parts.append(f"samples=[{samples}]")
    return " | ".join(parts)


def _format_yaml(columns: list[ColumnInfo]) -> str:
    """Output dbt source column blocks. Paste under a source's `columns:` key."""
    out: list[str] = ["columns:"]
    for col in columns:
        out.append(f"  - name: {col.name}")
        out.append('    description: ""  # TODO: business meaning + source path')
        out.append(f"    # {_format_meta_comment(col)}")
    return "\n".join(out)


def _format_markdown(table: str, columns: list[ColumnInfo]) -> str:
    """Output a markdown table for README appending."""
    header = (
        "| Column | Type | Nullable | Null % | Distinct | Sample values "
        "| Description | Source path | Notes |"
    )
    sep = (
        "|--------|------|----------|--------|----------|---------------"
        "|-------------|-------------|-------|"
    )
    lines = [f"### `{table}`", "", header, sep]
    for col in columns:
        nullable = "yes" if col.is_nullable else "no"
        null_pct = f"{col.null_pct}%" if col.null_pct is not None else "—"
        distinct = str(col.distinct_count) if col.distinct_count is not None else "—"
        if col.top_values:
            samples = "<br>".join(f"`{v}` ({n})" for v, n in col.top_values)
        else:
            samples = "—"
        lines.append(
            f"| `{col.name}` | `{col.data_type}` | {nullable} | {null_pct} "
            f"| {distinct} | {samples} | TODO | TODO | TODO |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate column dictionaries for any bronze table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--schema", required=True, help="e.g. bronze_listings")
    parser.add_argument("--table", required=True, help="e.g. remax_developments")
    parser.add_argument("--format", choices=("yaml", "markdown", "fixtures"), default="yaml")
    parser.add_argument(
        "--rows",
        type=int,
        default=5,
        help="Number of fixture rows (only used with --format fixtures)",
    )
    parser.add_argument("--output", help="Write to file instead of stdout")
    parser.add_argument(
        "--no-active-only",
        action="store_true",
        help="Disable WHERE _dlt_valid_to IS NULL filter on SCD2 tables",
    )
    parser.add_argument(
        "--sample-cap",
        type=int,
        default=10000,
        help="Row cap for distinct-count / sampling queries (default 10000)",
    )
    parser.add_argument(
        "--distinct-threshold",
        type=int,
        default=20,
        help=(
            "Top-3 sample values are only included when distinct_count "
            "is <= this threshold (default 20)"
        ),
    )
    args = parser.parse_args()

    conn = _connect()
    try:
        columns = _get_columns(conn, args.schema, args.table)
        active_only = _has_scd2_columns(columns) and not args.no_active_only

        if args.format == "fixtures":
            output = _generate_fixtures(conn, args.schema, args.table, args.rows, active_only)
        else:
            _enrich_with_stats(
                conn,
                args.schema,
                args.table,
                columns,
                active_only,
                args.sample_cap,
                args.distinct_threshold,
            )
            if args.format == "yaml":
                output = _format_yaml(columns)
            else:
                output = _format_markdown(args.table, columns)
    finally:
        conn.close()

    if args.output:
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
            if not output.endswith("\n"):
                f.write("\n")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
