"""
DGES CNA acesso — Bronze Load DAG.

Walks ALL MinIO blobs under
    s3://raw/dges_acesso/{year}/fase_{n}/...
parses each with the right engine (openpyxl/xlrd/odf), normalizes column
labels via SOURCE_LABEL_TO_COLUMN, and upserts into

    bronze_education.raw_dges_acesso
      (year, phase, codigo_instit, codigo_curso,
       source_loaded_at,
       nome_instituicao, nome_curso, grau,
       vagas_iniciais, vagas_recolocacao,
       colocados, colocados_desemp, colocados_sem_class,
       vaga_adic_sem_class, vaga_adic_autonomas, vaga_adic_alineas_c_e,
       nota_ult_colocado, vagas_sobrantes,
       sobras_2f, nao_matric_2f, nao_matric_2f_sem_class, sobras_retiradas)

Idempotent: re-runs upsert (no-op when no upstream change). Processes EVERY
blob each run (not just latest) — designed to handle annual `ingestion` DAG
adding one new (year, phase) blob then a `bronze_load` rerun.

PK: (year, phase, codigo_instit, codigo_curso). year+phase from the MinIO
path; codigo_instit + codigo_curso from each data row.

Label drift across years/phases is the main risk; SOURCE_LABEL_TO_COLUMN
collapses known synonyms. Unknown source labels are logged with file path
in the summarize task (drift sentinel).

Row filtering: a "valid data row" has codigo_instit matching ^[0-9A-Za-z]{2,5}$
(filters out blank rows, the 2018 .ods '(1)(2)...' annotation row, and
trailing summary rows like 'Total geral').
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

log = logging.getLogger(__name__)

BRONZE_TABLE = "bronze_education.raw_dges_acesso"

# Validates codigo_instit shape. DGES codes observed: 0140, 3055, 7001, L184 (rare).
# 2-5 chars alphanumeric covers everything seen.
_CODE_RE = re.compile(r"^[0-9A-Za-z]{2,5}$")

# Path parser: raw/dges_acesso/{year}/fase_{n}/{filename}
_MINIO_PATH_RE = re.compile(r"^dges_acesso/(\d{4})/fase_(\d+)/[^/]+\.(xlsx|xls|ods)$")


def _engine_for_suffix(suffix: str) -> str:
    return {"xlsx": "openpyxl", "xls": "xlrd", "ods": "odf"}[suffix.lower()]


def _normalize_label(s: object) -> str | None:
    """Strip + collapse internal whitespace (so '\\n' in source labels normalizes)."""
    if s is None:
        return None
    text = str(s).strip()
    if not text or text.lower() == "nan":
        return None
    return re.sub(r"\s+", " ", text)


def _build_ddl() -> str:
    from pipelines.gis.dges_acesso.dges_acesso_config import BRONZE_DATA_COLUMNS

    # codigo_instit + codigo_curso are PK; everything else is nullable data.
    data_cols = [c for c in BRONZE_DATA_COLUMNS if c[0] not in ("codigo_instit", "codigo_curso")]
    col_lines = [f"  {name:<28} {sqltype}," for name, sqltype in data_cols]
    body = "\n".join(col_lines)
    return f"""
CREATE SCHEMA IF NOT EXISTS bronze_education;
CREATE TABLE IF NOT EXISTS {BRONZE_TABLE} (
  year             integer     NOT NULL,
  phase            integer     NOT NULL,
  codigo_instit    text        NOT NULL,
  codigo_curso     text        NOT NULL,
  source_loaded_at timestamptz NOT NULL DEFAULT now(),
{body}
  PRIMARY KEY (year, phase, codigo_instit, codigo_curso)
);
CREATE INDEX IF NOT EXISTS raw_dges_acesso_codigo_instit
  ON {BRONZE_TABLE} (codigo_instit);
CREATE INDEX IF NOT EXISTS raw_dges_acesso_year_phase
  ON {BRONZE_TABLE} (year, phase);
"""


def _build_upsert() -> tuple[str, tuple[str, ...]]:
    from pipelines.gis.dges_acesso.dges_acesso_config import BRONZE_DATA_COLUMNS

    pk = ("year", "phase", "codigo_instit", "codigo_curso")
    data_cols = tuple(
        c[0] for c in BRONZE_DATA_COLUMNS if c[0] not in ("codigo_instit", "codigo_curso")
    )
    all_cols = pk + data_cols
    col_list = ", ".join(all_cols)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in data_cols)
    sql = f"""
