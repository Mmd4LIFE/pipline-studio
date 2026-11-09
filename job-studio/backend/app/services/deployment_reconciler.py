from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Deployment, Job, JobRevision, JobRun, OutboxEvent
from app.security import later, utcnow
from app.services.airflow_client import AirflowClient, AirflowUnavailable
from app.services.ids import new_id
from app.services.spec_publisher import publish_spec, unpublish_spec

logger = logging.getLogger("studio.reconciler")
MAX_ATTEMPTS = 40


def process_outbox(db: Session) -> None:
    events = db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.status == "pending", OutboxEvent.next_attempt_at <= utcnow())
        .order_by(OutboxEvent.created_at)
        .limit(20)
    ).all()
    client = AirflowClient()
    for event in events:
        event.attempts += 1
        try:
            if event.event_type == "deploy_job":
                _deploy(db, client, event.payload_json)
            elif event.event_type == "pause_job":
                _pause(db, client, event.payload_json, paused=True)
            elif event.event_type == "resume_job":
                _pause(db, client, event.payload_json, paused=False)
            elif event.event_type == "run_job":
                _run(db, client, event.payload_json)
            elif event.event_type == "archive_job":
                _archive(db, client, event.payload_json)
            elif event.event_type == "sync_runs":
                _sync_runs(db, client, event.payload_json)
            else:
                raise RuntimeError(f"Unknown event {event.event_type}")
            event.status = "done"
            event.last_error = None
        except Exception as exc:
            logger.exception("Outbox event %s failed", event.id)
            event.last_error = str(exc)[:2000]
            if event.attempts >= MAX_ATTEMPTS:
                event.status = "failed"
                _mark_job_failed(db, event)
            else:
                event.next_attempt_at = later(min(120, 5 * event.attempts))
        event.updated_at = utcnow()
        db.commit()


def _job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise RuntimeError("Job disappeared")
    return job


def _deploy(db: Session, client: AirflowClient, payload: dict) -> None:
    job = _job(db, payload["job_id"])
    deployment = db.get(Deployment, payload["deployment_id"])
    if not deployment:
        raise RuntimeError("Deployment disappeared")
    revision = db.get(JobRevision, deployment.revision_id)
    if not revision:
        raise RuntimeError("Revision disappeared")
    job.status = "publish_pending"
    publish_spec(revision.config_json)
    deployment.state = "deploying"
    job.status = "deploying"
    db.commit()

    dag = client.get_dag(job.dag_id)
    if not dag:
        raise AirflowUnavailable("DAG not yet visible to Airflow")

    deployment.airflow_seen_at = utcnow()
    client.set_paused(job.dag_id, paused=False)
    job.desired_enabled = True
    job.status = "active"
    if deployment.run_immediately and deployment.trigger_run_id:
        run = client.trigger_run(job.dag_id, deployment.trigger_run_id)
        _upsert_run(db, job, revision.id, run)
        db.add(
            OutboxEvent(
                id=new_id("obx"),
                event_type="sync_runs",
                payload_json={"job_id": job.id},
                next_attempt_at=later(5),
            )
        )
    deployment.state = "active"
    deployment.last_error = None
    db.commit()


def _pause(db: Session, client: AirflowClient, payload: dict, paused: bool) -> None:
    job = _job(db, payload["job_id"])
    client.set_paused(job.dag_id, paused=paused)
    job.desired_enabled = not paused
    job.status = "paused" if paused else "active"
    db.commit()


def _run(db: Session, client: AirflowClient, payload: dict) -> None:
    job = _job(db, payload["job_id"])
    run_id = payload.get("dag_run_id") or f"studio_manual__{job.id}__{int(utcnow().timestamp())}"
    run = client.trigger_run(job.dag_id, run_id)
    revision_id = job.current_revision_id
    _upsert_run(db, job, revision_id, run)
    db.add(
        OutboxEvent(
            id=new_id("obx"),
            event_type="sync_runs",
            payload_json={"job_id": job.id},
            next_attempt_at=later(5),
        )
    )
    db.commit()


def _archive(db: Session, client: AirflowClient, payload: dict) -> None:
    job = _job(db, payload["job_id"])
    try:
        if client.get_dag(job.dag_id):
            client.set_paused(job.dag_id, paused=True)
    except AirflowUnavailable:
        logger.warning("Airflow unavailable while archiving %s", job.dag_id)
    unpublish_spec(job.id)
    job.desired_enabled = False
    job.status = "archived"
    db.commit()


def _sync_runs(db: Session, client: AirflowClient, payload: dict) -> None:
    job = _job(db, payload["job_id"])
    runs = client.list_runs(job.dag_id, limit=20)
    for run in runs:
        stored = _upsert_run(db, job, job.current_revision_id, run)
        _attach_metrics(client, job, stored, run)
    still_running = any(
        (run.get("state") or "").lower() in {"queued", "running", "scheduled"} for run in runs
    )
    db.commit()
    if still_running:
        raise AirflowUnavailable("Runs still in progress")


def _upsert_run(db: Session, job: Job, revision_id: str | None, run: dict) -> JobRun:
    airflow_run_id = run.get("dag_run_id") or run.get("run_id")
    if not airflow_run_id:
        raise RuntimeError("Airflow run payload missing dag_run_id")
    existing = db.scalars(
        select(JobRun).where(JobRun.job_id == job.id, JobRun.airflow_run_id == airflow_run_id)
    ).first()
    if not existing:
        existing = JobRun(
            id=new_id("run"),
            job_id=job.id,
            airflow_run_id=airflow_run_id,
            revision_id=revision_id,
        )
        db.add(existing)
    existing.state = (run.get("state") or "queued").lower()
    existing.queued_at = _ts(run.get("queued_at") or run.get("execution_date"))
    existing.started_at = _ts(run.get("start_date"))
    existing.ended_at = _ts(run.get("end_date"))
    if existing.started_at and existing.ended_at:
        existing.duration_ms = int((existing.ended_at - existing.started_at).total_seconds() * 1000)
    existing.updated_at = utcnow()
    db.flush()
    return existing


def _attach_metrics(client: AirflowClient, job: Job, stored: JobRun, run: dict) -> None:
    tasks = client.task_instances(job.dag_id, stored.airflow_run_id)
    failed = [task for task in tasks if (task.get("state") or "").lower() == "failed"]
    if failed:
        stored.error_summary = (failed[0].get("note") or "Task failed")[:1000]
    for task in tasks:
        if task.get("task_id") != "extract_and_load_task":
            continue
        try_number = int(task.get("try_number") or 1)
        logs = client.task_logs(job.dag_id, stored.airflow_run_id, task["task_id"], try_number)
        match = re.search(r"STUDIO_METRICS (\{.*\})", logs)
        if match:
            try:
                metrics = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            stored.rows_read = metrics.get("rows_read")
            stored.rows_written = metrics.get("rows_written")
            stored.duration_ms = metrics.get("duration_ms") or stored.duration_ms
            stored.source_query_duration_ms = metrics.get("source_query_duration_ms")
            stored.load_duration_ms = metrics.get("load_duration_ms")


def _mark_job_failed(db: Session, event: OutboxEvent) -> None:
    job_id = (event.payload_json or {}).get("job_id")
    if not job_id:
        return
    job = db.get(Job, job_id)
    if job and event.event_type == "deploy_job":
        job.status = "failed_deployment"
        dep_id = event.payload_json.get("deployment_id")
        if dep_id:
            deployment = db.get(Deployment, dep_id)
            if deployment:
                deployment.state = "failed_deployment"
                deployment.last_error = event.last_error


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
