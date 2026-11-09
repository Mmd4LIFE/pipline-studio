from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import SessionLocal
from app.services.airflow_client import AirflowClient

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health():
    db_ok = True
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        db_ok = False
    airflow_ok = False
    try:
        airflow_ok = AirflowClient().health()
    except Exception:
        airflow_ok = False
    payload = {"status": "ok" if db_ok else "degraded", "database": db_ok, "airflow": airflow_ok}
    return JSONResponse(payload, status_code=200 if db_ok else 503)
