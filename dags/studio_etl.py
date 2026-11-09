"""Trusted SQL Pipeline Studio ETL runner.

Airflow tasks import this module. User SQL is treated as data and executed
only as a single read-only SELECT against an approved source connection.
Never put extracted rows into XCom — only lightweight metrics.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from airflow.hooks.base import BaseHook

MANAGED_JOBS_DIR = Path("/opt/airflow/managed-jobs")
IDENTIFIER_RE = r"^[A-Za-z_][A-Za-z0-9_]*$"

logger = logging.getLogger("studio_etl")


def _require_ident(value: str, label: str) -> str:
    import re

    if not isinstance(value, str) or not re.match(IDENTIFIER_RE, value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def load_frozen_spec(job_id: str, revision: int) -> dict[str, Any]:
    path = MANAGED_JOBS_DIR / "revisions" / job_id / f"{revision}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Frozen revision not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def connect_postgres(conn_id: str, application_name: str):
    conn = BaseHook.get_connection(conn_id)
    return psycopg2.connect(
        host=conn.host,
        port=conn.port or 5432,
        dbname=conn.schema,
        user=conn.login,
        password=conn.password,
        connect_timeout=15,
        application_name=application_name[:63],
        options="-c timezone=Asia/Tehran",
    )


def _source_type_to_pg(type_code: int | None) -> str:
    # psycopg2 type codes; fall back to TEXT for unknown types.
    mapping = {
        16: "BOOLEAN",
        20: "BIGINT",
        21: "SMALLINT",
        23: "INTEGER",
        25: "TEXT",
        700: "REAL",
        701: "DOUBLE PRECISION",
        1043: "TEXT",
        1082: "DATE",
        1114: "TIMESTAMP",
        1184: "TIMESTAMPTZ",
        1700: "NUMERIC",
    }
    return mapping.get(type_code or -1, "TEXT")


def extract_and_load(spec: dict[str, Any]) -> dict[str, Any]:
    source_cfg = spec["source"]
    dest_cfg = spec["destination"]
    load_cfg = spec.get("load") or {}
    mapping: dict[str, str] = dest_cfg["column_mapping"]
    source_cols = list(mapping.keys())
    dest_cols = list(mapping.values())

    for name in source_cols + dest_cols:
        _require_ident(name, "column")
    schema = _require_ident(dest_cfg["schema"], "schema")
    table = _require_ident(dest_cfg["table"], "table")

    batch_size = int(load_cfg.get("write_batch_size") or 2000)
    max_rows = int(load_cfg.get("max_rows") or 2_000_000)
    query_timeout = int(load_cfg.get("query_timeout_seconds") or 300)
    sql_text = source_cfg["sql"]

    source = connect_postgres(source_cfg["connection_id"], "studio_etl_source")
    target = connect_postgres(dest_cfg["connection_id"], "studio_etl_dest")
    rows_read = 0
    source_ms = 0
    load_ms = 0
    started = time.monotonic()

    try:
        source.set_session(readonly=True, autocommit=False)
        with source.cursor() as cur:
            cur.execute("SET statement_timeout = %s", (query_timeout * 1000,))
            cur.execute("SET lock_timeout = %s", (15_000,))
            cur.execute("SET TIME ZONE %s", ("Asia/Tehran",))

        dest_has_updated_at = False
        with target.cursor() as dst:
            dst.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (schema, table),
            )
            dest_names = {row[0] for row in dst.fetchall()}
            dest_has_updated_at = "updated_at" in dest_names
            missing = [col for col in dest_cols if col not in dest_names]
            if missing:
                raise ValueError(f"Destination is missing columns: {missing}")

        extract_started = time.monotonic()
        with target:
            with target.cursor() as dst:
                stage_name = sql.Identifier("studio_stage")
                col_defs = sql.SQL(", ").join(
                    sql.SQL("{} TEXT").format(sql.Identifier(col)) for col in dest_cols
                )
                dst.execute(
                    sql.SQL(
                        "CREATE TEMP TABLE {} ({}) ON COMMIT DROP"
                    ).format(stage_name, col_defs)
                )

                with source.cursor(name="studio_extract") as src:
                    src.itersize = batch_size
                    src.execute(sql_text)
                    description = src.description or []
                    desc_by_name = {item.name: item for item in description}
                    missing_src = [col for col in source_cols if col not in desc_by_name]
                    if missing_src:
                        raise ValueError(f"Source query missing columns: {missing_src}")

                    while True:
                        rows = src.fetchmany(batch_size)
                        if not rows:
                            break
                        rows_read += len(rows)
                        if rows_read > max_rows:
                            raise ValueError(f"Source exceeded max_rows={max_rows}")
                        named = []
                        for row in rows:
                            record = {
                                item.name: value
                                for item, value in zip(description, row, strict=True)
                            }
                            named.append(tuple(record[col] for col in source_cols))
                        insert_cols = sql.SQL(", ").join(
                            sql.Identifier(col) for col in dest_cols
                        )
                        execute_values(
                            dst,
                            sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                                stage_name, insert_cols
                            ).as_string(dst),
                            named,
                            page_size=batch_size,
                        )

                source_ms = int((time.monotonic() - extract_started) * 1000)
                load_started = time.monotonic()

                dest_ident = sql.Identifier(schema, table)
                dst.execute(sql.SQL("TRUNCATE TABLE {}").format(dest_ident))

                insert_dest_cols = list(dest_cols)
                select_cols = [sql.Identifier(col) for col in dest_cols]
                if dest_has_updated_at:
                    insert_dest_cols.append("updated_at")
                    select_cols.append(sql.SQL("NOW()"))

                dst.execute(
                    sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                        dest_ident,
                        sql.SQL(", ").join(sql.Identifier(c) for c in insert_dest_cols),
                        sql.SQL(", ").join(select_cols),
                        stage_name,
                    )
                )
                dst.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(dest_ident))
                rows_written = int(dst.fetchone()[0])
                load_ms = int((time.monotonic() - load_started) * 1000)

        metrics = {
            "rows_read": rows_read,
            "rows_written": rows_written,
            "source_query_duration_ms": source_ms,
            "load_duration_ms": load_ms,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "job_revision": spec.get("revision"),
            "status": "success",
        }
        logger.info("STUDIO_METRICS %s", json.dumps(metrics))
        return metrics
    finally:
        source.close()
        target.close()
