"""Transport-agnostic quiz sessions: one request advances the graph once.

The CLI drives the graph from a terminal loop that stays open for the whole
quiz. A browser cannot hold that loop, so the same lifecycle is exposed here as
four entry points. Each yields events as the graph runs, which lets an HTTP
layer stream progress instead of blocking silently through several model calls.

Learner-facing payloads are built only from graph.learner_view and the graded
results, so a reference answer or rubric never reaches the client early.
"""

from collections.abc import Iterator
from typing import Any, Literal, cast
from uuid import uuid4

from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from quizpilot.agents import LiveAgents
from quizpilot.config import (
    DEFAULT_TOPIC,
    configured_model,
    load_notes,
    validate_live_config,
)
from quizpilot.demo import DemoAgents
from quizpilot.errors import describe_error
from quizpilot.graph import build_graph, learner_view
from quizpilot.schemas import Difficulty, QuizResult, QuizState, initial_state

MAX_TOPIC_LENGTH = 120
MAX_ANSWER_LENGTH = 4000

COACH_LABEL = "Coach is choosing the next move"
TOOL_LABELS = {
    "generate_question": "Writing your next question",
    "grade_answer": "Grading your answer",
    "give_hint": "Fetching your hint",
}
SUMMARY_LABEL = "Scoring your quiz"


class SessionNotFound(LookupError):
    """No checkpoint exists for the requested session id."""


def new_session_id() -> str:
    return uuid4().hex[:12]