INSERT INTO {BRONZE_TABLE} ({col_list})
VALUES %s
ON CONFLICT (year, phase, codigo_instit, codigo_curso)
DO UPDATE SET {update_set}, source_loaded_at = now()
"""
    return sql, all_cols


def _coerce(value: object, sqltype: str):
    import math

    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() == "nan":
            return None
        if sqltype == "text":
            return s
        try:
            f = float(s.replace(",", "."))
        except ValueError:
            return None
        if math.isnan(f):
            return None
        return int(f) if sqltype == "integer" else f
    # numeric scalar (numpy/python)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    if sqltype == "text":
        return str(value).strip()
    return int(f) if sqltype == "integer" else f


def _parse_blob(body: bytes, engine: str) -> tuple[list[str], list[list], set[str]]:
    """Return (header_labels, data_rows, unknown_labels) for one file.

    Skips title rows by scanning for the first row whose column-B value is
    'Código Instit.' (the header anchor). Filters data rows by codigo_instit
    shape so the 2018 .ods '(1)(2)...' annotation row and trailing blanks
    drop out generically.
    """
    import io

    import pandas as pd

    from pipelines.gis.dges_acesso.dges_acesso_config import LEADING_BLANK_COLS

    df = pd.read_excel(io.BytesIO(body), engine=engine, sheet_name=0, header=None)

    # Find header row by anchor in column B (index 1).
    header_row_idx = None
    for i in range(min(20, len(df))):
        cell = df.iat[i, 1] if df.shape[1] > 1 else None
        if cell is None:
            continue
        if _normalize_label(cell) == "Código Instit.":
            header_row_idx = i
            break
    if header_row_idx is None:
        raise RuntimeError("Could not locate header row (no 'Código Instit.' anchor in col B).")

    # Header labels: normalize each cell. Stop at first NaN-stretch of 3+
    # (some files have trailing empty cols).
    headers: list[str | None] = []
    for j in range(LEADING_BLANK_COLS, df.shape[1]):
        headers.append(_normalize_label(df.iat[header_row_idx, j]))
    # Trim trailing Nones.
    while headers and headers[-1] is None:
        headers.pop()

    from pipelines.gis.dges_acesso.dges_acesso_config import SOURCE_LABEL_TO_COLUMN

    known_labels = set(SOURCE_LABEL_TO_COLUMN.keys())
    unknown = {h for h in headers if h is not None and h not in known_labels}

    # Data rows: from header_row_idx + 1 to end, filtered by codigo_instit shape.
    out_rows = []
    code_col_idx = LEADING_BLANK_COLS  # column B = first non-blank col = codigo_instit
    for i in range(header_row_idx + 1, len(df)):
        code_cell = df.iat[i, code_col_idx]
        if code_cell is None:
            continue
        code_str = str(code_cell).strip()
        if not code_str or code_str.lower() == "nan":
            continue
        if not _CODE_RE.fullmatch(code_str):
            continue
        row = [
            df.iat[i, LEADING_BLANK_COLS + k] if (LEADING_BLANK_COLS + k) < df.shape[1] else None
            for k in range(len(headers))
        ]
        out_rows.append(row)

    return [h or "" for h in headers], out_rows, unknown


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.dges_acesso.dges_acesso_config import (
        BRONZE_DATA_COLUMNS,
        MINIO_BUCKET,
        MINIO_PREFIX,
        SOURCE_LABEL_TO_COLUMN,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="dges_acesso_bronze_load",
        description=(
            "Load ALL dges_acesso (year, phase) blobs from MinIO into "
            "bronze_education.raw_dges_acesso. Idempotent upsert on "
            "(year, phase, codigo_instit, codigo_curso)."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["dges_acesso", "dges", "education", "higher_ed", "bronze", "p1"],
    )
    def dges_acesso_bronze_load():
        @task()
        def discover_blobs() -> list[dict]:
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            blobs = []
            for obj in client.list_objects(MINIO_BUCKET, prefix=f"{MINIO_PREFIX}/", recursive=True):
                m = _MINIO_PATH_RE.match(obj.object_name)
                if not m:
                    log.warning(
                        "[dges_acesso-bronze] skipping unrecognised blob: %s", obj.object_name
                    )
                    continue
                blobs.append(
                    {
                        "object_name": obj.object_name,
                        "year": int(m.group(1)),
                        "phase": int(m.group(2)),
                        "suffix": m.group(3),
                    }
                )
            blobs.sort(key=lambda b: (b["year"], b["phase"]))
            log.info("[dges_acesso-bronze] %d blobs to process", len(blobs))
            if not blobs:
                raise RuntimeError(
                    f"No blobs under s3://{MINIO_BUCKET}/{MINIO_PREFIX}/ — "
                    "run dges_acesso_backfill or dges_acesso_ingestion first."
                )
            return blobs

        @task()
        def ensure_table() -> str:
            import psycopg2
            from airflow.models import Variable

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(_build_ddl())
            conn.close()
            log.info("[dges_acesso-bronze] DDL applied for %s", BRONZE_TABLE)
            return BRONZE_TABLE

        @task()
        def load_all(blobs: list[dict], table: str) -> dict:
            import psycopg2
            from airflow.models import Variable
            from minio import Minio
            from psycopg2.extras import execute_values

            mc = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            upsert_sql, all_cols = _build_upsert()

            per_file_stats: list[dict] = []
            unknown_by_file: dict[str, list[str]] = {}
            total_upserted = 0

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            try:
                for b in blobs:
                    obj_name = b["object_name"]
                    year, phase = b["year"], b["phase"]
                    engine = _engine_for_suffix(b["suffix"])

                    obj = mc.get_object(MINIO_BUCKET, obj_name)
                    try:
                        body = obj.read()
                    finally:
                        obj.close()
                        obj.release_conn()

                    headers, data_rows, unknown = _parse_blob(body, engine)
                    if unknown:
                        unknown_by_file[obj_name] = sorted(unknown)
                        log.warning(
                            "[dges_acesso-bronze] %s: %d unknown labels: %s",
                            obj_name,
                            len(unknown),
                            sorted(unknown),
                        )

                    # Build header → bronze column map for this file.
                    header_to_bronze: list[tuple[int, str, str] | None] = []
                    for idx, label in enumerate(headers):
                        mapping = SOURCE_LABEL_TO_COLUMN.get(label)
                        if mapping is None:
                            header_to_bronze.append(None)
                            continue
                        bronze_col, sqltype = mapping
                        header_to_bronze.append((idx, bronze_col, sqltype))

                    # Each data row → tuple in all_cols order.
                    rows_for_insert: list[tuple] = []
                    for row in data_rows:
                        per_col: dict[str, object] = {c: None for c, _ in BRONZE_DATA_COLUMNS}
                        for entry in header_to_bronze:
                            if entry is None:
                                continue
                            idx, bronze_col, sqltype = entry
                            per_col[bronze_col] = _coerce(row[idx], sqltype)

                        # Skip if either PK component missing.
                        if not per_col.get("codigo_instit") or not per_col.get("codigo_curso"):
                            continue

                        tup = (
                            year,
                            phase,
                            per_col["codigo_instit"],
                            per_col["codigo_curso"],
                            *(
                                per_col[col]
                                for col in all_cols
                                if col not in ("year", "phase", "codigo_instit", "codigo_curso")
                            ),
                        )
                        rows_for_insert.append(tup)

                    with conn.cursor() as cur:
                        execute_values(cur, upsert_sql, rows_for_insert)
                    conn.commit()

                    log.info(
                        "[dges_acesso-bronze] %s: %d rows upserted",
                        obj_name,
                        len(rows_for_insert),
                    )
                    per_file_stats.append(
                        {
                            "object_name": obj_name,
                            "year": year,
                            "phase": phase,
                            "rows_upserted": len(rows_for_insert),
                        }
                    )
                    total_upserted += len(rows_for_insert)
            finally:
                conn.close()

            return {
                "n_files": len(per_file_stats),
                "total_upserted": total_upserted,
                "per_file": per_file_stats,
                "unknown_by_file": unknown_by_file,
            }

        @task()
        def summarize(result: dict) -> dict:
            log.info(
                "[dges_acesso-bronze] done: %d files, %d total rows upserted",
                result["n_files"],
                result["total_upserted"],
            )
            for s in result["per_file"]:
                log.info(
                    "  %d/fase_%d: %d rows  (%s)",
                    s["year"],
                    s["phase"],
                    s["rows_upserted"],
                    s["object_name"],
                )
            if result["unknown_by_file"]:
                log.warning(
                    "[dges_acesso-bronze] SCHEMA DRIFT — %d files have unknown labels:",
                    len(result["unknown_by_file"]),
                )
                for path, labels in result["unknown_by_file"].items():
                    log.warning("  %s → %s", path, labels)
                log.warning(
                    "[dges_acesso-bronze] add unknown labels to "
                    "SOURCE_LABEL_TO_COLUMN in dges_acesso_config.py"
                )
            return result

        blobs = discover_blobs()
        table = ensure_table()
        loaded = load_all(blobs, table)
        summarize(loaded)

    return dges_acesso_bronze_load()


dag = _create_dag()
