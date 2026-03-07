"""
dbt Scoped Build — BashOperator with dynamic selector

Runs `dbt build -s <select>` where the selector comes from dag_run.conf.
Triggered by bronze DAGs via TriggerDagRunOperator to rebuild only the
downstream models affected by each data source.

Usage:
    TriggerDagRunOperator(
        trigger_dag_id="dbt_scoped_build",
        conf={"select": "stg_idealista+"},
    )

    # Manual trigger:
    airflow dags trigger dbt_scoped_build --conf '{"select": "stg_bpstat+"}'

Keep dbt_full_pipeline (Cosmos) for manual full runs with per-model visibility.
"""
from __future__ import annotations

from datetime import timedelta

from airflow.decorators import dag
from airflow.operators.bash import BashOperator


@dag(
    dag_id="dbt_scoped_build",
    description=(
        "Scoped dbt build: runs only the models specified in dag_run.conf['select']. "
        "Triggered by bronze DAGs after data loads."
    ),
    schedule=None,
    start_date=None,
    catchup=False,
    default_args={
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=3),
    },
    tags=["dbt", "scoped"],
)
def dbt_scoped_build():

    BashOperator(
        task_id="dbt_build",
        bash_command=(
            'cd /opt/airflow/dbt && '
            '/home/airflow/.local/bin/dbt deps --profiles-dir . && '
            '/home/airflow/.local/bin/dbt build '
            '-s {{ dag_run.conf.get("select", "") }} '
            '--profiles-dir .'
        ),
    )


dag = dbt_scoped_build()