def session_config(session_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": session_id}, "recursion_limit": 64}


def build_for(state: QuizState, saver: BaseCheckpointSaver):
    """Pick the agent suite the way cli.run does: demo offline, live via .env."""
    if state["mode"] == "demo":
        agents: Any = DemoAgents()
    else:
        model = configured_model()
        validate_live_config(model)
        agents = LiveAgents(model, state["notes"])
    return build_graph(agents, saver)


def load_state(saver: BaseCheckpointSaver, session_id: str) -> QuizState:
    saved = saver.get_tuple(session_config(session_id))
    if saved is None:
        raise SessionNotFound(f"No quiz found with session ID {session_id}.")
    return cast(QuizState, saved.checkpoint["channel_values"])


def pending_tool(update: dict[str, Any]) -> str | None:
    """Read the coach's chosen tool so progress can be named before it runs."""
    for message in reversed(update.get("messages") or []):
        if isinstance(message, AIMessage) and len(message.tool_calls) == 1:
            return message.tool_calls[0]["name"]
    return None


def feedback_event(item: dict[str, Any]) -> dict[str, Any]:
    # Mirrors cli.display_feedback: the reference answer is revealed only once
    # the answer has been graded.
    result = QuizResult.model_validate(item)
    return {
        "type": "feedback",
        "question": result.question.text,
        "concept": result.question.concept,
        "score": result.grade.score,
        "feedback": result.grade.feedback,
        "referenceAnswer": result.question.reference_answer,
        "missedConcepts": result.grade.missed_concepts,
        "hintUsed": result.hint_used,
    }


def summary_event(values: QuizState) -> dict[str, Any]:
    results = [QuizResult.model_validate(item) for item in values["results"]]
    review = sorted(
        {
            concept
            for item in results
            if item.grade.score < 2
            for concept in (item.grade.missed_concepts or [item.question.concept])
        }
    )
    return {
        "type": "summary",
        "summary": values["summary"],
        "answered": len(results),
        "total": values["max_questions"],
        "score": sum(item.grade.score for item in results),
        "maxScore": 2 * len(results),
        "hintsUsed": sum(item.hint_used for item in results),
        "review": review,
        "stopped": values["request"] == "stop",
    }


def question_event(view: dict[str, Any]) -> dict[str, Any]:
    return {"type": "question", **view}


def emit_result(graph, config: dict[str, Any], seen: int) -> Iterator[dict[str, Any]]:
    """Report newly graded answers, then whatever the learner must act on next."""
    snapshot = graph.get_state(config)
    values = cast(QuizState, snapshot.values)
    for item in values["results"][seen:]:
        yield feedback_event(item)
    if not snapshot.next:
        yield summary_event(values)
        return
    pending = [value for task in snapshot.tasks for value in task.interrupts]
    if pending:
        yield question_event(pending[0].value)
        return
    # A node stopped mid-flight, typically a model or network failure. The
    # checkpoint is intact, so the turn can be re-driven.
    yield {
        "type": "error",
        "message": "The quiz stopped partway through a turn.",
        "canRetry": True,
    }


def drive(graph, config: dict[str, Any], value: Any, seen: int) -> Iterator[dict[str, Any]]:
    try:
        for update in graph.stream(value, config=config, stream_mode="updates"):
            for node, payload in update.items():
                if node == "coach":
                    yield {"type": "phase", "node": node, "label": COACH_LABEL}
                    name = pending_tool(payload or {})
                    if name:
                        yield {"type": "phase", "node": name, "label": TOOL_LABELS[name]}
                elif node == "summarize":
                    yield {"type": "phase", "node": node, "label": SUMMARY_LABEL}
    except Exception as exc:
        yield {"type": "error", "message": describe_error(exc), "canRetry": True}
        return
    yield from emit_result(graph, config, seen)


def validate_start(
    *,
    mode: str,
    topic: str | None = None,
    difficulty: str = "easy",
) -> tuple[str, str]:
    """Check quiz settings up front. Returns the normalised topic and model.

    An HTTP caller runs this before opening an event stream, so a bad request
    fails with a status code instead of a stream that opens and immediately dies.
    """
    if mode not in ("demo", "live"):
        raise ValueError("Mode must be demo or live.")
    if difficulty not in ("easy", "medium", "hard"):
        raise ValueError("Difficulty must be easy, medium, or hard.")
    topic = (topic or "").strip() or DEFAULT_TOPIC
    if len(topic) > MAX_TOPIC_LENGTH:
        raise ValueError(f"Keep the topic under {MAX_TOPIC_LENGTH} characters.")
    if mode == "demo" and topic.casefold() != DEFAULT_TOPIC.casefold():
        raise ValueError("The demo covers Python basics. Switch to live mode for your own topic.")
    model = ""
    if mode == "live":
        model = configured_model()
        validate_live_config(model)
    return topic, model


def validate_reply(*, kind: str, text: str | None = None) -> dict[str, Any]:
    """Check a learner reply and build the payload graph.await_answer expects."""
    if kind not in ("answer", "hint", "stop"):
        raise ValueError("Reply kind must be answer, hint, or stop.")
    if kind != "answer":
        return {"kind": kind}
    answer = (text or "").strip()
    if not answer:
        raise ValueError("Enter an answer before submitting.")
    if len(answer) > MAX_ANSWER_LENGTH:
        raise ValueError(f"Keep your answer to at most {MAX_ANSWER_LENGTH:,} characters.")
    return {"kind": kind, "text": answer}


def start_session(
    saver: BaseCheckpointSaver,
    *,
    mode: Literal["demo", "live"],
    topic: str | None = None,
    difficulty: Difficulty = "easy",
    max_questions: int = 5,
    session_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Create a quiz and run it up to its first question."""
    topic, model = validate_start(mode=mode, topic=topic, difficulty=difficulty)
    # As in the CLI: the bundled lesson backs Python basics, and any other
    # topic relies on the model's own knowledge.
    notes = load_notes() if topic.casefold() == DEFAULT_TOPIC.casefold() else ""
    state = initial_state(
        topic=topic,
        notes=notes,
        mode=mode,
        model=model,
        difficulty=difficulty,
        max_questions=max_questions,
    )
    session_id = session_id or new_session_id()
    config = session_config(session_id)
    yield {
        "type": "session",
        "sessionId": session_id,
        "mode": mode,
        "topic": state["topic"],
        "difficulty": state["difficulty"],
        "total": state["max_questions"],
        "hasNotes": bool(notes),
    }
    yield from drive(build_for(state, saver), config, state, seen=0)


def reply(
    saver: BaseCheckpointSaver,
    session_id: str,
    *,
    kind: Literal["answer", "hint", "stop"],
    text: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Resume the waiting interrupt with the learner's reply."""
    resume = validate_reply(kind=kind, text=text)
    state = load_state(saver, session_id)
    if state["summary"]:
        raise ValueError("This quiz has already finished.")
    graph = build_for(state, saver)
    config = session_config(session_id)
    yield from drive(graph, config, Command(resume=resume), seen=len(state["results"]))


def retry(saver: BaseCheckpointSaver, session_id: str) -> Iterator[dict[str, Any]]:
    """Re-drive a node that died mid-turn, as cli.run does when resuming."""
    state = load_state(saver, session_id)
    graph = build_for(state, saver)
    config = session_config(session_id)
    snapshot = graph.get_state(config)
    if not snapshot.next:
        yield summary_event(cast(QuizState, snapshot.values))
        return
    if any(task.interrupts for task in snapshot.tasks):
        # Nothing failed; the quiz is simply waiting on the learner.
        yield from emit_result(graph, config, seen=len(state["results"]))
        return
    yield from drive(graph, config, None, seen=len(state["results"]))


def snapshot(saver: BaseCheckpointSaver, session_id: str) -> dict[str, Any]:
    """Everything a reloaded browser needs to rejoin a saved quiz."""
    load_state(saver, session_id)  # Raises SessionNotFound for an unknown id.
    graph = build_graph(DemoAgents(), saver)  # Read-only: no agent ever runs here.
    current = graph.get_state(session_config(session_id))
    values = cast(QuizState, current.values)
    payload: dict[str, Any] = {
        "sessionId": session_id,
        "mode": values["mode"],
        "topic": values["topic"],
        "difficulty": values["difficulty"],
        "total": values["max_questions"],
        "results": [feedback_event(item) for item in values["results"]],
        "question": None,
        "summary": None,
        "canRetry": False,
    }
    if not current.next:
        payload["summary"] = summary_event(values)
        return payload
    pending = [value for task in current.tasks for value in task.interrupts]
    if pending:
        payload["question"] = question_event(pending[0].value)
    elif values["current_question"]:
        payload["question"] = question_event(learner_view(values))
        payload["canRetry"] = True
    else:
        payload["canRetry"] = True
    return payload
