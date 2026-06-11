"""
Rede Escolar Bronze Load — MinIO → Postgres+PostGIS.

Sibling DAG to rede_escolar_ingestion. Walks the MinIO prefix
    s3://raw/rede_escolar/
finds the LATEST run_date partition, parses every page_NNNNNN.geojson page in
that partition, unnests features (attributes + point geometry) into

    bronze_education.raw_rede_escolar
      (run_date, codigo_escola, source_loaded_at,
       arcgis_objectid, nome, codigo_uo, nome_uo, ..., latitude, longitude,
       geom geometry(Point, 4326), geom_pt geometry(Point, 3763))

The 42 ArcGIS field names are renamed to readable Portuguese (same convention
as publico_rankings, see wiki/concepts/dbt-source-column-descriptions.md).
PostGIS holds the dual-CRS geometries per ADR 2026-05-10 (geom for joins +
display, geom_pt for distance/area in meters).

PK: (run_date, codigo_escola). Monthly snapshots accumulate; silver picks the
latest run_date for current-state queries and reads the history for
change-over-time facts.

Idempotency: re-runs of the same logical date upsert into the same partition
(ON CONFLICT DO UPDATE on all data columns).
"""

from __future__ import annotations

import logging
from datetime import timedelta

log = logging.getLogger(__name__)

BRONZE_TABLE = "bronze_education.raw_rede_escolar"

# ---------------------------------------------------------------------------
# Column rename map — ArcGIS field name → bronze column.
# Order matters: DDL + INSERT use this dict's iteration order.
# Source field schema verified 2026-06-06 via FeatureServer ?f=json metadata.
# ---------------------------------------------------------------------------

# source_field → (renamed_column, sql_type). Geometry handled separately.
SOURCE_KEY_TO_COLUMN: dict[str, tuple[str, str]] = {
    # --- Esri internal ---
    "OBJECTID": ("arcgis_objectid", "bigint"),
    # --- Unidade Orgânica (agrupamento) ---
    "CODUOME": ("codigo_uo", "text"),  # código UO / agrupamento (DGEEC)
    "NOMEUO": ("nome_uo", "text"),
    "NIFUO": ("nif_uo", "text"),
    # --- Escola identity ---
    # CODESCME is the PK; pulled out separately so it's the first data column
    # in the table (after the composite PK).
    "NOME": ("nome", "text"),
    "SEDE": ("sede_flag", "text"),  # "S"/"N" — sede do agrupamento?
    "DTINICIO": ("data_inicio", "text"),  # not always a clean date; keep text
    # --- Endereço ---
    "MORADA": ("morada", "text"),
    "CP4": ("cp4", "text"),
    "CP3": ("cp3", "text"),
    "LOCALIDADE": ("localidade", "text"),
    "COD_CONCELHO": ("codigo_concelho", "text"),  # CAOP code
    "CONCELHO": ("concelho", "text"),
    "COD_DISTRITO": ("codigo_distrito", "text"),
    "DISTRITO": ("distrito", "text"),
    "CODDSR": ("codigo_dsr", "text"),  # Direção de Serviços de Região
    "CODQZP": ("codigo_qzp", "text"),  # Quadro de Zona Pedagógica
    "IDNUTS": ("nuts_id", "text"),
    "NUTS_DESC": ("nuts_desc", "text"),
    # --- Coordinates (kept as columns in addition to geom, for sanity checks) ---
    "LATITUDE": ("latitude", "double precision"),
    "LONGITUDE": ("longitude", "double precision"),
    # --- Tipologia + tutela + natureza ---
    "CODGRUPONATUREZAINST": ("codigo_grupo_natureza", "text"),
    "GRUPONATUREZAINST": ("grupo_natureza", "text"),
    "CODTIPOLOGIA": ("codigo_tipologia", "text"),
    "TIPOLOGIA": ("tipologia", "text"),  # e.g. "EB1", "Sec/3", "JI"
    "TUTELA": ("tutela", "text"),
    "TUTELA_DESC": ("tutela_desc", "text"),
    "ENSINOS_MIN": ("ensinos_ministrados", "text"),  # codes (concat)
    "ENSINOS_MIN_DESC": ("ensinos_ministrados_desc", "text"),
    "NATUREZAINSTITUCIONAL": ("natureza_institucional", "text"),
    "NATUREZAINSTITUCIONAL_DESC": ("natureza_institucional_desc", "text"),
    # --- Situação operacional ---
    "CODSITUACAOESCOLA": ("codigo_situacao", "text"),
    "SITUACAOESCOLA": ("situacao_escola", "text"),  # filter "Em funcionamento"
    "CICLO": ("ciclo", "text"),
    "CICLO_COD": ("codigo_ciclo", "text"),
    "DGEEC": ("dgeec_code", "text"),  # often duplicates CODESCME
    "ESCOLA_EXTINGUIR": ("flag_extinguir", "text"),
    # --- Contacto ---
    "FAX": ("fax", "text"),
    "URL": ("url", "text"),
    "EMAIL": ("email", "text"),
    "TELEFONE": ("telefone", "text"),
}

