import os
import re
import subprocess
import sys

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from quizpilot.cli import main
from quizpilot.config import load_notes
from quizpilot.demo import CARDS, DemoAgents
from quizpilot.graph import build_graph
from quizpilot.schemas import initial_state


def run_cli(tmp_path, *arguments, answers="", model="openai:test-model"):
    environment = {
        **os.environ,
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "QUIZPILOT_MODEL": model,
    }
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("OPENROUTER_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "quizpilot", "--database", str(tmp_path / "quiz.db"), *arguments],
        input=answers,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=environment,
        timeout=30,
    )


def test_cli_defaults_to_offline_and_resumes_in_another_process(tmp_path):
    first = run_cli(tmp_path, answers="/hint\n/pause\n")
    assert first.returncode == 0, first.stderr
    assert "Offline demo" in first.stdout
    assert "Hint:" in first.stdout
    assert "Reference:" not in first.stdout
    session = re.search(r"Session ([a-f0-9]+)", first.stdout).group(1)
    second = run_cli(tmp_path, "--resume", session, answers="/stop\n")
    assert second.returncode == 0, second.stderr
    assert "Question 1/5" in second.stdout
    assert "Hint:" in second.stdout
    assert "No answers were graded" in second.stdout


def test_cli_completes_quiz_and_trace_hides_current_answer(tmp_path):
    result = run_cli(tmp_path, "--demo", "--questions", "1", "--trace", answers="A mutable list\n")
    assert result.returncode == 0, result.stderr
    assert "[graph] coach" in result.stdout
    assert "[graph] tools" in result.stdout
    assert "Score: 2/2" in result.stdout
    assert "rubric" not in result.stdout


@pytest.mark.parametrize(
    ("model", "key_name"),
    [
        ("openai:test-model", "OPENAI_API_KEY"),
        ("openrouter:quizpilot/test-model:free", "OPENROUTER_API_KEY"),
    ],
)
def test_cli_live_requires_the_selected_providers_key(tmp_path, model, key_name):
    missing_key = run_cli(tmp_path, "--live", model=model)
    assert missing_key.returncode == 1
    assert key_name in missing_key.stderr
    assert not (tmp_path / "quiz.db").exists()


def test_cli_demo_rejects_custom_topic(tmp_path):
    custom = run_cli(tmp_path, "--topic", "History")
    assert custom.returncode == 1
    assert "demo covers Python basics" in custom.stderr


@pytest.mark.parametrize("interruption", [EOFError, KeyboardInterrupt])
def test_live_topic_prompt_can_cancel_without_creating_a_session(
    monkeypatch, tmp_path, capsys, interruption
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUIZPILOT_MODEL", "openrouter:quizpilot/test-model:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter-key")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def cancel(prompt):
        raise interruption

    monkeypatch.setattr("builtins.input", cancel)
    database = tmp_path / "quiz.db"
    assert main(["--live", "--database", str(database)]) == 0
    assert "Quiz cancelled" in capsys.readouterr().out
    assert not database.exists()


def test_cli_unknown_session_has_clear_error(tmp_path):
    result = run_cli(tmp_path, "--resume", "missing")
    assert result.returncode == 1
    assert "No saved sessions" in result.stderr


@pytest.mark.parametrize(
    "arguments", [("--topic", "History"), ("--difficulty", "hard"), ("--questions", "2")]
)
def test_cli_resume_rejects_new_quiz_settings(tmp_path, arguments):
    first = run_cli(tmp_path, answers="/pause\n")
    session = re.search(r"Session ([a-f0-9]+)", first.stdout).group(1)
    resumed = run_cli(tmp_path, "--resume", session, *arguments)
    assert resumed.returncode == 1
    assert "restores saved quiz settings" in resumed.stderr


def test_completed_live_quiz_can_be_reviewed_without_api_key(tmp_path):
    # Populate a live session using a stand-in, never a paid model call.
    config = {"configurable": {"thread_id": "completed"}}
    state = initial_state(
        topic="Python basics",
        notes=load_notes(),
        mode="live",
        model="openai:test-model",
        max_questions=1,
    )
    with SqliteSaver.from_conn_string(str(tmp_path / "quiz.db")) as saver:
        graph = build_graph(DemoAgents(), saver)
        output = graph.invoke(state, config)
        graph.invoke(
            Command(
                resume={"kind": "answer", "text": output["current_question"]["reference_answer"]}
            ),
            config,
        )
    resumed = run_cli(tmp_path, "--resume", "completed", model="")
    assert resumed.returncode == 0, resumed.stderr
    assert "Score: 2/2" in resumed.stdout
    assert "Feedback:" in resumed.stdout
    assert "Your answer >" not in resumed.stdout


def test_live_requires_an_explicit_model_instead_of_a_hardcoded_fallback(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QUIZPILOT_MODEL", raising=False)
    database = tmp_path / "quiz.db"
    assert main(["--live", "--database", str(database)]) == 1
    assert "Set QUIZPILOT_MODEL" in capsys.readouterr().err
    assert not database.exists()


def test_editing_only_env_changes_new_and_resumed_live_quizzes(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    # An old shell export must not shadow the model selected in the project file.
    monkeypatch.setenv("QUIZPILOT_MODEL", "openrouter:quizpilot/stale-export:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "stale-exported-test-key")
    first_model = "openrouter:quizpilot/model-a:free"
    second_model = "openrouter:another-publisher/model-b:free"
    test_key = "fake-file-api-key"
    env_path = tmp_path / ".env"
    env_path.write_text(f"QUIZPILOT_MODEL={first_model}\nOPENROUTER_API_KEY={test_key}\n")
    selected = []

    def agents(model_name, notes):
        selected.append(model_name)
        assert os.environ["OPENROUTER_API_KEY"] == test_key
        return DemoAgents()

    monkeypatch.setattr("quizpilot.cli.LiveAgents", agents)
    answers = iter(
        ["/pause", CARDS[0].question.reference_answer, CARDS[0].question.reference_answer]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    database = str(tmp_path / "quiz.db")
    arguments = ["--live", "--topic", "Python basics", "--questions", "1", "--database", database]
    assert main(arguments) == 0
    output = capsys.readouterr()
    assert f"Model: {first_model}" in output.out
    session = re.search(r"Session ([a-f0-9]+)", output.out).group(1)

    # This is the only configuration edit needed to switch every agent.
    env_path.write_text(env_path.read_text().replace(first_model, second_model))
    assert main(["--resume", session, "--database", database]) == 0
    output = capsys.readouterr()
    assert f"Model: {second_model}" in output.out
    assert first_model not in output.out
    assert "Score: 2/2" in output.out

    assert main(arguments) == 0
    assert "Score: 2/2" in capsys.readouterr().out
    assert selected == [first_model, second_model, second_model]
