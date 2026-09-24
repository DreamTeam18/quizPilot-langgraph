"""HTTP surface for QuizPilot, served as a single Vercel Python Function.

Routes keep their /api prefix because the rewrite in vercel.json points every
/api/* path at this file while preserving the original URL.

A live turn is several model calls, so mutating routes answer with an event
stream rather than one delayed JSON body: the browser can show which agent is
working, and the connection stays warm through a slow turn. The blocking graph
runs in a worker thread that owns its own database connection, while the
request task emits heartbeats.
"""

import asyncio
import json
import os
import secrets
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

# The package lives in src/ and is not pip-installed inside the function bundle.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from quizpilot import housekeeping, service  # noqa: E402
from quizpilot.checkpointing import configured_dsn, open_store  # noqa: E402
from quizpilot.config import (  # noqa: E402
    DEFAULT_DATABASE,
    load_environment,
    validate_live_config,
)
from quizpilot.errors import describe_error  # noqa: E402

load_environment()

HEARTBEAT_SECONDS = 10.0

app = FastAPI(title="QuizPilot", docs_url=None, redoc_url=None)


def local_database() -> Path | None:
    """No SQLite fallback when deployed: that filesystem does not persist.

    Returning None makes open_store report the missing DATABASE_URL plainly
    instead of failing later on a write that silently disappears.
    """
    return None if os.environ.get("VERCEL") else DEFAULT_DATABASE


class StartRequest(BaseModel):
    mode: str = "demo"
    topic: str | None = None
    difficulty: str = "easy"
    maxQuestions: int = Field(default=5, ge=1, le=5)


class ReplyRequest(BaseModel):
    kind: str
    text: str | None = None


def client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_access(request: Request) -> None:
    """An optional shared code, for when the deployment should not be open."""
    expected = os.environ.get("QUIZPILOT_ACCESS_CODE", "").strip()
    if not expected:
        return
    supplied = request.headers.get("x-quizpilot-access", "")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="This QuizPilot needs an access code.")


def guard(request: Request, limit: housekeeping.Limit) -> None:
    """Count the request before any streaming starts, so a refusal can be a 429."""
    check_access(request)
    with open_store(local_database()) as store:
        try:
            housekeeping.enforce(store.connection, limit, client_id(request))
        except housekeeping.RateLimited as exc:
            raise HTTPException(
                status_code=429,
                detail=str(exc),
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc


def as_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.SessionNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ImportError):
        return HTTPException(
            status_code=500,
            detail=f"Missing model integration: {exc}",
        )
    return HTTPException(status_code=500, detail=describe_error(exc))


async def event_stream(produce: Callable[[], Iterator[dict[str, Any]]]) -> StreamingResponse:
    """Run a blocking event generator in a thread and forward it as SSE."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker() -> None:
        try:
            for event in produce():
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:  # Reported in-band; the session stays saved.
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": describe_error(exc), "canRetry": True},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    async def emit():
        task = loop.run_in_executor(None, worker)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"  # Keeps proxies from closing a slow turn.
                    continue
                if event is None:
                    return
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            await task

    return StreamingResponse(
        emit(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.post("/api/session")
async def create_session(body: StartRequest, request: Request):
    guard(request, housekeeping.NEW_SESSIONS)
    session_id = service.new_session_id()

    def produce() -> Iterator[dict[str, Any]]:
        with open_store(local_database()) as store:
            housekeeping.record_session(store.connection, session_id)
            yield from service.start_session(
                store.saver,
                mode=body.mode,  # type: ignore[arg-type]
                topic=body.topic,
                difficulty=body.difficulty,  # type: ignore[arg-type]
                max_questions=body.maxQuestions,
                session_id=session_id,
            )

    # Surface bad settings as a 4xx instead of a stream that opens and dies.
    try:
        service.validate_start(mode=body.mode, topic=body.topic, difficulty=body.difficulty)
    except Exception as exc:
        raise as_http_error(exc) from exc
    return await event_stream(produce)


@app.post("/api/session/{session_id}/reply")
async def post_reply(session_id: str, body: ReplyRequest, request: Request):
    guard(request, housekeeping.REPLIES)

    def produce() -> Iterator[dict[str, Any]]:
        with open_store(local_database()) as store:
            yield from service.reply(
                store.saver,
                session_id,
                kind=body.kind,  # type: ignore[arg-type]
                text=body.text,
            )

    try:
        service.validate_reply(kind=body.kind, text=body.text)
    except Exception as exc:
        raise as_http_error(exc) from exc
    return await event_stream(produce)


@app.post("/api/session/{session_id}/retry")
async def post_retry(session_id: str, request: Request):
    guard(request, housekeeping.REPLIES)

    def produce() -> Iterator[dict[str, Any]]:
        with open_store(local_database()) as store:
            yield from service.retry(store.saver, session_id)

    return await event_stream(produce)


@app.get("/api/session/{session_id}")
async def get_session(session_id: str, request: Request):
    check_access(request)

    def read() -> dict[str, Any]:
        with open_store(local_database()) as store:
            return service.snapshot(store.saver, session_id)

    try:
        return await asyncio.to_thread(read)
    except Exception as exc:
        raise as_http_error(exc) from exc


@app.get("/api/health")
async def health():
    """Whether live quizzes can run. Never reports the key itself."""
    model = os.environ.get("QUIZPILOT_MODEL", "").strip()
    live_error = ""
    try:
        validate_live_config(model) if model else None
    except Exception as exc:
        live_error = str(exc)

    def database_state() -> str:
        try:
            with open_store(local_database()) as store:
                if store.connection is not None:
                    store.connection.execute("SELECT 1")
                return "ok"
        except Exception as exc:
            return describe_error(exc)

    return {
        "status": "ok",
        "demo": True,
        "live": bool(model) and not live_error,
        "liveError": live_error or None,
        "persistence": "postgres" if configured_dsn() else "sqlite",
        "database": await asyncio.to_thread(database_state),
        "accessCode": bool(os.environ.get("QUIZPILOT_ACCESS_CODE", "").strip()),
    }


@app.api_route("/api/cleanup", methods=["GET", "POST"])
async def cleanup(request: Request):
    """Called by the Vercel cron so old checkpoints do not fill the database."""
    expected = os.environ.get("CRON_SECRET", "").strip()
    if expected and request.headers.get("authorization", "") != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized.")

    def run() -> dict[str, int]:
        with open_store(local_database()) as store:
            return housekeeping.prune(store.connection)

    return await asyncio.to_thread(run)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    error = as_http_error(exc)
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
