from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import ConnectionRef, User
from app.security import hash_password, utcnow
from app.services.ids import new_id


def seed() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.email == settings.studio_admin_email.lower()))
        if not admin:
            db.add(
                User(
                    id=new_id("usr"),
                    email=settings.studio_admin_email.lower(),
                    password_hash=hash_password(settings.studio_admin_password),
                    role="admin",
                    created_at=utcnow(),
                )
            )
        existing = {row.airflow_conn_id for row in db.scalars(select(ConnectionRef)).all()}
        if "ludo_source" not in existing:
            db.add(
                ConnectionRef(
                    id=new_id("cnn"),
                    name="Ludo PostgreSQL",
                    airflow_conn_id="ludo_source",
                    engine="postgresql",
                    capability="read",
                    allowed_schemas=["public"],
                    enabled=True,
                )
            )
        if "warehouse" not in existing:
            db.add(
                ConnectionRef(
                    id=new_id("cnn"),
                    name="Warehouse PostgreSQL",
                    airflow_conn_id="warehouse",
                    engine="postgresql",
                    capability="write",
                    allowed_schemas=["analytics"],
                    enabled=True,
                )
            )
        db.commit()
    finally:
        db.close()
