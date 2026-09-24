"""Auxiliary Postgres tables a public deployment needs.

A deployed QuizPilot spends the operator's model credits, so it caps how often
one client may start quizzes or submit answers. It also records when each
session was created, so old checkpoints can be dropped instead of filling a
free database tier. Neither concern belongs in the quiz graph, and neither is
enforced locally, where there is no Postgres connection.
"""

import time
from dataclasses import dataclass
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS quizpilot_rate (
    bucket       text   NOT NULL,
    client       text   NOT NULL,
    window_start bigint NOT NULL,
    hits         integer NOT NULL,
    PRIMARY KEY (bucket, client, window_start)
);
CREATE TABLE IF NOT EXISTS quizpilot_session (
    session_id text        PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""

# LangGraph's Postgres checkpointer owns these; they are keyed by thread_id,
# which is the QuizPilot session id.
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


@dataclass(frozen=True)
class Limit:
    bucket: str
    allowance: int
    window_seconds: int


NEW_SESSIONS = Limit("session", allowance=12, window_seconds=3600)
REPLIES = Limit("reply", allowance=60, window_seconds=600)


class RateLimited(Exception):
    def __init__(self, limit: Limit, retry_after: int):
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(f"Too many requests. Try again in {retry_after} seconds.")


def ensure_schema(connection: Any) -> None:
    connection.execute(SCHEMA)


def enforce(connection: Any | None, limit: Limit, client: str) -> None:
    """Count this request in its fixed window and raise once over the allowance."""
    if connection is None:  # Local development has no Postgres to count in.
        return
    now = int(time.time())
    window_start = now - now % limit.window_seconds
    statement = """
        INSERT INTO quizpilot_rate (bucket, client, window_start, hits)
        VALUES (%s, %s, %s, 1)
        ON CONFLICT (bucket, client, window_start)
        DO UPDATE SET hits = quizpilot_rate.hits + 1
        RETURNING hits
    """
    arguments = (limit.bucket, client[:100], window_start)
    try:
        row = connection.execute(statement, arguments).fetchone()
    except Exception:
        # Most likely the table does not exist yet. Create it and count once.
        ensure_schema(connection)
        row = connection.execute(statement, arguments).fetchone()
    hits = row["hits"] if isinstance(row, dict) else row[0]
    if hits > limit.allowance:
        raise RateLimited(limit, retry_after=window_start + limit.window_seconds - now)


def record_session(connection: Any | None, session_id: str) -> None:
    if connection is None:
        return
    try:
        connection.execute(
            "INSERT INTO quizpilot_session (session_id) VALUES (%s) "
            "ON CONFLICT (session_id) DO NOTHING",
            (session_id,),
        )
    except Exception:
        ensure_schema(connection)
        connection.execute(
            "INSERT INTO quizpilot_session (session_id) VALUES (%s) "
            "ON CONFLICT (session_id) DO NOTHING",
            (session_id,),
        )


def prune(connection: Any | None, *, retention_days: int = 7) -> dict[str, int]:
    """Drop checkpoints for sessions older than the retention window."""
    if connection is None:
        return {"sessions": 0}
    ensure_schema(connection)
    expired = [
        row["session_id"] if isinstance(row, dict) else row[0]
        for row in connection.execute(
            "SELECT session_id FROM quizpilot_session "
            "WHERE created_at < now() - make_interval(days => %s)",
            (retention_days,),
        ).fetchall()
    ]
    for table in CHECKPOINT_TABLES:
        for session_id in expired:
            connection.execute(f"DELETE FROM {table} WHERE thread_id = %s", (session_id,))
    connection.execute(
        "DELETE FROM quizpilot_session WHERE created_at < now() - make_interval(days => %s)",
        (retention_days,),
    )
    connection.execute(
        "DELETE FROM quizpilot_rate WHERE window_start < %s",
        (int(time.time()) - 86_400,),
    )
    return {"sessions": len(expired)}
