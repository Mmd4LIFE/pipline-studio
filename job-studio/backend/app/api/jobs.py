from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_editor
from app.db import get_db
from app.errors import AppError
from app.models import Deployment, Job, JobRevision, JobRun, User
from app.schemas.job import JobCreate, JobPatch, ValidateRequest  # noqa: F401
from app.services.airflow_client import AirflowClient
from app.services.deployment_reconciler import process_outbox
from app.services.ids import new_id
from app.services.job_service import (
    create_job,
    current_revision,
    enqueue_deploy,
    enqueue_simple,
    patch_job,
    serialize_job,
    validate_job_payload,
)
from app.services.sql_preview import inspect_destination, preview_source
from app.services.sql_validator import format_sql, validate_select

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    q: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    stmt = select(Job).order_by(Job.updated_at.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    jobs = db.scalars(stmt).all()
    items = [serialize_job(db, job) for job in jobs]
    if q:
        needle = q.lower()
        items = [
            item
            for item in items
            if needle in item["name"].lower()
            or needle in item["dag_id"].lower()
            or needle in item["slug"].lower()
        ]
    return items


@router.post("")
def create(
    payload: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    job = create_job(db, user.id, payload)
    return serialize_job(db, job)


@router.get("/{job_id}")
def detail(job_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    job = db.get(Job, job_id)
    if not job:
        raise AppError("validation_error", "Job not found", 404)
    return serialize_job(db, job)


@router.patch("/{job_id}")
def patch(
    job_id: str,
    payload: JobPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    job = db.get(Job, job_id)
    if not job:
        raise AppError("validation_error", "Job not found", 404)
    job = patch_job(db, job, user.id, payload)
    return serialize_job(db, job)


@router.post("/validate")
def validate(payload: ValidateRequest, _: User = Depends(require_editor)):
    validate_select(payload.source.sql)
    formatted = format_sql(payload.source.sql)
    preview = preview_source(payload.source.connection_id, payload.source.sql) if payload.preview else None
    dest_cols = None
    if payload.destination:
        dest_cols = inspect_destination(
            payload.destination.connection_id,
            payload.destination.schema_name,
            payload.destination.table,
        )
        if payload.destination.column_mapping and preview:
            from app.services.sql_preview import validate_mapping

            validate_mapping(preview.columns, dest_cols, payload.destination.column_mapping)
    return {
        "ok": True,
        "formatted_sql": formatted,
        "preview": preview.model_dump() if preview else None,
        "destination_columns": [col.model_dump() for col in dest_cols] if dest_cols else None,
    }


@router.post("/{job_id}/deploy")
def deploy(
    job_id: str,
    run_immediately: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    job = db.get(Job, job_id)
    if not job:
        raise AppError("validation_error", "Job not found", 404)
    revision = current_revision(db, job)
    if not revision:
        raise AppError("validation_error", "Job has no revision", 400)
    payload = JobCreate(
        name=job.name,
        description=job.description,
        tags=job.tags or [],
        source=revision.config_json["source"],
        destination=revision.config_json["destination"],
        load=revision.config_json.get("load") or {},
        schedule=revision.config_json.get("schedule") or {},
        run_immediately=run_immediately,
    )
    validate_job_payload(payload)
    deployment = enqueue_deploy(db, job, user.id, run_immediately)
    try:
        process_outbox(db)
    except Exception:
        pass
    db.refresh(job)
    return {"deployment_id": deployment.id, "job": serialize_job(db, job)}


@router.post("/{job_id}/run")
def run_now(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    job = db.get(Job, job_id)
    if not job:
        raise AppError("validation_error", "Job not found", 404)
    if job.status == "archived":
        raise AppError("validation_error", "Archived jobs cannot run", 400)
    enqueue_simple(
        db,
        job,
        user.id,
        "run_job",
        {"dag_run_id": f"studio_manual__{job.id}__{new_id('r')}"},
    )
    process_outbox(db)
    db.refresh(job)
    return serialize_job(db, job)


@router.post("/{job_id}/pause")
def pause(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    job = _require_job(db, job_id)
    job.status = "paused"
    job.desired_enabled = False
    enqueue_simple(db, job, user.id, "pause_job")
    process_outbox(db)
    db.refresh(job)
    return serialize_job(db, job)


@router.post("/{job_id}/resume")
def resume(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    job = _require_job(db, job_id)
    enqueue_simple(db, job, user.id, "resume_job")
    process_outbox(db)
    db.refresh(job)
    return serialize_job(db, job)


@router.post("/{job_id}/archive")
def archive(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    job = _require_job(db, job_id)
    enqueue_simple(db, job, user.id, "archive_job")
    process_outbox(db)
    db.refresh(job)
    return serialize_job(db, job)


@router.post("/{job_id}/duplicate")
def duplicate(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    job = _require_job(db, job_id)
    revision = current_revision(db, job)
    if not revision:
        raise AppError("validation_error", "Nothing to duplicate", 400)
    payload = JobCreate(
        name=f"{job.name} copy",
        description=job.description,
        tags=job.tags or [],
        source=revision.config_json["source"],
        destination=revision.config_json["destination"],
        load=revision.config_json.get("load") or {},
        schedule=revision.config_json.get("schedule") or {},
        run_immediately=False,
    )
    copy = create_job(db, user.id, payload)
    return serialize_job(db, copy)


@router.get("/{job_id}/revisions")
def revisions(job_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    job = _require_job(db, job_id)
    rows = db.scalars(
        select(JobRevision).where(JobRevision.job_id == job.id).order_by(JobRevision.revision_no.desc())
    ).all()
    return [
        {
            "id": row.id,
            "revision_no": row.revision_no,
            "sha256": row.sha256,
            "created_at": row.created_at.isoformat(),
            "config": row.config_json,
        }
        for row in rows
    ]


@router.get("/{job_id}/deployments")
def deployments(job_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    job = _require_job(db, job_id)
    rows = db.scalars(
        select(Deployment).where(Deployment.job_id == job.id).order_by(Deployment.created_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "state": row.state,
            "last_error": row.last_error,
            "attempt_count": row.attempt_count,
            "airflow_seen_at": row.airflow_seen_at.isoformat() if row.airflow_seen_at else None,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/{job_id}/runs")
def runs(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
    limit: int = Query(default=25, ge=1, le=100),
):
    job = _require_job(db, job_id)
    try:
        from app.services.deployment_reconciler import _sync_runs

        _sync_runs(db, AirflowClient(), {"job_id": job.id})
    except Exception:
        db.rollback()
    rows = db.scalars(
        select(JobRun).where(JobRun.job_id == job.id).order_by(JobRun.created_at.desc()).limit(limit)
    ).all()
    return [_run_out(row) for row in rows]


@router.get("/{job_id}/runs/{run_id}")
def run_detail(job_id: str, run_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    job = _require_job(db, job_id)
    row = db.get(JobRun, run_id)
    if not row or row.job_id != job.id:
        raise AppError("validation_error", "Run not found", 404)
    tasks = []
    try:
        tasks = AirflowClient().task_instances(job.dag_id, row.airflow_run_id)
    except Exception:
        tasks = []
    return {**_run_out(row), "tasks": tasks}


@router.get("/{job_id}/runs/{run_id}/logs")
def run_logs(job_id: str, run_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    job = _require_job(db, job_id)
    row = db.get(JobRun, run_id)
    if not row or row.job_id != job.id:
        raise AppError("validation_error", "Run not found", 404)
    client = AirflowClient()
    tasks = client.task_instances(job.dag_id, row.airflow_run_id)
    logs = []
    for task in tasks:
        try_number = int(task.get("try_number") or 1)
        content = client.task_logs(job.dag_id, row.airflow_run_id, task.get("task_id"), try_number)
        logs.append(
            {
                "task_id": task.get("task_id"),
                "state": task.get("state"),
                "content": _redact(content),
            }
        )
    return logs


def _require_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppError("validation_error", "Job not found", 404)
    return job


def _run_out(row: JobRun) -> dict:
    return {
        "id": row.id,
        "airflow_run_id": row.airflow_run_id,
        "state": row.state,
        "queued_at": row.queued_at.isoformat() if row.queued_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_ms": row.duration_ms,
        "rows_read": row.rows_read,
        "rows_written": row.rows_written,
        "error_summary": row.error_summary,
    }


def _redact(text: str) -> str:
    return (
        text.replace("password", "[redacted]")
        .replace("PASSWORD", "[redacted]")
        .replace("secret", "[redacted]")
    )
