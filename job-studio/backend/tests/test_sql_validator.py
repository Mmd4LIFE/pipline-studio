import pytest

from app.services.sql_validator import SqlValidationError, format_sql, validate_select

GOOD_SQL = """
SELECT
    u.id,
    u.first_name,
    CAST(ms.created_at AS DATE) AS date_day,
    COUNT(ms.id) AS match_count,
    MIN(ms.place) AS min_place
FROM users AS u
JOIN match_seats AS ms
    ON ms.user_id = u.id
GROUP BY
    u.id,
    u.first_name,
    CAST(ms.created_at AS DATE)
"""


def test_accepts_single_select():
    root = validate_select(GOOD_SQL)
    assert root is not None
    formatted = format_sql(GOOD_SQL)
    assert "SELECT" in formatted.upper()


def test_accepts_with_select():
    validate_select("WITH x AS (SELECT 1 AS id) SELECT id FROM x")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM users",
        "INSERT INTO users SELECT 1",
        "UPDATE users SET first_name = 'x'",
        "DROP TABLE users",
        "SELECT 1; SELECT 2",
        "SELECT * INTO tmp FROM users",
        "SELECT pg_sleep(1)",
        "SELECT * FROM users; DELETE FROM users",
        "CREATE TABLE x (id int)",
        "COPY users TO STDOUT",
    ],
)
def test_rejects_unsafe_sql(sql: str):
    with pytest.raises(SqlValidationError):
        validate_select(sql)
