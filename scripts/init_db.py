"""Create the Postgres tables QuizPilot needs. Run once per database.

Reads DATABASE_URL from the environment or from .env, so either works:

    DATABASE_URL=postgresql://... python scripts/init_db.py
    python scripts/init_db.py          # with DATABASE_URL set in .env

LangGraph's checkpointer creates its own tables through setup(); the rate-limit
and session-retention tables come from quizpilot.housekeeping.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quizpilot import housekeeping  # noqa: E402
from quizpilot.checkpointing import configured_dsn, postgres_store  # noqa: E402
from quizpilot.config import load_environment  # noqa: E402


def main() -> int:
    load_environment()
    dsn = configured_dsn()
    if not dsn:
        print(
            "Set DATABASE_URL to your Postgres connection string, "
            "in .env or on the command line.",
            file=sys.stderr,
        )
        return 1
    with postgres_store(dsn) as store:
        store.saver.setup()
        housekeeping.ensure_schema(store.connection)
    print("QuizPilot tables are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
