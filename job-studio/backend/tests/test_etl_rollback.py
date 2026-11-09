from unittest.mock import MagicMock

from app.services.ids import slugify, spec_hash


def test_slugify_and_hash_are_stable():
    assert slugify("Ludo Daily User Stats") == "ludo_daily_user_stats"
    digest = spec_hash({"a": 1, "b": 2})
    assert digest == spec_hash({"b": 2, "a": 1})
    assert len(digest) == 64


def test_failed_load_does_not_commit_destination():
    """The destination transaction must roll back if insert fails mid-load."""
    dest = MagicMock()
    dest.__enter__.return_value = dest
    dest.__exit__.return_value = False
    cursor = MagicMock()
    dest.cursor.return_value.__enter__.return_value = cursor

    try:
        with dest:
            with dest.cursor() as dst:
                dst.execute("TRUNCATE TABLE analytics.daily_user_stats")
                raise RuntimeError("simulated copy failure")
    except RuntimeError:
        pass

    dest.__exit__.assert_called()
    assert dest.__exit__.call_args[0][0] is RuntimeError