# PK: codigo_escola (CODESCME) is the natural DGEEC 6-digit key; run_date
# partitions monthly snapshots.
PK_DATA_COL = "codigo_escola"  # renamed from CODESCME (handled in loader)

SOURCE_KEYS: tuple[str, ...] = tuple(SOURCE_KEY_TO_COLUMN.keys())
RENAMED_COLS: tuple[str, ...] = tuple(r for r, _ in SOURCE_KEY_TO_COLUMN.values())
TEXT_SOURCE_KEYS: tuple[str, ...] = tuple(
    k for k, (_, t) in SOURCE_KEY_TO_COLUMN.items() if t == "text"
)
NUMERIC_SOURCE_KEYS: tuple[str, ...] = tuple(
    k for k, (_, t) in SOURCE_KEY_TO_COLUMN.items() if t in ("double precision", "bigint")
)

# Build DDL programmatically.
_data_col_lines = [
    f"  {rename:<32} {sql_type}," for rename, sql_type in SOURCE_KEY_TO_COLUMN.values()
]
_DATA_COLUMN_DDL = "\n".join(_data_col_lines)

DDL = f"""
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS bronze_education;
CREATE TABLE IF NOT EXISTS {BRONZE_TABLE} (
  run_date         date        NOT NULL,
  codigo_escola    text        NOT NULL,
  source_loaded_at timestamptz NOT NULL DEFAULT now(),
{_DATA_COLUMN_DDL}
  geom             geometry(Point, 4326),
  geom_pt          geometry(Point, 3763),
  PRIMARY KEY (run_date, codigo_escola)
);
CREATE INDEX IF NOT EXISTS raw_rede_escolar_geom_gist
  ON {BRONZE_TABLE} USING gist (geom);
CREATE INDEX IF NOT EXISTS raw_rede_escolar_geom_pt_gist
  ON {BRONZE_TABLE} USING gist (geom_pt);
CREATE INDEX IF NOT EXISTS raw_rede_escolar_dgeec
  ON {BRONZE_TABLE} (dgeec_code)
  WHERE dgeec_code IS NOT NULL AND dgeec_code <> '';
CREATE INDEX IF NOT EXISTS raw_rede_escolar_codigo_uo
  ON {BRONZE_TABLE} (codigo_uo);
CREATE INDEX IF NOT EXISTS raw_rede_escolar_situacao
  ON {BRONZE_TABLE} (situacao_escola);
"""

# Insert column list: (run_date, codigo_escola, <renamed cols...>, geom, geom_pt).
# source_loaded_at is DEFAULT now(), refreshed in ON CONFLICT.
_INSERT_COLS: tuple[str, ...] = ("run_date", "codigo_escola") + RENAMED_COLS + ("geom", "geom_pt")

# Geom values arrive as WKT; cast inside VALUES via template (psycopg2 trick).
# Use execute_values with a `template` that wraps the two geom slots in
# ST_GeomFromText(...). All other placeholders are %s.
_geom_template_slots: list[str] = []
for col in _INSERT_COLS:
    if col == "geom":
        _geom_template_slots.append("ST_GeomFromText(%s, 4326)")
    elif col == "geom_pt":
        _geom_template_slots.append("ST_Transform(ST_GeomFromText(%s, 4326), 3763)")
    else:
        _geom_template_slots.append("%s")
VALUES_TEMPLATE = "(" + ", ".join(_geom_template_slots) + ")"

_insert_col_list = ", ".join(_INSERT_COLS)
_update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in (*RENAMED_COLS, "geom", "geom_pt"))
UPSERT_SQL = f"""
INSERT INTO {BRONZE_TABLE} ({_insert_col_list})
VALUES %s
ON CONFLICT (run_date, codigo_escola)
DO UPDATE SET {_update_set}, source_loaded_at = now()
"""


