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
        conn.execute("SET TIME ZONE %s", ("Asia/Tehran",))
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
                SELECT column_name, data_type
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
            return [ColumnInfo(name=name, type=dtype) for name, dtype in rows]
    finally:
        conn.close()


def validate_mapping(source_cols: list[ColumnInfo], dest_cols: list[ColumnInfo], mapping: dict[str, str]) -> None:
    source_by = {col.name: col for col in source_cols}
    dest_by = {col.name: col for col in dest_cols}
    for src, dst in mapping.items():
        if src not in source_by:
            raise SqlValidationError(f"Source column {src} is not in the query result")
        if dst not in dest_by:
            raise SqlValidationError(f"Destination column {dst} does not exist")


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
