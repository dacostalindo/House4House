"""
DGEEC Estabelecimentos do Ensino Superior — Bronze Load DAG.

Sibling DAG to dgeec_ens_sup_ingestion. Walks the MinIO prefix
    s3://raw/dgeec_ens_sup/
finds the LATEST run_date partition, downloads the ZIP, extracts the
shapefile to a local temp dir, reads it with pyogrio, and upserts into

    bronze_education.raw_dgeec_ens_sup
      (run_date, codigo_unidade_organica, source_loaded_at,
       codigo_instituicao, instituicao_nome, unidade_organica_nome,
       natureza_tipo, website, email, morada, codigo_postal, distrito,
       concelho, telefone, outro_telefone, fax, latitude, longitude,
       geom geometry(Point, 4326), geom_pt geometry(Point, 3763))

The 16 DBF field names (truncated to 10 chars by the shapefile format) are
renamed to readable Portuguese snake_case, per the pillar convention
established in rede_escolar (see wiki/concepts/dbt-source-column-descriptions.md).
PostGIS holds dual-CRS geometries per ADR 2026-05-10.

PK: (run_date, codigo_unidade_organica). The shapefile's grain is UO
(faculdade/escola-level), 321 unique UO codes / 321 rows — verified via
live probe 2026-06-07. DGEEC's "Estabelecimento" terminology here refers to
the parent institution (e.g. "Universidade dos Açores"), NOT a physical
building — so `Código do Estabelecimento` is non-unique (101 values across
321 rows) and is renamed `codigo_instituicao` to avoid the confusion.

Both 4-digit codes (codigo_instituicao, codigo_unidade_organica) are stored
as TEXT zero-padded to width 4 to match the convention DGES uses when
publishing acesso ao ensino superior rankings — silver joins to DGES will
work without re-padding.

Idempotency: re-runs of the same logical date upsert into the same partition
(ON CONFLICT DO UPDATE on all data columns).
"""

from __future__ import annotations

import logging
from datetime import timedelta

log = logging.getLogger(__name__)

BRONZE_TABLE = "bronze_education.raw_dgeec_ens_sup"

# ---------------------------------------------------------------------------
# Column rename map — DBF (10-char truncated) → bronze column.
# Order matters: DDL + INSERT use this dict's iteration order.
# Schema verified 2026-06-07 via pyogrio.read_info on the live shapefile.
# ---------------------------------------------------------------------------

# Custom-handled columns (PK + numeric int→text zfill) are NOT in this map.
# Everything in here is plain text or plain double precision.
#
# source_field → (renamed_column, sql_type, kind)
#   kind: 'text', 'numeric'  (PK + zfill cols are handled separately)
SOURCE_KEY_TO_COLUMN: dict[str, tuple[str, str, str]] = {
    # --- Parent institution (non-unique, 101 distinct values) ---
    # DBF "Código do" = full label "Código do Estabelecimento".
    # Renamed to `codigo_instituicao` because DGEEC's "estabelecimento"
    # terminology here means the parent institution (Universidade, Politécnico),
    # NOT a physical building — avoids confusion with rede_escolar's
    # codigo_escola which IS a per-building 6-digit DGEEC code.
    "Código do": ("codigo_instituicao", "text", "zfill4"),
    "Estabeleci": ("instituicao_nome", "text", "text"),
    # --- Unidade Orgânica (PK; handled separately below) ---
    "Código da": ("codigo_unidade_organica", "text", "zfill4_pk"),
    "Unidade Or": ("unidade_organica_nome", "text", "text"),
    # --- Categorisation ---
    # Verbatim: "Ensino Superior {Público|Privado} - {Universitário|Politécnico|...}"
    # 6 distinct values. Silver may split into natureza + tipo if needed.
    "Natureza e": ("natureza_tipo", "text", "text"),
    # --- Web/contact ---
    "Website": ("website", "text", "text"),
    "Email": ("email", "text", "text"),
    # --- Endereço ---
    "Morada": ("morada", "text", "text"),
    "Código Po": ("codigo_postal", "text", "text"),  # "9501-801 PONTA DELGADA"
    "Distrito": ("distrito", "text", "text"),  # incl. ilhas ("Ilha de São Miguel")
    "Concelho": ("concelho", "text", "text"),
    "Telefone": ("telefone", "text", "text"),
    "Outro tele": ("outro_telefone", "text", "text"),
    "Fax": ("fax", "text", "text"),
    # --- Coordinates (kept alongside geom for sanity checks) ---
    "Latitude": ("latitude", "double precision", "numeric"),
    "Longitude": ("longitude", "double precision", "numeric"),
}

