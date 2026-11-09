from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ConnectionRef, Deployment, Job, JobRevision, JobRun, OutboxEvent
from app.schemas.job import JobCreate, JobPatch
from app.security import utcnow
from app.services.ids import new_id, slugify, spec_hash
from app.services.sql_preview import auto_map_columns, inspect_destination, preview_source, validate_mapping
from app.services.sql_validator import SqlValidationError, format_sql, validate_select


APPROVED_SOURCES = {"ludo_source"}
APPROVED_DESTS = {"warehouse"}


def audit(db: Session, actor_id: str | None, entity_type: str, entity_id: str, action: str, after: dict | None = None) -> None:
    db.add(
        AuditEvent(
            id=new_id("aud"),
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            after_json=after,
        )
    )


def _unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    n = 2
    while db.scalar(select(Job).where(Job.slug == slug)):
        slug = f"{base}_{n}"
        n += 1
    return slug


def spec_from_create(job: Job, revision_no: int, payload: JobCreate) -> dict[str, Any]:
    dest = payload.destination
    return {
        "schema_version": 1,
        "job_id": job.id,
        "revision": revision_no,
        "name": payload.name,
        "dag_id": job.dag_id,
        "source": payload.source.model_dump(),
        "destination": {
            "connection_id": dest.connection_id,
            "schema": dest.schema_name,
            "table": dest.table,
            "create_table": dest.create_table,
            "column_mapping": dest.column_mapping,
        },
        "load": payload.load.model_dump(),
        "schedule": payload.schedule.model_dump(),
        "alerts": {"enabled": False},
    }


def validate_job_payload(payload: JobCreate, preview: bool = False) -> dict[str, Any]:
    if payload.source.connection_id not in APPROVED_SOURCES:
        raise SqlValidationError("Source connection is not approved")
    if payload.destination.connection_id not in APPROVED_DESTS:
        raise SqlValidationError("Destination connection is not approved")
    if payload.destination.create_table:
        raise SqlValidationError("Create-table is not enabled in this release")
    if payload.destination.schema_name != "analytics":
        raise SqlValidationError("Writable schema is limited to analytics")
    validate_select(payload.source.sql)
    formatted = format_sql(payload.source.sql)
    preview_result = preview_source(payload.source.connection_id, payload.source.sql)
    dest_cols = inspect_destination(
        payload.destination.connection_id,
        payload.destination.schema_name,
        payload.destination.table,
    )
    payload.destination.column_mapping = auto_map_columns(
        preview_result.columns, dest_cols, payload.destination.column_mapping
    )
    validate_mapping(preview_result.columns, dest_cols, payload.destination.column_mapping)
    return {
        "formatted_sql": formatted,
        "preview": preview_result.model_dump() if preview else None,
        "source_columns": [col.model_dump() for col in preview_result.columns],
        "destination_columns": [col.model_dump() for col in dest_cols],
    }


def create_job(db: Session, owner_id: str, payload: JobCreate) -> Job:
    validate_job_payload(payload, preview=False)
    slug = _unique_slug(db, payload.name)
    job = Job(
        id=new_id("job"),
        slug=slug,
        name=payload.name,
        description=payload.description,
        dag_id=f"studio_{slug}",
        owner_id=owner_id,
        status="draft",
        desired_enabled=False,
        tags=payload.tags,
    )
    db.add(job)
    db.flush()
    revision = _store_revision(db, job, owner_id, payload)
    job.current_revision_id = revision.id
    audit(db, owner_id, "job", job.id, "create", {"slug": slug, "dag_id": job.dag_id})
    db.commit()
    db.refresh(job)
    return job


def _store_revision(db: Session, job: Job, owner_id: str, payload: JobCreate) -> JobRevision:
    latest = db.scalars(
        select(JobRevision).where(JobRevision.job_id == job.id).order_by(JobRevision.revision_no.desc())
    ).first()
    revision_no = (latest.revision_no + 1) if latest else 1
    config = spec_from_create(job, revision_no, payload)
    revision = JobRevision(
        id=new_id("rev"),
        job_id=job.id,
        revision_no=revision_no,
        config_json=config,
        sha256=spec_hash(config),
        created_by=owner_id,
    )
    db.add(revision)
    db.flush()
    return revision


