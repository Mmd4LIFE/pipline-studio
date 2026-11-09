from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_editor
from app.db import get_db
from app.errors import AppError
from app.models import ConnectionRef, User
from app.security import utcnow
from app.services.sql_preview import ConnectionFailed, inspect_destination, test_connection

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("")
def list_connections(_: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ConnectionRef).order_by(ConnectionRef.name)).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "airflow_conn_id": row.airflow_conn_id,
            "engine": row.engine,
            "capability": row.capability,
            "allowed_schemas": row.allowed_schemas,
            "enabled": row.enabled,
            "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
            "last_test_ok": row.last_test_ok,
        }
        for row in rows
    ]


@router.post("/{connection_id}/test")
def test_conn(
    connection_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
):
    row = db.scalar(select(ConnectionRef).where(ConnectionRef.airflow_conn_id == connection_id))
    if not row:
        raise AppError("validation_error", "Unknown connection", 404)
    try:
        test_connection(row.airflow_conn_id, "read" if row.capability == "read" else "write")
        row.last_test_ok = True
        row.last_test_error = None
    except Exception as exc:
        row.last_test_ok = False
        row.last_test_error = str(exc)[:500]
        row.last_tested_at = utcnow()
        db.commit()
        raise ConnectionFailed("Connection test failed") from exc
    row.last_tested_at = utcnow()
    db.commit()
    return {"ok": True, "tested_at": row.last_tested_at.isoformat()}


@router.get("/{connection_id}/tables/{schema}/{table}")
def table_columns(
    connection_id: str,
    schema: str,
    table: str,
    _: User = Depends(current_user),
):
    cols = inspect_destination(connection_id, schema, table)
    return [col.model_dump() for col in cols]
