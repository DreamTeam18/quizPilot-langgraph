"""The HTTP surface, exercised in demo mode so no model is ever called."""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quizpilot import config
from quizpilot.demo import CARDS

API = Path(__file__).resolve().parents[1] / "api" / "index.py"


def load_api():
    spec = importlib.util.spec_from_file_location("quizpilot_api", API)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api(tmp_path, monkeypatch):
    # api/index.py calls load_environment() at import, and that reads the
    # developer's .env with override=True. Left alone it would undo the deletes
    # below, so these tests would describe whatever happens to be configured on
    # this machine rather than the code. Patch it before the module is loaded.
    monkeypatch.setattr(config, "load_environment", lambda: None)
    for name in ("QUIZPILOT_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "QUIZPILOT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    module = load_api()
    monkeypatch.setattr(module, "DEFAULT_DATABASE", tmp_path / "sessions.sqlite3")
    return module


@pytest.fixture
def client(api):
    with TestClient(api.app) as started:
        yield started


def stream(response) -> list[dict]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def of_type(events, name):
    return [event for event in events if event["type"] == name]


def reference_for(text):
    return next(card.question.reference_answer for card in CARDS if card.question.text == text)


def begin(client, **body):
    payload = {"mode": "demo"}
    payload.update(body)
    events = stream(client.post("/api/session", json=payload))
    return events[0]["sessionId"], events


def test_health_reports_demo_without_a_model(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["demo"] is True
    assert body["live"] is False
    assert body["persistence"] == "sqlite"
    assert "key" not in json.dumps(body).lower()


def test_creating_a_session_streams_to_the_first_question(client):
    session_id, events = begin(client)
    assert len(session_id) == 12
    question = of_type(events, "question")[0]
    assert question["number"] == 1
    assert "rubric" not in json.dumps(events)
    assert "referenceAnswer" not in json.dumps(events)


def test_a_full_demo_quiz_runs_over_http(client):
    session_id, events = begin(client, maxQuestions=2)
    question = of_type(events, "question")[0]["question"]
    for _ in range(2):
        batch = stream(
            client.post(
                f"/api/session/{session_id}/reply",
                json={"kind": "answer", "text": reference_for(question)},
            )
        )
        assert of_type(batch, "feedback")[0]["score"] == 2
        following = of_type(batch, "question")
        if not following:
            assert of_type(batch, "summary")[0]["score"] == 4
            return
        question = following[0]["question"]
    pytest.fail("the quiz never finished")


def test_snapshot_resumes_a_saved_session(client):
    session_id, events = begin(client)
    question = of_type(events, "question")[0]["question"]
    client.post(
        f"/api/session/{session_id}/reply",
        json={"kind": "answer", "text": reference_for(question)},
    )
    body = client.get(f"/api/session/{session_id}").json()
    assert body["sessionId"] == session_id
    assert len(body["results"]) == 1
    assert body["question"]["number"] == 2


def test_hint_is_served_without_advancing(client):
    session_id, events = begin(client)
    first = of_type(events, "question")[0]
    batch = stream(client.post(f"/api/session/{session_id}/reply", json={"kind": "hint"}))
    hinted = of_type(batch, "question")[0]
    assert hinted["question"] == first["question"]
    assert hinted["hint"]


def test_retry_replays_a_waiting_question(client):
    session_id, events = begin(client)
    expected = of_type(events, "question")[0]["question"]
    batch = stream(client.post(f"/api/session/{session_id}/retry", json={}))
    assert of_type(batch, "question")[0]["question"] == expected


def test_unknown_session_is_a_404(client):
    assert client.get("/api/session/deadbeefcafe").status_code == 404


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"mode": "demo", "topic": "Java collections"}, 400),
        ({"mode": "wobble"}, 400),
        ({"mode": "live"}, 400),
        ({"mode": "demo", "maxQuestions": 9}, 422),
    ],
)
def test_bad_settings_fail_before_the_stream_opens(client, body, status):
    response = client.post("/api/session", json=body)
    assert response.status_code == status
    assert not response.headers["content-type"].startswith("text/event-stream")


def test_an_empty_answer_is_rejected(client):
    session_id, _ = begin(client)
    response = client.post(f"/api/session/{session_id}/reply", json={"kind": "answer", "text": " "})
    assert response.status_code == 400
    assert "Enter an answer" in response.json()["detail"]


def test_cleanup_requires_the_cron_secret(api, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    with TestClient(api.app) as client:
        assert client.post("/api/cleanup").status_code == 401
        allowed = client.post("/api/cleanup", headers={"authorization": "Bearer s3cret"})
        assert allowed.status_code == 200
