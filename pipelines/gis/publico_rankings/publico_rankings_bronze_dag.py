"""
Público Rankings Bronze Load — MinIO → Postgres

Sibling DAG to publico_rankings_ingestion. Walks the MinIO prefix
    s3://raw/publico_rankings/
discovers every {year}/{kind}.json blob, parses it, and upserts unnested
rows into

    bronze_education.raw_publico_rankings
      (year, kind, eid, source_loaded_at, nome, id_publico, concelho,
       contexto_agrupamento, codigo_uo_dgeec, latitude, longitude,
       media_total_exames, ranking_exames, ...)               -- 95 columns

The schema unnests the source JSON: each cryptic 1-6 char source key is mapped
to a human-readable Portuguese column name via `SOURCE_KEY_TO_COLUMN`. Source
values arrive as a mix of JSON numbers and JSON strings (Público is inconsistent
year-over-year); the loader coerces both to float and writes NULL on parse
failure. The raw JSONB blob is intentionally NOT retained — MinIO holds the
verbatim audit trail, so the bronze table can stay typed.

Column-name source: every mapping below was verified against Público's
interactive school card for eid=1069 (Escola Dr. Ferreira da Silva,
Oliveira de Azeméis, 2024 sec). The full label-by-label cross-check lives
at wiki/concepts/publico-rankings-column-legend.md.

Disciplina codebook collision: the source uses two *different* discipline
suffixes:
  1-letter (in m*/n*/r*/nim*/nip*): m=Mat A, p=Port, b=Bio-Geo, f=FQ-A,
    g=Geo-A, fl=Filo, h=His-A, ma=Economia A, i=MACS
  2-letter (in rs*): ma=Mat A, po=Port, bi=Bio, fq=FQ, ge=Geo, fi=Filo,
    ec=Economia, mc=MACS
Note `ma` flips: Economia in 1-letter, Matemática A in 2-letter. The rename
map below resolves both into the same renamed column suffix.

Idempotency: PRIMARY KEY (year, kind, eid) + ON CONFLICT DO UPDATE on every
unnested column means full replays are safe and source_loaded_at refreshes
per row.
"""

from __future__ import annotations

import logging
from datetime import timedelta

log = logging.getLogger(__name__)

BRONZE_TABLE = "bronze_education.raw_publico_rankings"

# ---------------------------------------------------------------------------
# Column rename map — source JSON key → bronze column name (human-readable).
# Order matters: insert/SELECT/DDL all use this dict's iteration order.
# Verified against UI screenshots; see wiki/concepts/publico-rankings-column-legend.md.
# ---------------------------------------------------------------------------

