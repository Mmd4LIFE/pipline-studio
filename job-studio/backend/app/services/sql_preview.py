from __future__ import annotations

import time
from typing import Any

import psycopg

from app.config import get_settings
from app.schemas.common import ColumnInfo, PreviewResult
from app.services.sql_validator import SqlValidationError, validate_select


class ConnectionFailed(RuntimeError):
    error_type = "connection_failed"


class QueryTimeout(RuntimeError):
    error_type = "query_timeout"


def _pg_type_name(oid: int) -> str:
    mapping = {
        16: "boolean",
        20: "bigint",
        21: "smallint",
        23: "integer",
        25: "text",
        700: "real",
        701: "double precision",
        1043: "text",
        1082: "date",
        1114: "timestamp",
        1184: "timestamptz",
        1700: "numeric",
    }
    return mapping.get(oid, f"oid:{oid}")


def _connect(dsn: str, timeout: int):
    try:
        return psycopg.connect(dsn, connect_timeout=min(timeout, 10), autocommit=False)
    except Exception as exc:
        raise ConnectionFailed("Could not connect to the approved database") from exc


def preview_source(connection_id: str, sql_text: str) -> PreviewResult:
    settings = get_settings()
    validate_select(sql_text)
    try:
        dsn = settings.source_dsn(connection_id)
    except KeyError as exc:
        raise SqlValidationError("Unknown source connection") from exc

    timeout = settings.studio_preview_timeout_seconds
    max_rows = settings.studio_preview_max_rows
    started = time.monotonic()
    conn = _connect(dsn, timeout)
    try:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET TIME ZONE 'Asia/Tehran'")
        conn.execute(f"SET statement_timeout = {int(timeout * 1000)}")
        conn.execute("SET lock_timeout = 5000")
        with conn.cursor() as cur:
            wrapped = (
                "SELECT * FROM (\n"
                + sql_text.rstrip().rstrip(";")
                + "\n) AS studio_preview LIMIT %s"
            )
            try:
                cur.execute(wrapped, (max_rows + 1,))
            except psycopg.errors.QueryCanceled as exc:
                raise QueryTimeout("Source preview exceeded the timeout") from exc
            if getattr(cur, "description", None) is None:
                raise SqlValidationError("Query did not return columns")
            columns = [
                ColumnInfo(name=col.name, type=_pg_type_name(col.type_code or 0))
                for col in cur.description
            ]
            rows = cur.fetchmany(max_rows + 1)
            truncated = len(rows) > max_rows
            rows = rows[:max_rows]
            payload = []
            for row in rows:
                item = {}
                for col, value in zip(columns, row, strict=True):
                    item[col.name] = _jsonable(value)
                payload.append(item)
            duration_ms = int((time.monotonic() - started) * 1000)
            return PreviewResult(
                columns=columns,
                rows=payload,
                row_count=len(payload),
                truncated=truncated,
                duration_ms=duration_ms,
            )
    finally:
        conn.close()


def inspect_destination(connection_id: str, schema: str, table: str) -> list[ColumnInfo]:
    settings = get_settings()
    try:
        dsn = settings.dest_dsn(connection_id)
    except KeyError as exc:
        raise SqlValidationError("Unknown destination connection") from exc
    conn = _connect(dsn, 10)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, table),
            )
            rows = cur.fetchall()
            if not rows:
                raise SqlValidationError(
                    f"Destination table {schema}.{table} was not found"
                )
            return [
                ColumnInfo(
                    name=name,
                    type=dtype,
                    nullable=nullable == "YES",
                    has_default=default is not None,
                )
                for name, dtype, nullable, default in rows
            ]
    finally:
        conn.close()


SKIP_DEST_COLUMNS = {"updated_at"}


def auto_map_columns(source_cols: list[ColumnInfo], dest_cols: list[ColumnInfo], mapping: dict[str, str] | None = None) -> dict[str, str]:
    source_names = {col.name for col in source_cols}
    dest_names = {col.name for col in dest_cols}
    cleaned = {
        src: dst
        for src, dst in (mapping or {}).items()
        if src in source_names and dst in dest_names and dst not in SKIP_DEST_COLUMNS
    }
    mapped_dest = set(cleaned.values())
    for col in source_cols:
        if col.name in dest_names and col.name not in SKIP_DEST_COLUMNS and col.name not in mapped_dest:
            cleaned[col.name] = col.name
            mapped_dest.add(col.name)
    return cleaned


def required_destination_columns(dest_cols: list[ColumnInfo]) -> list[str]:
    return [
        col.name
        for col in dest_cols
        if not col.nullable and not col.has_default and col.name not in SKIP_DEST_COLUMNS
    ]


def validate_mapping(source_cols: list[ColumnInfo], dest_cols: list[ColumnInfo], mapping: dict[str, str]) -> None:
    source_by = {col.name: col for col in source_cols}
    dest_by = {col.name: col for col in dest_cols}
    if not mapping:
        raise SqlValidationError("No query columns match the destination table")
    for src, dst in mapping.items():
        if src not in source_by:
            raise SqlValidationError(
                f"Source column {src} is not in the query result. "
                f"The SELECT returns: {', '.join(source_by)}"
            )
        if dst not in dest_by:
            raise SqlValidationError(f"Destination column {dst} does not exist")
    missing = [name for name in required_destination_columns(dest_cols) if name not in mapping.values()]
    if missing:
        required = required_destination_columns(dest_cols)
        raise SqlValidationError(
            "This query cannot load into the destination table. "
            f"Missing required columns: {', '.join(missing)}. "
            f"Add them to the SELECT. Required: {', '.join(required)}."
        )


def test_connection(connection_id: str, capability: str) -> None:
    settings = get_settings()
    dsn = settings.source_dsn(connection_id) if capability == "read" else settings.dest_dsn(connection_id)
    conn = _connect(dsn, 8)
    try:
        with conn.cursor() as cur:
            if capability == "read":
                cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT 1")
            cur.fetchone()
    finally:
        conn.close()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
