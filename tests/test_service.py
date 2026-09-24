"""The web session service must drive the same quiz without leaking answers."""

import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from quizpilot import service
from quizpilot.demo import CARDS


@pytest.fixture
def saver():
    return InMemorySaver()


def events(iterator):
    return list(iterator)


def of_type(items, name):
    return [item for item in items if item["type"] == name]


def reference_for(text):
    return next(card.question.reference_answer for card in CARDS if card.question.text == text)


def start(saver, **overrides):
    options = {"mode": "demo"}
    options.update(overrides)
    items = events(service.start_session(saver, **options))
    return items[0]["sessionId"], items


def test_start_session_reaches_the_first_question(saver):
    session_id, items = start(saver)
    assert len(session_id) == 12
    question = of_type(items, "question")[0]
    assert question["number"] == 1
    assert question["total"] == 5
    assert question["difficulty"] == "easy"
    assert question["hint"] is None
    assert of_type(items, "phase"), "the client needs progress events to react to"


def test_no_payload_leaks_the_rubric_or_an_ungraded_reference_answer(saver):
    session_id, items = start(saver)
    text = json.dumps(items)
    assert "rubric" not in text
    assert "reference_answer" not in text
    assert "referenceAnswer" not in text
    # Only once an answer is graded does the reference become visible.
    question = of_type(items, "question")[0]["question"]
    graded = events(service.reply(saver, session_id, kind="answer", text="a wrong answer"))
    feedback = of_type(graded, "feedback")[0]
    assert feedback["referenceAnswer"] == reference_for(question)
    assert "rubric" not in json.dumps(graded)


def test_hint_stays_on_the_same_question(saver):
    session_id, items = start(saver)
    first = of_type(items, "question")[0]
    hinted = of_type(events(service.reply(saver, session_id, kind="hint")), "question")[0]
    assert hinted["question"] == first["question"]
    assert hinted["number"] == first["number"]
    assert hinted["hint"]


def test_correct_answers_run_to_a_summary(saver):
    session_id, items = start(saver)
    question = of_type(items, "question")[0]["question"]
    for _ in range(5):
        batch = events(
            service.reply(saver, session_id, kind="answer", text=reference_for(question))
        )
        assert of_type(batch, "feedback")[0]["score"] == 2
        following = of_type(batch, "question")
        if not following:
            summary = of_type(batch, "summary")[0]
            assert summary["answered"] == 5
            assert summary["score"] == summary["maxScore"] == 10
            assert summary["hintsUsed"] == 0
            assert summary["review"] == []
            assert not summary["stopped"]
            return
        question = following[0]["question"]
    pytest.fail("the quiz never finished")


def test_stop_summarises_only_completed_answers(saver):
    session_id, items = start(saver)
    question = of_type(items, "question")[0]["question"]
    events(service.reply(saver, session_id, kind="answer", text=reference_for(question)))
    summary = of_type(events(service.reply(saver, session_id, kind="stop")), "summary")[0]
    assert summary["answered"] == 1
    assert summary["total"] == 5
    assert summary["stopped"]


def test_snapshot_lets_a_reloaded_browser_rejoin(saver):
    session_id, items = start(saver)
    question = of_type(items, "question")[0]["question"]
    events(service.reply(saver, session_id, kind="answer", text=reference_for(question)))
    payload = service.snapshot(saver, session_id)
    assert payload["sessionId"] == session_id
    assert payload["topic"] == "Python basics"
    assert len(payload["results"]) == 1
    assert payload["question"]["number"] == 2
    assert payload["summary"] is None
    assert not payload["canRetry"]


def test_snapshot_of_a_finished_quiz_reports_the_summary(saver):
    session_id, _ = start(saver, max_questions=1)
    payload_question = service.snapshot(saver, session_id)["question"]
    events(
        service.reply(
            saver, session_id, kind="answer", text=reference_for(payload_question["question"])
        )
    )
    payload = service.snapshot(saver, session_id)
    assert payload["question"] is None
    assert payload["summary"]["answered"] == 1


def test_retry_on_a_waiting_quiz_replays_the_question(saver):
    session_id, items = start(saver)
    question = of_type(items, "question")[0]
    replayed = of_type(events(service.retry(saver, session_id)), "question")[0]
    assert replayed["question"] == question["question"]


def test_unknown_session_is_reported_as_missing(saver):
    with pytest.raises(service.SessionNotFound):
        service.snapshot(saver, "deadbeefcafe")


@pytest.mark.parametrize(
    ("kind", "text", "message"),
    [
        ("answer", "   ", "Enter an answer"),
        ("answer", "x" * 4001, "at most"),
        ("shout", None, "answer, hint, or stop"),
    ],
)
def test_invalid_replies_are_rejected(saver, kind, text, message):
    session_id, _ = start(saver)
    with pytest.raises(ValueError, match=message):
        events(service.reply(saver, session_id, kind=kind, text=text))


def test_demo_refuses_a_custom_topic(saver):
    with pytest.raises(ValueError, match="demo covers Python basics"):
        events(service.start_session(saver, mode="demo", topic="Java collections"))


def test_an_overlong_topic_is_rejected(saver):
    with pytest.raises(ValueError, match="under 120 characters"):
        events(service.start_session(saver, mode="live", topic="x" * 121))


def test_the_grade_arrives_before_the_next_question_is_written(saver):
    """A learner should read their score while the next question is drafted."""
    session_id, items = start(saver)
    question = of_type(items, "question")[0]["question"]
    batch = events(service.reply(saver, session_id, kind="answer", text=reference_for(question)))

    kinds = [item["type"] for item in batch]
    labels = [item.get("label") for item in batch]

    feedback_at = kinds.index("feedback")
    writing_at = labels.index("Writing your next question")
    assert feedback_at < writing_at, (
        "the grade must be reported before the coach moves on to the next question"
    )
    # And the question itself still lands after the grade.
    assert feedback_at < kinds.index("question")


def test_a_grade_is_reported_exactly_once(saver):
    session_id, items = start(saver)
    question = of_type(items, "question")[0]["question"]
    batch = events(service.reply(saver, session_id, kind="answer", text=reference_for(question)))
    assert len(of_type(batch, "feedback")) == 1