def current_revision(db: Session, job: Job) -> JobRevision | None:
    if not job.current_revision_id:
        return None
    return db.get(JobRevision, job.current_revision_id)


def patch_job(db: Session, job: Job, owner_id: str, payload: JobPatch) -> Job:
    if job.status == "archived":
        raise SqlValidationError("Archived jobs cannot be edited")
    current = current_revision(db, job)
    if not current:
        raise SqlValidationError("Job has no revision to edit")
    config = current.config_json
    merged = JobCreate(
        name=payload.name or job.name,
        description=payload.description if payload.description is not None else job.description,
        tags=payload.tags if payload.tags is not None else (job.tags or []),
        source=payload.source or config["source"],
        destination=payload.destination or config["destination"],
        load=payload.load or config["load"],
        schedule=payload.schedule or config["schedule"],
    )
    validate_job_payload(merged, preview=False)
    if payload.name:
        job.name = payload.name
    if payload.description is not None:
        job.description = payload.description
    if payload.tags is not None:
        job.tags = payload.tags
    revision = _store_revision(db, job, owner_id, merged)
    job.current_revision_id = revision.id
    job.updated_at = utcnow()
    if job.status not in ("draft", "failed_deployment"):
        job.status = "draft"
    audit(db, owner_id, "job", job.id, "edit", {"revision": revision.revision_no})
    db.commit()
    db.refresh(job)
    return job


def enqueue_deploy(db: Session, job: Job, actor_id: str, run_immediately: bool) -> Deployment:
    revision = current_revision(db, job)
    if not revision:
        raise SqlValidationError("Nothing to deploy")
    job.status = "publish_pending"
    job.desired_enabled = True
    deployment = Deployment(
        id=new_id("dep"),
        job_id=job.id,
        revision_id=revision.id,
        state="publish_pending",
        run_immediately=run_immediately,
        trigger_run_id=f"studio_init__{job.id}__{revision.revision_no}" if run_immediately else None,
    )
    db.add(deployment)
    db.add(
        OutboxEvent(
            id=new_id("obx"),
            event_type="deploy_job",
            payload_json={"job_id": job.id, "deployment_id": deployment.id},
        )
    )
    audit(db, actor_id, "job", job.id, "deploy", {"deployment_id": deployment.id})
    db.commit()
    db.refresh(deployment)
    return deployment


def enqueue_simple(db: Session, job: Job, actor_id: str, event_type: str, extra: dict | None = None) -> None:
    db.add(
        OutboxEvent(
            id=new_id("obx"),
            event_type=event_type,
            payload_json={"job_id": job.id, **(extra or {})},
        )
    )
    audit(db, actor_id, "job", job.id, event_type, extra)
    db.commit()


def serialize_job(db: Session, job: Job) -> dict[str, Any]:
    revision = current_revision(db, job)
    config = revision.config_json if revision else None
    last_run = db.scalars(
        select(JobRun).where(JobRun.job_id == job.id).order_by(JobRun.created_at.desc())
    ).first()
    last_dep = db.scalars(
        select(Deployment).where(Deployment.job_id == job.id).order_by(Deployment.created_at.desc())
    ).first()
    dest = (config or {}).get("destination") or {}
    source = (config or {}).get("source") or {}
    schedule = (config or {}).get("schedule") or {}
    return {
        "id": job.id,
        "slug": job.slug,
        "name": job.name,
        "description": job.description,
        "dag_id": job.dag_id,
        "status": job.status,
        "desired_enabled": job.desired_enabled,
        "current_revision": revision.revision_no if revision else None,
        "config": config,
        "last_error": last_dep.last_error if last_dep else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "source_name": source.get("connection_id"),
        "destination_label": f"{dest.get('schema')}.{dest.get('table')}" if dest else None,
        "schedule_label": schedule.get("cron") or "manual",
        "last_run": {
            "state": last_run.state,
            "airflow_run_id": last_run.airflow_run_id,
            "ended_at": last_run.ended_at.isoformat() if last_run.ended_at else None,
            "duration_ms": last_run.duration_ms,
            "rows_written": last_run.rows_written,
        }
        if last_run
        else None,
    }
