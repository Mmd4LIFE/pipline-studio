"""Trusted static DAG factory for SQL Pipeline Studio.

Reads validated JSON specs from /opt/airflow/managed-jobs/current/.
Never imports or executes user-provided Python.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException

from studio_etl import extract_and_load, load_frozen_spec

CURRENT_DIR = Path("/opt/airflow/managed-jobs/current")
logger = logging.getLogger("studio_managed_jobs")


def _iter_specs() -> list[dict]:
    specs: list[dict] = []
    if not CURRENT_DIR.is_dir():
        return specs
    for path in sorted(CURRENT_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                spec = json.load(handle)
            dag_id = spec.get("dag_id")
            if not isinstance(dag_id, str) or not dag_id.startswith("studio_"):
                raise ValueError("dag_id must start with studio_")
            specs.append(spec)
        except Exception:
            logger.exception("Rejected malformed Studio spec %s", path)
    specs.sort(key=lambda item: item.get("dag_id") or "")
    return specs


def _build_dag(spec: dict):
    dag_id = spec["dag_id"]
    job_id = spec["job_id"]
    published_revision = int(spec["revision"])
    schedule_cfg = spec.get("schedule") or {}
    cron = schedule_cfg.get("cron")
    timezone = schedule_cfg.get("timezone") or "Asia/Tehran"
    catchup = bool(schedule_cfg.get("catchup", False))
    max_active_runs = int(schedule_cfg.get("max_active_runs") or 1)
    retries = int(schedule_cfg.get("retries") or 2)
    retry_delay = int(schedule_cfg.get("retry_delay_seconds") or 300)
    execution_timeout = int(schedule_cfg.get("execution_timeout_seconds") or 1200)
    tz = pendulum.timezone(timezone)

    @dag(
        dag_id=dag_id,
        description=spec.get("name") or dag_id,
        start_date=pendulum.datetime(2026, 11, 1, tz=tz),
        schedule=cron or None,
        catchup=catchup,
        max_active_runs=max_active_runs,
        is_paused_upon_creation=True,
        tags=["studio", "managed"],
        render_template_as_native_obj=False,
    )
    def studio_job():
        @task(retries=0)
        def validate_runtime_config() -> dict:
            frozen = load_frozen_spec(job_id, published_revision)
            if frozen.get("dag_id") != dag_id:
                raise ValueError("Frozen spec dag_id mismatch")
            return {"job_id": job_id, "revision": published_revision}

        @task(
            retries=retries,
            retry_delay=pendulum.duration(seconds=retry_delay),
            execution_timeout=pendulum.duration(seconds=execution_timeout),
        )
        def extract_and_load_task(meta: dict) -> dict:
            frozen = load_frozen_spec(meta["job_id"], int(meta["revision"]))
            return extract_and_load(frozen)

        @task(retries=0)
        def record_load_metrics(metrics: dict | None) -> dict:
            if not metrics:
                raise AirflowSkipException("No metrics recorded")
            return {
                "rows_read": metrics.get("rows_read"),
                "rows_written": metrics.get("rows_written"),
                "duration_ms": metrics.get("duration_ms"),
                "job_revision": metrics.get("job_revision"),
            }

        meta = validate_runtime_config()
        metrics = extract_and_load_task(meta)
        record_load_metrics(metrics)

    return studio_job()


for _spec in _iter_specs():
    try:
        globals()[_spec["dag_id"]] = _build_dag(_spec)
    except Exception:
        logger.exception("Failed to register Studio DAG from spec %s", _spec.get("dag_id"))