# Source-key → (renamed_column, sql_type). text for identifiers/labels,
# double precision for everything else.
SOURCE_KEY_TO_COLUMN: dict[str, tuple[str, str]] = {
    # --- Identity & geography ---
    "e":     ("nome",                  "text"),
    "id":    ("id_publico",            "text"),
    "co":    ("concelho",              "text"),
    "c":     ("contexto_agrupamento",  "text"),
    "coduo": ("codigo_uo_dgeec",       "text"),
    "lt":    ("latitude",              "double precision"),
    "ln":    ("longitude",             "double precision"),
    "t":     ("tipo",                  "double precision"),  # 1=privado, 2=publico
    # --- Headline principal ---
    "mt":    ("media_total_exames",    "double precision"),
    "rt":    ("ranking_exames",        "double precision"),
    "nt":    ("num_provas_total",      "double precision"),
    # --- Ranking da Superação ---
    "rs":    ("ranking_superacao",     "double precision"),
    "v":     ("media_esperada",        "double precision"),
    # --- Per-disciplina principal (1-letter codebook) ---
    # m = Matemática A, p = Português, b = Bio-Geo, f = Física-Química A,
    # g = Geografia A, fl = Filosofia, h = História A, ma = ECONOMIA A, i = MACS
    "mm":    ("media_matematica_a",    "double precision"),
    "mp":    ("media_portugues",       "double precision"),
    "mb":    ("media_bio_geo",         "double precision"),
    "mf":    ("media_fq_a",            "double precision"),
    "mg":    ("media_geografia_a",     "double precision"),
    "mfl":   ("media_filosofia",       "double precision"),
    "mh":    ("media_historia_a",      "double precision"),
    "mma":   ("media_economia_a",      "double precision"),
    "mi":    ("media_macs",            "double precision"),
    "nm":    ("num_provas_matematica_a", "double precision"),
    "np":    ("num_provas_portugues",  "double precision"),
    "nb":    ("num_provas_bio_geo",    "double precision"),
    "nf":    ("num_provas_fq_a",       "double precision"),
    "ng":    ("num_provas_geografia_a","double precision"),
    "nfl":   ("num_provas_filosofia",  "double precision"),
    "nh":    ("num_provas_historia_a", "double precision"),
    "nma":   ("num_provas_economia_a", "double precision"),
    "ni":    ("num_provas_macs",       "double precision"),
    "rm":    ("ranking_matematica_a",  "double precision"),
    "rp":    ("ranking_portugues",     "double precision"),
    "rb":    ("ranking_bio_geo",       "double precision"),
    "rf":    ("ranking_fq_a",          "double precision"),
    "rg":    ("ranking_geografia_a",   "double precision"),
    "rfl":   ("ranking_filosofia",     "double precision"),
    "rh":    ("ranking_historia_a",    "double precision"),
    "rma":   ("ranking_economia_a",    "double precision"),
    "ri":    ("ranking_macs",          "double precision"),
    # --- Nota Interna (CIF — Classificação Interna de Frequência) ---
    # Same 1-letter codebook.
    "nimm":  ("cif_media_matematica_a", "double precision"),
    "nimp":  ("cif_media_portugues",   "double precision"),
    "nimb":  ("cif_media_bio_geo",     "double precision"),
    "nimf":  ("cif_media_fq_a",        "double precision"),
    "nimg":  ("cif_media_geografia_a", "double precision"),
    "nimfl": ("cif_media_filosofia",   "double precision"),
    "nimma": ("cif_media_economia_a",  "double precision"),
    "nimi":  ("cif_media_macs",        "double precision"),
    "nipm":  ("cif_ranking_matematica_a", "double precision"),
    "nipp":  ("cif_ranking_portugues", "double precision"),
    "nipb":  ("cif_ranking_bio_geo",   "double precision"),
    "nipf":  ("cif_ranking_fq_a",      "double precision"),
    "nipg":  ("cif_ranking_geografia_a","double precision"),
    "nipfl": ("cif_ranking_filosofia", "double precision"),
    "nipma": ("cif_ranking_economia_a","double precision"),
    "nipi":  ("cif_ranking_macs",      "double precision"),
    # --- Per-disciplina Superação (2-letter codebook) ---
    # CAREFUL: 'ma' here = Matemática A, NOT Economia (opposite of 1-letter codebook).
    "rsma":  ("ranking_superacao_matematica_a", "double precision"),
    "rspo":  ("ranking_superacao_portugues",    "double precision"),
    "rsbi":  ("ranking_superacao_bio_geo",      "double precision"),
    "rsfq":  ("ranking_superacao_fq_a",         "double precision"),
    "rsge":  ("ranking_superacao_geografia_a",  "double precision"),
    "rsfi":  ("ranking_superacao_filosofia",    "double precision"),
    "rsec":  ("ranking_superacao_economia_a",   "double precision"),
    "rsmc":  ("ranking_superacao_macs",         "double precision"),
    # --- Prior-year carry (rolling history of mt/rt) ---
    # The YY suffix is legacy: in newer files these hold the IMMEDIATELY PRIOR
    # year, regardless of literal digits. e.g. m21 in the 2024 file = 2023 value.
    "m17":   ("media_legacy_y17",      "double precision"),
    "m18":   ("media_legacy_y18",      "double precision"),
    "m19":   ("media_legacy_y19",      "double precision"),
    "m20":   ("media_legacy_y20",      "double precision"),
    "m21":   ("media_ano_anterior",    "double precision"),
    "r17":   ("ranking_legacy_y17",    "double precision"),
    "r18":   ("ranking_legacy_y18",    "double precision"),
    "r19":   ("ranking_legacy_y19",    "double precision"),
    "r20":   ("ranking_legacy_y20",    "double precision"),
    "r21":   ("ranking_ano_anterior",  "double precision"),
    # --- Contexto socioeconómico ---
    "hp":    ("habilitacoes_pais",     "double precision"),  # anos escolaridade pai (média)
    "hm":    ("habilitacoes_maes",     "double precision"),  # anos escolaridade mãe (média)
    "ac":    ("pct_sem_ase",           "double precision"),  # % alunos SEM Acção Social Escolar
    "im":    ("idade_media_12ano",     "double precision"),  # idade média alunos no 12º ano
    "pdq":   ("pct_professores_quadros","double precision"), # % corpo docente em quadros
    # --- Taxa de retenção (10º/11º/12º para sec; 7º/8º/9º para 9ano) ---
    "tx0":   ("taxa_retencao_ano0",    "double precision"),  # 10º (sec) ou 7º (9ano)
    "tx1":   ("taxa_retencao_ano1",    "double precision"),  # 11º ou 8º
    "tx2":   ("taxa_retencao_ano2",    "double precision"),  # 12º ou 9º
    # --- Equidade ---
    "pde":   ("equidade_pct_ase_3anos",     "double precision"),  # % alunos ASE concluíram em 3 anos
    "pdp":   ("equidade_pct_pais_3anos",    "double precision"),  # % país com perfil semelhante em 3 anos
    "pdr":   ("equidade_ranking_diferenca", "double precision"),  # ranking da diferença escola vs país
    # --- Equivalência à Frequência ---
    "eq1":         ("equivalencia_comp1",       "double precision"),
    "eq2":         ("equivalencia_comp2",       "double precision"),
    "eq3":         ("equivalencia_delta",       "double precision"),
    "eqnaousar":   ("equivalencia_flag_nao_usar","double precision"),
    "eqnusar":     ("equivalencia_flag_nao_usar_v2","double precision"),
    "re":          ("ranking_equivalencia",     "double precision"),
}

