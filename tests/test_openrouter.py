"""Check the real OpenRouter integration with synthetic HTTP responses."""

import json
import os

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from quizpilot.agents import LiveAgents
from quizpilot.cli import main
from quizpilot.config import configured_model, load_environment, load_notes, validate_live_config
from quizpilot.demo import CARDS
from quizpilot.graph import build_graph
from quizpilot.schemas import initial_state

pytest.importorskip("langchain_openrouter")


@pytest.mark.parametrize(
    "model_id", ["quizpilot/test-model-a:free", "another-publisher/test-model-b:free"]
)
def test_openrouter_uses_env_key_and_one_model_for_all_agents(monkeypatch, tmp_path, model_id):
    test_key = "quizpilot-fake-openrouter-test-key"
    # Isolate variables inserted by dotenv as well as monkeypatch itself.
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QUIZPILOT_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "different-fake-openai-key")
    (tmp_path / ".env").write_text(
        f"QUIZPILOT_MODEL=openrouter:{model_id}\nOPENROUTER_API_KEY={test_key}\n"
    )
    load_environment()
    selected = configured_model()
    validate_live_config(selected)

    question = CARDS[0].question
    replies = iter(
        [
            ("generate_question", {"focus": question.concept}),
            ("read_notes", {}),
            ("Question", question.model_dump()),
            ("grade_answer", {}),
            ("read_notes", {}),
            ("Grade", {"score": 2, "feedback": "Correct.", "missed_concepts": []}),
        ]
    )
    requests = []
    reasoning = [{"type": "reasoning.text", "text": "Synthetic test context.", "index": 0}]

    def fake_send(client, request, **kwargs):
        # Replaces HTTP transport completely: no external requests or real keys.
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == f"Bearer {test_key}"
        payload = json.loads(request.content)
        assert payload["model"] == model_id
        requests.append(payload)
        name, arguments = next(replies)
        assert name in {item["function"]["name"] for item in payload["tools"]}
        return httpx.Response(
            200,
            request=request,
            json={
                "id": f"test-completion-{len(requests)}",
                "created": 0,
                "model": model_id,
                "object": "chat.completion",
                "system_fingerprint": None,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning_details": reasoning,
                            "tool_calls": [
                                {
                                    "id": f"test-call-{len(requests)}",
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    monkeypatch.setattr(httpx.Client, "send", fake_send)
    agents = LiveAgents(selected, load_notes())
    graph = build_graph(agents, InMemorySaver())
    config = {"configurable": {"thread_id": "openrouter-integration"}}
    state = initial_state(
        topic="Python basics", notes=load_notes(), mode="live", model=selected, max_questions=1
    )
    graph.invoke(state, config)
    output = graph.invoke(Command(resume={"kind": "answer", "text": "A mutable list"}), config)

    assert "Score: 2/2" in output["summary"]
    assert len(requests) == 6
    assert requests[1]["tool_choice"] == "auto"
    assert requests[4]["tool_choice"] == "auto"
    # Reasoning context survives the specialist's read_notes tool round trip.
    assert any(message.get("reasoning_details") == reasoning for message in requests[2]["messages"])
    assert test_key not in repr(output)


def test_provider_outage_returns_details_without_hidden_sdk_retries(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUIZPILOT_MODEL", "openrouter:quizpilot/test-model:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter-key")
    attempts = []

    def unavailable(client, request, **kwargs):
        attempts.append(request)
        # If retry configuration regresses, fail on the second attempt instead
        # of letting the SDK's default retry loop hold the test for minutes.
        assert len(attempts) == 1, "Unexpected automatic SDK retry"
        return httpx.Response(
            503,
            request=request,
            json={
                "error": {
                    "code": 503,
                    "message": "Provider returned error",
                    "metadata": {
                        "provider_name": "Test provider",
                        "raw": '{"error":{"message":"Temporarily overloaded"}}',
                    },
                }
            },
        )

    monkeypatch.setattr(httpx.Client, "send", unavailable)
    result = main(["--live", "--database", str(tmp_path / "failed-quiz.db")])
    output = capsys.readouterr()
    assert result == 1
    assert len(attempts) == 1
    assert "HTTP 503" in output.err
    assert "Test provider" in output.err
    assert "Temporarily overloaded" in output.err
    assert "Resume with:" in output.out
