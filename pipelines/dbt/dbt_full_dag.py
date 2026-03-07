"""
dbt Full Pipeline — Cosmos DbtTaskGroup

Runs all three dbt layers (staging → silver → gold) with one Airflow task
per model. The full dbt ref() lineage graph is visible in the Airflow UI.

Trigger: manually, or via TriggerDagRunOperator from the last bronze DAG
in each daily batch.

Dependencies:
    astronomer-cosmos>=1.8.0
    dbt-postgres==1.9.0
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from airflow.decorators import dag
from airflow.operators.empty import EmptyOperator
from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig, ExecutionConfig
from cosmos.profiles import PostgresUserPasswordProfileMapping

DBT_PROJECT_DIR = Path("/opt/airflow/dbt")


@dag(
    dag_id="dbt_full_pipeline",
    description=(
        "Full dbt medallion pipeline: staging views → silver tables → gold analytics. "
        "One Airflow task per dbt model; dependency graph matches dbt ref() lineage."
    ),
    schedule=None,
    start_date=None,
    catchup=False,
    default_args={
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=3),
    },
    tags=["dbt", "cosmos", "staging", "silver", "gold"],
)
def dbt_full_pipeline():

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    profile_config = ProfileConfig(
        profile_name="house4house",
        target_name="prod",
        profile_mapping=PostgresUserPasswordProfileMapping(
            conn_id="warehouse_postgres",
            profile_args={"schema": "gold_analytics"},
        ),
    )

    project_config = ProjectConfig(
        dbt_project_path=DBT_PROJECT_DIR,
    )

    execution_config = ExecutionConfig(
        dbt_executable_path="/home/airflow/.local/bin/dbt",
    )

    transform = DbtTaskGroup(
        group_id="dbt_transform",
        project_config=project_config,
        profile_config=profile_config,
        execution_config=execution_config,
        operator_args={
            "install_deps": True,
        },
    )

    start >> transform >> end


dag = dbt_full_pipeline()
