from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.security import utcnow


class ConnectionRef(Base):
    __tablename__ = "connection_refs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    airflow_conn_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="postgresql")
    capability: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_schemas: Mapped[list] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