PK_COLS: tuple[str, str, str] = ("year", "kind", "eid")
SOURCE_KEYS: tuple[str, ...] = tuple(SOURCE_KEY_TO_COLUMN.keys())
RENAMED_COLS: tuple[str, ...] = tuple(rename for rename, _ in SOURCE_KEY_TO_COLUMN.values())
TEXT_SOURCE_KEYS: tuple[str, ...] = tuple(
    k for k, (_, t) in SOURCE_KEY_TO_COLUMN.items() if t == "text"
)
NUMERIC_SOURCE_KEYS: tuple[str, ...] = tuple(
    k for k, (_, t) in SOURCE_KEY_TO_COLUMN.items() if t == "double precision"
)
ALL_INSERT_COLS: tuple[str, ...] = PK_COLS + RENAMED_COLS

# Build DDL programmatically.
_data_col_lines = [
    f"  {rename:<35} {sql_type}," for rename, sql_type in SOURCE_KEY_TO_COLUMN.values()
]
_DATA_COLUMN_DDL = "\n".join(_data_col_lines)

DDL = f"""
CREATE SCHEMA IF NOT EXISTS bronze_education;
CREATE TABLE IF NOT EXISTS {BRONZE_TABLE} (
  year             smallint    NOT NULL,
  kind             text        NOT NULL CHECK (kind IN ('sec','9ano')),
  eid              text        NOT NULL,
  source_loaded_at timestamptz NOT NULL DEFAULT now(),
{_DATA_COLUMN_DDL}
  PRIMARY KEY (year, kind, eid)
);
CREATE INDEX IF NOT EXISTS raw_publico_rankings_codigo_uo_dgeec
  ON {BRONZE_TABLE} (codigo_uo_dgeec)
  WHERE codigo_uo_dgeec IS NOT NULL AND codigo_uo_dgeec <> '';
"""

# Templated UPSERT.
_update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in RENAMED_COLS)
_insert_col_list = ", ".join(ALL_INSERT_COLS)
UPSERT_SQL = f"""
INSERT INTO {BRONZE_TABLE} ({_insert_col_list})
VALUES %s
ON CONFLICT (year, kind, eid)
DO UPDATE SET {_update_set}, source_loaded_at = now()
"""


