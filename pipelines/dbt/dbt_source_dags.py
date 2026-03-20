"""
dbt Source-Scoped Builds — Cosmos per-source DAGs

Factory that generates one Cosmos DAG per data source. Each DAG rebuilds
the full downstream chain (staging → silver → gold) for its source using
DbtTaskGroup with RenderConfig(select=...).

Every dbt model becomes its own Airflow task, giving per-model visibility,
retries, and clear failure identification in the UI.

Triggered by bronze DAGs via TriggerDagRunOperator after data loads.
Manual trigger also supported.

Dependencies:
    astronomer-cosmos>=1.8.0
    dbt-postgres==1.9.0
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from airflow.decorators import dag, task
from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig, ExecutionConfig, RenderConfig
from cosmos.profiles import PostgresUserPasswordProfileMapping

DBT_PROJECT_DIR = Path("/opt/airflow/dbt")

# ── Shared Cosmos configuration (same as dbt_full_dag.py) ──────────────

PROFILE_CONFIG = ProfileConfig(
    profile_name="house4house",
    target_name="prod",
    profile_mapping=PostgresUserPasswordProfileMapping(
        conn_id="warehouse_postgres",
        profile_args={"schema": "gold_analytics"},
    ),
)

PROJECT_CONFIG = ProjectConfig(
    dbt_project_path=DBT_PROJECT_DIR,
)

EXECUTION_CONFIG = ExecutionConfig(
    dbt_executable_path="/home/airflow/.local/bin/dbt",
)

# ── Source → selector registry ──────────────────────────────────────────

DBT_SOURCE_CONFIGS: dict[str, dict] = {
    "osm": {
        "select": ["stg_osm_pois+", "stg_osm_transport+"],
        "tags": ["dbt", "cosmos", "osm"],
    },
    "idealista": {
        "select": ["stg_idealista+"],
        "tags": ["dbt", "cosmos", "idealista"],
    },
    "caop": {
        "select": ["stg_caop_distritos+", "stg_caop_municipios+", "stg_caop_freguesias+"],
        "tags": ["dbt", "cosmos", "caop"],
    },
    "bgri": {
        "select": ["stg_bgri_freguesia_agg+"],
        "tags": ["dbt", "cosmos", "bgri"],
    },
    "ine": {
        "select": ["stg_ine_indicators+"],
        "tags": ["dbt", "cosmos", "ine"],
    },
    "bpstat": {
        "select": ["stg_bpstat+"],
        "tags": ["dbt", "cosmos", "bpstat"],
    },
    "ecb": {
        "select": ["stg_ecb+"],
        "tags": ["dbt", "cosmos", "ecb"],
    },
    "eurostat": {
        "select": ["stg_eurostat+"],
        "tags": ["dbt", "cosmos", "eurostat"],
    },
    "crus": {
        "select": ["stg_crus_ordenamento+"],
        "tags": ["dbt", "cosmos", "crus"],
    },
    "bupi": {
        "select": ["stg_bupi+"],
        "tags": ["dbt", "cosmos", "bupi"],
    },
    "cadastro": {
        "select": ["stg_cadastro+"],
        "tags": ["dbt", "cosmos", "cadastro"],
    },
    "srup": {
        "select": ["stg_srup_ic+", "stg_srup_ran+", "stg_srup_dph+"],
        "tags": ["dbt", "cosmos", "srup"],
    },
}


# ── DAG factory ─────────────────────────────────────────────────────────

def _create_source_dag(source: str, config: dict):
    """Create a Cosmos DAG for a single data source."""

    dag_id = f"dbt_{source}_build"

    @dag(
        dag_id=dag_id,
        description=f"dbt build for {source}: staging → silver → gold (Cosmos per-model tasks).",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args={
            "owner": "data-engineering",
            "retries": 1,
            "retry_delay": timedelta(minutes=3),
        },
        tags=config.get("tags", ["dbt", "cosmos"]),
    )
    def source_dag():
        dbt_build = DbtTaskGroup(
            group_id="dbt_build",
            project_config=PROJECT_CONFIG,
            profile_config=PROFILE_CONFIG,
            execution_config=EXECUTION_CONFIG,
            render_config=RenderConfig(
                select=config["select"],
            ),
            operator_args={
                "install_deps": True,
            },
        )

        @task(trigger_rule="all_success")
        def regenerate_docs():
            """Regenerate dbt docs (catalog.json + manifest.json).

            The static files in target/ are updated in place. If dbt docs serve
            is already running it will pick up changes on next page load.
            """
            import subprocess

            dbt_bin = str(EXECUTION_CONFIG.dbt_executable_path)
            project_dir = str(DBT_PROJECT_DIR)

            subprocess.run(
                [dbt_bin, "docs", "generate", "--profiles-dir", project_dir],
                cwd=project_dir,
                check=True,
                capture_output=True,
                text=True,
            )

        dbt_build >> regenerate_docs()

    return source_dag()


# Generate all DAGs — Airflow discovers them as module-level variables.
for _source, _config in DBT_SOURCE_CONFIGS.items():
    globals()[f"dbt_{_source}_build"] = _create_source_dag(_source, _config)
