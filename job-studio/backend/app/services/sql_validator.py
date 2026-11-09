from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

FORBIDDEN_FUNCTIONS = {
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_sleep",
    "dblink",
    "dblink_exec",
    "lo_import",
    "lo_export",
    "lo_get",
    "query_to_xml",
    "pg_execute_server_program",
    "copy_file",
}

FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Grant,
    exp.Set,
    exp.Use,
    exp.Copy,
    exp.Pragma,
)

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SqlValidationError(ValueError):
    error_type = "validation_error"


def validate_select(sql_text: str) -> sqlglot.Expression:
    if not sql_text or not sql_text.strip():
        raise SqlValidationError("SQL is required")
    if "\x00" in sql_text:
        raise SqlValidationError("SQL contains a null byte")

    stripped = sql_text.strip().rstrip(";").strip()
    try:
        statements = sqlglot.parse(stripped, dialect="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SqlValidationError(f"SQL could not be parsed: {exc}") from exc

    statements = [stmt for stmt in statements if stmt is not None]
    if len(statements) != 1:
        raise SqlValidationError("Exactly one SQL statement is allowed")

    root = statements[0]
    if isinstance(root, exp.With):
        if root.this is None or not isinstance(root.this, exp.Select):
            raise SqlValidationError("WITH queries must end in a single SELECT")
    elif not isinstance(root, exp.Select):
        raise SqlValidationError("Only a single SELECT or WITH ... SELECT is allowed")

    if root.find(exp.Into):
        raise SqlValidationError("SELECT INTO is not allowed")
    if root.find(exp.TableSample):
        raise SqlValidationError("TABLESAMPLE is not allowed")

    for node in root.walk():
        if isinstance(node, FORBIDDEN_TYPES):
            raise SqlValidationError(f"{node.__class__.__name__} statements are not allowed")
        if isinstance(node, exp.Anonymous):
            name = (node.this or "").lower()
            if name in FORBIDDEN_FUNCTIONS:
                raise SqlValidationError(f"Function {name} is not allowed")
        if isinstance(node, exp.Func):
            name = node.sql_name().lower() if hasattr(node, "sql_name") else ""
            if name in FORBIDDEN_FUNCTIONS:
                raise SqlValidationError(f"Function {name} is not allowed")

    lowered = stripped.lower()
    for token in (
        " for update",
        " for share",
        " into outfile",
        " pg_sleep",
        " dblink",
        ";--",
    ):
        if token in lowered:
            raise SqlValidationError("SQL contains a disallowed clause")

    return root


def format_sql(sql_text: str) -> str:
    root = validate_select(sql_text)
    return root.sql(dialect="postgres", pretty=True)


def quoted_ident(name: str) -> str:
    if not IDENT_RE.match(name):
        raise SqlValidationError(f"Invalid identifier: {name}")
    return '"' + name.replace('"', '""') + '"'
