"""
dbt Gold Layer — Builds gold_analytics models via dbt.

Trigger manually after bronze loads complete.
Runs: dbt deps → dbt run → dbt test → dbt docs generate
"""
from __future__ import annotations

from datetime import timedelta

from airflow.decorators import dag
from airflow.operators.bash import BashOperator

DBT_DIR = "/opt/airflow/dbt"


@dag(
    dag_id="dbt_gold_build",
    description="Run dbt models for gold_analytics layer",
    schedule=None,
    start_date=None,
    catchup=False,
    default_args={
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["dbt", "gold", "analytics"],
)
def dbt_gold_build():

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"cd {DBT_DIR} && dbt deps",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_DIR} && dbt run --select gold",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --select gold",
    )

    dbt_docs = BashOperator(
        task_id="dbt_docs_generate",
        bash_command=f"cd {DBT_DIR} && dbt docs generate",
    )

    dbt_deps >> dbt_run >> dbt_test >> dbt_docs


dag = dbt_gold_build()