def _coerce_numeric(v):
    """Coerce a raw JSON value to float or None. NULL on parse failure."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
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
    """Coerce a raw JSON value to text or None. Empty strings → None."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return str(v)


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.publico_rankings.publico_rankings_config import (
        MINIO_BUCKET,
        MINIO_PREFIX,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="publico_rankings_bronze_load",
        description=(
            "Load Público rankings from MinIO into bronze_education.raw_publico_rankings "
            "(unnested + human-readable column names)."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["publico", "rankings", "education", "schools", "bronze", "p1"],
    )
    def publico_rankings_bronze_load():
        @task()
        def discover_objects() -> list[dict]:
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            specs = []
            for obj in client.list_objects(
                MINIO_BUCKET, prefix=f"{MINIO_PREFIX}/", recursive=True
            ):
                parts = obj.object_name.split("/")
                if len(parts) != 3 or not parts[2].endswith(".json"):
                    log.warning("[publico-bronze] skipping unrecognized key %s", obj.object_name)
                    continue
                year = int(parts[1])
                kind = parts[2][: -len(".json")]
                if kind not in ("sec", "9ano"):
                    log.warning("[publico-bronze] skipping unknown kind %s", obj.object_name)
                    continue
                specs.append(
                    {"object_name": obj.object_name, "year": year, "kind": kind, "size": obj.size}
                )
            log.info("[publico-bronze] discovered %d blobs in MinIO", len(specs))
            if not specs:
                raise RuntimeError(
                    f"No blobs under s3://{MINIO_BUCKET}/{MINIO_PREFIX}/ — "
                    "run publico_rankings_ingestion first."
                )
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
            log.info("[publico-bronze] DDL applied for %s", BRONZE_TABLE)
            return BRONZE_TABLE

        @task()
        def load_one(spec: dict, table: str) -> dict:
            """Fetch one MinIO blob, parse JSON, unnest into renamed columns, upsert."""
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

            rows = json.loads(body)
            if not isinstance(rows, list):
                raise ValueError(
                    f"{spec['object_name']}: expected JSON array, got {type(rows).__name__}"
                )

            known = set(SOURCE_KEYS)
            unknown_keys = set()
            payload = []
            for r in rows:
                eid = r.get("eid")
                if eid is None:
                    log.warning(
                        "[publico-bronze] row in %s missing 'eid', skipping",
                        spec["object_name"],
                    )
                    continue
                for k in r.keys():
                    if k not in known and k != "eid":
                        unknown_keys.add(k)
                tup = [spec["year"], spec["kind"], str(eid)]
                for src_key in SOURCE_KEYS:
                    if src_key in TEXT_SOURCE_KEYS:
                        tup.append(_coerce_text(r.get(src_key)))
                    else:
                        tup.append(_coerce_numeric(r.get(src_key)))
                payload.append(tuple(tup))

            if unknown_keys:
                log.warning(
                    "[publico-bronze] %s/%s: source has %d unknown keys (dropped): %s",
                    spec["year"], spec["kind"], len(unknown_keys), sorted(unknown_keys),
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
                    execute_values(cur, UPSERT_SQL, payload)
                conn.commit()
            finally:
                conn.close()

            log.info(
                "[publico-bronze] upserted %d rows for %s/%s",
                len(payload), spec["year"], spec["kind"],
            )
            return {
                "year": spec["year"],
                "kind": spec["kind"],
                "rows_upserted": len(payload),
                "unknown_keys": sorted(unknown_keys),
            }

        @task()
        def summarize(results: list[dict]) -> dict:
            total = sum(r["rows_upserted"] for r in results)
            all_unknown: set[str] = set()
            for r in sorted(results, key=lambda x: (x["year"], x["kind"])):
                log.info(
                    "[publico-bronze]   %d/%s -> %d rows%s",
                    r["year"], r["kind"], r["rows_upserted"],
                    f" (unknown keys: {r['unknown_keys']})" if r["unknown_keys"] else "",
                )
                all_unknown.update(r["unknown_keys"])
            if all_unknown:
                log.warning(
                    "[publico-bronze] schema drift — add to SOURCE_KEY_TO_COLUMN: %s",
                    sorted(all_unknown),
                )
            log.info(
                "[publico-bronze] done: %d (year,kind) partitions, %d total rows",
                len(results), total,
            )
            return {
                "partitions": len(results),
                "total_rows": total,
                "unknown_keys": sorted(all_unknown),
            }

        specs = discover_objects()
        table = ensure_table()
        loaded = load_one.partial(table=table).expand(spec=specs)
        summarize(loaded)

    return publico_rankings_bronze_load()


dag = _create_dag()