def _coerce_numeric(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() == "null":
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _coerce_text(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return str(v)


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.rede_escolar.rede_escolar_config import MINIO_BUCKET, MINIO_PREFIX

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="rede_escolar_bronze_load",
        description=(
            "Load latest rede_escolar GeoJSON pages from MinIO into "
            "bronze_education.raw_rede_escolar with dual-CRS PostGIS geometry."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["rede_escolar", "gesedu", "education", "schools", "bronze", "p1"],
    )
    def rede_escolar_bronze_load():
        @task()
        def discover_latest_run() -> dict:
            """Find the most recent run_date partition + list its page blobs."""
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            # List all run_date prefixes under MINIO_PREFIX/.
            run_dates: set[str] = set()
            for obj in client.list_objects(MINIO_BUCKET, prefix=f"{MINIO_PREFIX}/", recursive=True):
                parts = obj.object_name.split("/")
                if len(parts) != 3 or not parts[2].endswith(".geojson"):
                    continue
                run_dates.add(parts[1])

            if not run_dates:
                raise RuntimeError(
                    f"No blobs under s3://{MINIO_BUCKET}/{MINIO_PREFIX}/ — "
                    "run rede_escolar_ingestion first."
                )
            latest = max(run_dates)  # YYYY-MM-DD sorts lexically
            log.info(
                "[rede_escolar-bronze] %d run_dates found, latest=%s",
                len(run_dates),
                latest,
            )
            return {"run_date": latest}

        @task()
        def fanout_pages(run_info: dict) -> list[dict]:
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            run_date = run_info["run_date"]
            prefix = f"{MINIO_PREFIX}/{run_date}/"
            specs = []
            for obj in client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True):
                if not obj.object_name.endswith(".geojson"):
                    continue
                specs.append(
                    {
                        "object_name": obj.object_name,
                        "run_date": run_date,
                        "size": obj.size,
                    }
                )
            specs.sort(key=lambda s: s["object_name"])
            log.info("[rede_escolar-bronze] %d pages in %s", len(specs), prefix)
            return specs

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
            log.info("[rede_escolar-bronze] DDL applied for %s", BRONZE_TABLE)
            return BRONZE_TABLE

        @task()
        def load_page(spec: dict, table: str) -> dict:
            """Fetch one GeoJSON page, unnest features, upsert with dual-CRS geom."""
            import json

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
            obj = mc.get_object(MINIO_BUCKET, spec["object_name"])
            try:
                body = obj.read()
            finally:
                obj.close()
                obj.release_conn()

            doc = json.loads(body)
            features = doc.get("features", [])

            known = set(SOURCE_KEYS)
            unknown_keys: set[str] = set()
            payload = []
            skipped_no_pk = 0
            skipped_no_geom = 0

            for feat in features:
                props = feat.get("properties") or {}
                geom = feat.get("geometry") or {}

                codigo_escola = _coerce_text(props.get("CODESCME"))
                if not codigo_escola:
                    skipped_no_pk += 1
                    continue

                # Geometry: GeoJSON Point => coordinates [lon, lat].
                wkt = None
                if geom.get("type") == "Point":
                    coords = geom.get("coordinates") or []
                    if len(coords) >= 2 and coords[0] is not None and coords[1] is not None:
                        try:
                            lon = float(coords[0])
                            lat = float(coords[1])
                            wkt = f"POINT({lon} {lat})"
                        except (TypeError, ValueError):
                            wkt = None
                if wkt is None:
                    skipped_no_geom += 1
                    # We still insert the row — schools without geom exist;
                    # geom + geom_pt stay NULL.

                for k in props.keys():
                    if k not in known and k != "CODESCME":
                        unknown_keys.add(k)

                row: list = [spec["run_date"], codigo_escola]
                for src_key in SOURCE_KEYS:
                    raw = props.get(src_key)
                    if src_key in TEXT_SOURCE_KEYS:
                        row.append(_coerce_text(raw))
                    else:
                        row.append(_coerce_numeric(raw))
                # geom (WKT) twice — once for geom (4326), once for geom_pt (3763
                # via ST_Transform in the VALUES template). Both can be NULL.
                row.append(wkt)
                row.append(wkt)
                payload.append(tuple(row))

            if unknown_keys:
                log.warning(
                    "[rede_escolar-bronze] %s: %d unknown source keys (dropped): %s",
                    spec["object_name"],
                    len(unknown_keys),
                    sorted(unknown_keys),
                )

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
                "[rede_escolar-bronze] %s: %d upserted (skipped %d no-pk, %d no-geom)",
                spec["object_name"],
                len(payload),
                skipped_no_pk,
                skipped_no_geom,
            )
            return {
                "object_name": spec["object_name"],
                "run_date": spec["run_date"],
                "rows_upserted": len(payload),
                "skipped_no_pk": skipped_no_pk,
                "skipped_no_geom": skipped_no_geom,
                "unknown_keys": sorted(unknown_keys),
            }

        @task()
        def summarize(results: list[dict]) -> dict:
            total = sum(r["rows_upserted"] for r in results)
            total_no_pk = sum(r["skipped_no_pk"] for r in results)
            total_no_geom = sum(r["skipped_no_geom"] for r in results)
            all_unknown: set[str] = set()
            for r in results:
                all_unknown.update(r["unknown_keys"])
            if all_unknown:
                log.warning(
                    "[rede_escolar-bronze] schema drift — add to SOURCE_KEY_TO_COLUMN: %s",
                    sorted(all_unknown),
                )
            log.info(
                "[rede_escolar-bronze] done: %d pages, %d rows, %d no-pk skipped, %d no-geom",
                len(results),
                total,
                total_no_pk,
                total_no_geom,
            )
            return {
                "pages": len(results),
                "total_rows": total,
                "skipped_no_pk": total_no_pk,
                "skipped_no_geom": total_no_geom,
                "unknown_keys": sorted(all_unknown),
            }

        run_info = discover_latest_run()
        specs = fanout_pages(run_info)
        table = ensure_table()
        loaded = load_page.partial(table=table).expand(spec=specs)
        summarize(loaded)

    return rede_escolar_bronze_load()


dag = _create_dag()
