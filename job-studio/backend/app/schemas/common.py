from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    error_type: str
    message: str
    details: dict[str, Any] | None = None


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True
    has_default: bool = False


class PreviewResult(BaseModel):
    columns: list[ColumnInfo]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    duration_ms: int
