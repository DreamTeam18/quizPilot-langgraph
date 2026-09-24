"""Where quiz sessions are stored: a SQLite file locally, Postgres when deployed.

The CLI keeps its single-file database. Serverless hosts have an ephemeral
filesystem, so a deployed QuizPilot needs a network database or every resume
fails. Both paths hand back the same BaseCheckpointSaver to build_graph.
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

# Vercel's Postgres integrations inject their own name; accept the common ones.
DSN_VARIABLES = (
    "QUIZPILOT_DATABASE_URL",
    "DATABASE_URL",
    "POSTGRES_URL",
    "POSTGRES_URL_NON_POOLING",
)


@dataclass(frozen=True)
class Store:
    """The checkpointer, plus the Postgres connection behind it when there is one.

    Auxiliary tables such as the rate-limit counter reuse that connection
    rather than paying for a second round trip on every request.
    """

    saver: BaseCheckpointSaver
    connection: Any | None = None


def configured_dsn() -> str | None:
    for name in DSN_VARIABLES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


@contextmanager
def sqlite_store(path: Path) -> Iterator[Store]:
    from langgraph.checkpoint.sqlite import SqliteSaver

    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), check_same_thread=False) as connection:
        yield Store(SqliteSaver(connection))


@contextmanager
def postgres_store(dsn: str) -> Iterator[Store]:
    """One short-lived connection per request, which is what serverless wants.

    PostgresSaver.from_conn_string is deliberately unused: it pins
    prepare_threshold=0, and server-side prepared statements break against a
    transaction-pooled endpoint such as Neon's -pooler host. A threshold of
    None turns them off and works on pooled and direct endpoints alike.
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise ImportError(f"{exc}. Reinstall the project: pip install -e .") from exc

    with Connection.connect(
        dsn, autocommit=True, prepare_threshold=None, row_factory=dict_row
    ) as connection:
        yield Store(PostgresSaver(connection), connection)


@contextmanager
def open_store(sqlite_path: Path | None = None) -> Iterator[Store]:
    """Postgres when a DSN is configured, otherwise the local SQLite file."""
    dsn = configured_dsn()
    if dsn:
        with postgres_store(dsn) as store:
            yield store
        return
    if sqlite_path is None:
        raise ValueError("Set DATABASE_URL to a Postgres connection string in the environment.")
    with sqlite_store(sqlite_path) as store:
        yield store