# Helpful slices
SOURCE_KEYS: tuple[str, ...] = tuple(SOURCE_KEY_TO_COLUMN.keys())
RENAMED_COLS: tuple[str, ...] = tuple(r for r, _, _ in SOURCE_KEY_TO_COLUMN.values())
PK_SOURCE_KEY = "Código da"  # → codigo_unidade_organica

# Build DDL programmatically.
_data_col_lines = [
    f"  {rename:<28} {sql_type},"
    for rename, sql_type, _ in SOURCE_KEY_TO_COLUMN.values()
]
_DATA_COLUMN_DDL = "\n".join(_data_col_lines)

DDL = f"""
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS bronze_education;
CREATE TABLE IF NOT EXISTS {BRONZE_TABLE} (
  run_date         date        NOT NULL,
  source_loaded_at timestamptz NOT NULL DEFAULT now(),
{_DATA_COLUMN_DDL}
  geom             geometry(Point, 4326),
  geom_pt          geometry(Point, 3763),
  PRIMARY KEY (run_date, codigo_unidade_organica)
);
CREATE INDEX IF NOT EXISTS raw_dgeec_ens_sup_geom_gist
  ON {BRONZE_TABLE} USING gist (geom);
CREATE INDEX IF NOT EXISTS raw_dgeec_ens_sup_geom_pt_gist
  ON {BRONZE_TABLE} USING gist (geom_pt);
CREATE INDEX IF NOT EXISTS raw_dgeec_ens_sup_codigo_instituicao
  ON {BRONZE_TABLE} (codigo_instituicao);
CREATE INDEX IF NOT EXISTS raw_dgeec_ens_sup_natureza
  ON {BRONZE_TABLE} (natureza_tipo);
"""

# Insert column list: run_date first, then renamed data cols (in source key
# order), then geom + geom_pt. source_loaded_at uses DEFAULT now() / ON CONFLICT.
_INSERT_COLS: tuple[str, ...] = ("run_date",) + RENAMED_COLS + ("geom", "geom_pt")

_values_slots: list[str] = []
for col in _INSERT_COLS:
    if col == "geom":
        _values_slots.append("ST_GeomFromText(%s, 4326)")
    elif col == "geom_pt":
        _values_slots.append("ST_Transform(ST_GeomFromText(%s, 4326), 3763)")
    else:
        _values_slots.append("%s")
VALUES_TEMPLATE = "(" + ", ".join(_values_slots) + ")"

_insert_col_list = ", ".join(_INSERT_COLS)
_update_set = ", ".join(
    f"{c} = EXCLUDED.{c}" for c in (*RENAMED_COLS, "geom", "geom_pt")
)
UPSERT_SQL = f"""
INSERT INTO {BRONZE_TABLE} ({_insert_col_list})
VALUES %s
ON CONFLICT (run_date, codigo_unidade_organica)
DO UPDATE SET {_update_set}, source_loaded_at = now()
"""


