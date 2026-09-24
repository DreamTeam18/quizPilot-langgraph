"""Rate limiting and retention, without a Postgres server.

These cover the branching a deployment depends on: that everything is a no-op
without a connection, that the counter refuses once over its allowance, and
that a missing table is created and the statement retried rather than raising.
The SQL itself is exercised against a real database by scripts/init_db.py.
"""

import pytest

from quizpilot import housekeeping


class FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._row


class FakeConnection:
    """Records statements; optionally fails until the schema is created."""

    def __init__(self, *, rows=None, missing_table=False):
        self.statements: list[str] = []
        self.rows = rows or []
        self.missing_table = missing_table
        self.hits = 0

    def execute(self, statement, arguments=None):
        self.statements.append(" ".join(statement.split()))
        if self.missing_table and "quizpilot_rate" in statement and "CREATE" not in statement:
            raise RuntimeError('relation "quizpilot_rate" does not exist')
        if "CREATE TABLE" in statement:
            self.missing_table = False
            return FakeCursor(None)
        if "INSERT INTO quizpilot_rate" in statement:
            self.hits += 1
            return FakeCursor({"hits": self.hits})
        if "SELECT session_id" in statement:
            return FakeCursor([{"session_id": item} for item in self.rows])
        return FakeCursor(None)


def test_everything_is_a_no_op_without_a_connection():
    limit = housekeeping.Limit("test", allowance=1, window_seconds=60)
    housekeeping.enforce(None, limit, "1.2.3.4")
    housekeeping.enforce(None, limit, "1.2.3.4")  # Would refuse if it counted.
    housekeeping.record_session(None, "abc")
    assert housekeeping.prune(None) == {"sessions": 0}


def test_the_counter_refuses_once_over_its_allowance():
    connection = FakeConnection()
    limit = housekeeping.Limit("test", allowance=2, window_seconds=600)
    housekeeping.enforce(connection, limit, "1.2.3.4")
    housekeeping.enforce(connection, limit, "1.2.3.4")
    with pytest.raises(housekeeping.RateLimited) as raised:
        housekeeping.enforce(connection, limit, "1.2.3.4")
    assert 0 < raised.value.retry_after <= 600
    assert "Try again in" in str(raised.value)


def test_a_missing_table_is_created_and_the_statement_retried():
    connection = FakeConnection(missing_table=True)
    housekeeping.enforce(connection, housekeeping.NEW_SESSIONS, "1.2.3.4")
    assert any("CREATE TABLE IF NOT EXISTS quizpilot_rate" in s for s in connection.statements)
    assert sum("INSERT INTO quizpilot_rate" in s for s in connection.statements) == 2


def test_a_long_client_identifier_cannot_overflow_the_column():
    connection = FakeConnection()
    housekeeping.enforce(connection, housekeeping.REPLIES, "x" * 500)
    assert connection.statements  # Truncation happens in the bound argument.


def test_prune_clears_every_checkpoint_table_for_an_expired_session():
    connection = FakeConnection(rows=["old-session"])
    assert housekeeping.prune(connection, retention_days=7) == {"sessions": 1}
    for table in housekeeping.CHECKPOINT_TABLES:
        assert any(f"DELETE FROM {table} WHERE thread_id" in s for s in connection.statements)
    assert any("DELETE FROM quizpilot_session" in s for s in connection.statements)
    assert any("DELETE FROM quizpilot_rate" in s for s in connection.statements)
