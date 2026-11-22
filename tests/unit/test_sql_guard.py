import pytest

from universal_ai_studio.core.security.sql_guard import SqlSafetyError, validate_read_only_sql


def test_accepts_select_on_allowed_table():
    assert validate_read_only_sql("SELECT * FROM sales.orders", {"sales.orders"}) == "SELECT * FROM sales.orders"


@pytest.mark.parametrize("sql", ["DELETE FROM sales.orders", "SELECT * FROM sales.orders; DROP TABLE users", "SELECT * FROM sales.orders -- bypass"])
def test_rejects_unsafe_sql(sql: str):
    with pytest.raises(SqlSafetyError):
        validate_read_only_sql(sql, {"sales.orders"})