def _coerce_text(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    # pyogrio may hand back numpy scalars; coerce defensively.
    return str(v).strip() or None


def _coerce_numeric(v):
    import math

    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


def _point_wkb_to_wkt(wkb: bytes | None) -> str | None:
    """Decode a Point WKB to 'POINT(x y)'. Returns None on NULL/empty/non-Point.

    Point WKB layout (21 bytes): 1B byte-order + uint32 geom_type (1=Point)
    + float64 x + float64 y. Avoids a shapely dependency, which is not
    installed in the docker Airflow image.
    """
    import struct

    if wkb is None or len(wkb) < 21:
        return None
    byte_order = wkb[0]
    endian = "<" if byte_order == 1 else ">"
    geom_type = struct.unpack(f"{endian}I", wkb[1:5])[0]
    if geom_type != 1:  # only Point supported here
        return None
    x, y = struct.unpack(f"{endian}dd", wkb[5:21])
    import math

    if math.isnan(x) or math.isnan(y):
        return None
    return f"POINT({x} {y})"


def _coerce_zfill4(v) -> str | None:
    """Source codes ship as int64 (range 100..7730, widths 3 or 4).
    Pad to width 4 to match DGES publishing convention so silver joins work."""
    import math

    if v is None:
        return None
    try:
        i = int(v)
    except (TypeError, ValueError):
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return f"{i:04d}"


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.dgeec_ens_sup.dgeec_ens_sup_config import (
        LAYER_NAME,
        MINIO_BUCKET,
        MINIO_PREFIX,
        ZIP_FILENAME,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="dgeec_ens_sup_bronze_load",
        description=(
            "Load latest dgeec_ens_sup shapefile ZIP from MinIO into "
            "bronze_education.raw_dgeec_ens_sup with dual-CRS PostGIS geometry."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["dgeec_ens_sup", "dgeec", "education", "higher_ed", "bronze", "p1"],
    )
    def dgeec_ens_sup_bronze_load():
        @task()
        def discover_latest_run() -> dict:
            """Find the most recent run_date partition under MINIO_PREFIX."""
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            run_dates: set[str] = set()
            for obj in client.list_objects(
                MINIO_BUCKET, prefix=f"{MINIO_PREFIX}/", recursive=True
            ):
                parts = obj.object_name.split("/")
                if len(parts) != 3 or not parts[2].endswith(".zip"):
                    continue
                run_dates.add(parts[1])

            if not run_dates:
                raise RuntimeError(
                    f"No ZIP under s3://{MINIO_BUCKET}/{MINIO_PREFIX}/ — "
                    "run dgeec_ens_sup_ingestion first."
                )
            latest = max(run_dates)
            object_name = f"{MINIO_PREFIX}/{latest}/{ZIP_FILENAME}"
            log.info(
                "[dgeec_ens_sup-bronze] %d run_dates found, latest=%s, blob=%s",
                len(run_dates),
                latest,
                object_name,
            )
            return {"run_date": latest, "object_name": object_name}

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
                cur.execute(DDL)
            conn.close()
            log.info("[dgeec_ens_sup-bronze] DDL applied for %s", BRONZE_TABLE)
            return BRONZE_TABLE

        @task()
        def load(run_info: dict, table: str) -> dict:
            """Fetch ZIP from MinIO, extract, read shapefile, upsert with dual-CRS geom."""
            import io
            import tempfile
            import zipfile
            from pathlib import Path

            import psycopg2
            import pyogrio
            from airflow.models import Variable
            from minio import Minio
            from psycopg2.extras import execute_values

            mc = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            obj = mc.get_object(MINIO_BUCKET, run_info["object_name"])
            try:
                body = obj.read()
            finally:
                obj.close()
                obj.release_conn()

            with tempfile.TemporaryDirectory(prefix="dgeec_ens_sup_bronze_") as td:
                with zipfile.ZipFile(io.BytesIO(body)) as zf:
                    zf.extractall(td)
                shp_paths = list(Path(td).glob("*.shp"))
                if not shp_paths:
                    raise RuntimeError(
                        f"No .shp inside MinIO blob {run_info['object_name']}"
                    )
                if len(shp_paths) > 1:
                    log.warning(
                        "[dgeec_ens_sup-bronze] multiple .shp in ZIP: %s — using %s",
                        [p.name for p in shp_paths],
                        shp_paths[0].name,
                    )
                shp_path = shp_paths[0]

                # pyogrio.raw.read() returns (meta, fids, geometries, fields)
                # and does NOT depend on geopandas (read_dataframe does).
                # geometries is an ndarray of bytes (WKB); fields is a list of
                # ndarrays in meta["fields"] order. We zip back to a dict.
                meta, _fids, geometries, field_arrays = pyogrio.raw.read(str(shp_path))
                field_data = dict(zip(meta["fields"], field_arrays, strict=True))

            n_rows = len(geometries)
            log.info(
                "[dgeec_ens_sup-bronze] read %d rows from %s (layer=%s, fields=%d)",
                n_rows,
                shp_path.name,
                LAYER_NAME,
                len(field_data),
            )

            known = set(SOURCE_KEYS)
            unknown_keys = set(field_data.keys()) - known
            if unknown_keys:
                log.warning(
                    "[dgeec_ens_sup-bronze] %d unknown source columns (dropped): %s",
                    len(unknown_keys),
                    sorted(unknown_keys),
                )

            payload = []
            skipped_no_pk = 0
            skipped_no_geom = 0

            for i in range(n_rows):
                # PK
                pk_val = _coerce_zfill4(field_data.get(PK_SOURCE_KEY, [None] * n_rows)[i])
                if not pk_val:
                    skipped_no_pk += 1
                    continue

                # Geometry → WKT via raw WKB decode (Point: 21 bytes).
                # Header: 1 byte byte-order + uint32 geom_type (1=Point) + 2× float64.
                wkb = geometries[i]
                wkt = _point_wkb_to_wkt(wkb)
                if wkt is None:
                    skipped_no_geom += 1

                out_row: list = [run_info["run_date"]]
                for src_key, (_renamed, _sqltype, kind) in SOURCE_KEY_TO_COLUMN.items():
                    raw = field_data.get(src_key, [None] * n_rows)[i]
                    if kind in ("zfill4", "zfill4_pk"):
                        out_row.append(_coerce_zfill4(raw))
                    elif kind == "numeric":
                        out_row.append(_coerce_numeric(raw))
                    else:
                        out_row.append(_coerce_text(raw))
                # geom (WKT) twice — once for geom (4326), once for geom_pt
                # (3763 via ST_Transform in VALUES template). Both NULL-safe.
                out_row.append(wkt)
                out_row.append(wkt)
                payload.append(tuple(out_row))

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            try:
                with conn.cursor() as cur:
                    execute_values(cur, UPSERT_SQL, payload, template=VALUES_TEMPLATE)
                conn.commit()
            finally:
                conn.close()

            log.info(
                "[dgeec_ens_sup-bronze] %s: %d upserted (skipped %d no-pk, %d no-geom)",
                run_info["object_name"],
                len(payload),
                skipped_no_pk,
                skipped_no_geom,
            )
            return {
                "object_name": run_info["object_name"],
                "run_date": run_info["run_date"],
                "rows_upserted": len(payload),
                "skipped_no_pk": skipped_no_pk,
                "skipped_no_geom": skipped_no_geom,
                "unknown_keys": sorted(unknown_keys),
            }

        @task()
        def summarize(result: dict) -> dict:
            if result["unknown_keys"]:
                log.warning(
                    "[dgeec_ens_sup-bronze] schema drift — add to SOURCE_KEY_TO_COLUMN: %s",
                    result["unknown_keys"],
                )
            log.info(
                "[dgeec_ens_sup-bronze] done: run_date=%s, %d rows, "
                "%d no-pk skipped, %d no-geom",
                result["run_date"],
                result["rows_upserted"],
                result["skipped_no_pk"],
                result["skipped_no_geom"],
            )
            return result

        run_info = discover_latest_run()
        table = ensure_table()
        loaded = load(run_info, table)
        summarize(loaded)

    return dgeec_ens_sup_bronze_load()


dag = _create_dag()
