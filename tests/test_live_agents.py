"""Exercise the real model/tool plumbing with a scripted model and no API calls."""

import json
import re
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import Field

from quizpilot.agents import LiveAgents
from quizpilot.cli import main
from quizpilot.config import load_notes
from quizpilot.demo import CARDS
from quizpilot.graph import build_graph
from quizpilot.schemas import Question, initial_state


class ScriptedModel(BaseChatModel):
    bound_names: list[str] = Field(default_factory=list)
    calls: list[dict[str, Any]] = Field(default_factory=list)
    question: Question = Field(default_factory=lambda: CARDS[0].question.model_copy(deep=True))

    @property
    def _llm_type(self):
        return "quizpilot-scripted-test-model"

    def bind_tools(self, tools, **kwargs):
        names = [convert_to_openai_tool(item)["function"]["name"] for item in tools]
        return self.model_copy(update={"bound_names": names})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append({"tools": self.bound_names, "messages": messages})
        if "generate_question" in self.bound_names:
            name, arguments = "generate_question", {"focus": self.question.concept}
        elif "grade_answer" in self.bound_names:
            name, arguments = "grade_answer", {}
        elif not any(
            isinstance(item, ToolMessage) and item.name == "read_notes" for item in messages
        ):
            name, arguments = "read_notes", {}
        elif "Question" in self.bound_names:
            name, arguments = "Question", self.question.model_dump()
        else:
            name, arguments = (
                "Grade",
                {"score": 2, "feedback": "Correct.", "missed_concepts": []},
            )
        message = AIMessage(
            content="",
            tool_calls=[{"id": uuid4().hex, "name": name, "args": arguments}],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_live_specialists_call_notes_and_return_structured_results():
    model = ScriptedModel()
    agents = LiveAgents("test-model", load_notes(), model=model)
    graph = build_graph(agents, InMemorySaver())
    config = {"configurable": {"thread_id": "live-plumbing"}}
    state = initial_state(
        topic="Python basics", notes=load_notes(), mode="live", model="test-model", max_questions=1
    )
    output = graph.invoke(state, config)
    assert output["__interrupt__"][0].value["question"] == CARDS[0].question.text
    output = graph.invoke(Command(resume={"kind": "answer", "text": "A mutable list"}), config)
    assert "Score: 2/2" in output["summary"]
    assert len(model.calls) == 6  # Two coach calls and two calls per specialist.
    grader_start = next(call for call in model.calls if "Grade" in call["tools"])
    assert len(grader_start["messages"]) == 2  # System + task, no coach history.
    assert any(
        isinstance(message, ToolMessage) and message.name == "read_notes"
        for call in model.calls
        for message in call["messages"]
    )


@pytest.mark.parametrize("target", ["Question", "Grade"])
def test_specialist_recovers_from_text_instead_of_a_structured_tool_call(target):
    class ProseOnceModel(ScriptedModel):
        prose_target: str

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if self.prose_target in self.bound_names and not any(
                call.get("prose_response") for call in self.calls
            ):
                self.calls.append(
                    {"tools": self.bound_names, "messages": messages, "prose_response": True}
                )
                return ChatResult(
                    generations=[
                        ChatGeneration(message=AIMessage(content="I will read the notes."))
                    ]
                )
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = ProseOnceModel(prose_target=target)
    agents = LiveAgents("test-model", load_notes(), model=model)
    graph = build_graph(agents, InMemorySaver())
    config = {"configurable": {"thread_id": "structured-recovery"}}
    state = initial_state(
        topic="Python basics", notes=load_notes(), mode="live", model="test-model", max_questions=1
    )
    graph.invoke(state, config)
    output = graph.invoke(Command(resume={"kind": "answer", "text": "A mutable list"}), config)
    assert "Score: 2/2" in output["summary"]
    assert len(model.calls) == 7


def test_missing_structured_output_stops_after_two_attempts_without_advancing():
    class ProseOnlyModel(ScriptedModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if "Question" in self.bound_names:
                self.calls.append({"tools": self.bound_names, "messages": messages})
                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content="A question in prose."))]
                )
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = ProseOnlyModel()
    agents = LiveAgents("test-model", load_notes(), model=model)
    graph = build_graph(agents, InMemorySaver())
    config = {"configurable": {"thread_id": "structured-failure"}}
    state = initial_state(
        topic="Python basics", notes=load_notes(), mode="live", model="test-model"
    )
    with pytest.raises(RuntimeError, match="after two attempts"):
        graph.invoke(state, config)
    assert len([call for call in model.calls if "Question" in call["tools"]]) == 2
    saved = graph.get_state(config).values
    assert saved["current_question"] is None
    assert saved["results"] == []


@pytest.mark.parametrize(
    ("arguments", "interactive", "topic_reply", "notes_text", "expected_topic"),
    [
        (["--topic", "Java basics"], True, None, None, "Java basics"),
        ([], True, "Java basics", None, "Java basics"),
        (
            ["--notes", "java_notes.md"],
            True,
            "",
            "# Java basics\n## Inheritance\nUse extends to inherit from a class.",
            "Java basics",
        ),
        (
            ["--notes", "java_notes.md"],
            False,
            None,
            "# Java basics\n## Inheritance\nUse extends to inherit from a class.",
            "Java basics",
        ),
        (
            ["--notes", "java_notes.md"],
            False,
            None,
            "## Inheritance\nUse extends to inherit from a class.",
            "java notes",
        ),
    ],
    ids=["topic-flag", "topic-prompt", "notes-prompt", "notes-title", "notes-filename"],
)
def test_custom_topic_reaches_all_agents_and_survives_resume(
    monkeypatch, tmp_path, capsys, arguments, interactive, topic_reply, notes_text, expected_topic
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUIZPILOT_MODEL", "openrouter:quizpilot/test-model:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter-key")
    monkeypatch.setattr("sys.stdin.isatty", lambda: interactive)
    notes_path = tmp_path / "java_notes.md"
    if notes_text is not None:
        notes_path.write_text(notes_text, encoding="utf-8")
    question = Question(
        text="Which Java keyword makes one class inherit from another?",
        concept="Inheritance",
        difficulty="easy",
        reference_answer="extends",
        rubric=["Names the extends keyword."],
        hint="It means making an existing class more specific.",
    )
    model = ScriptedModel(question=question)
    monkeypatch.setattr(
        "quizpilot.cli.LiveAgents",
        lambda model_name, notes: LiveAgents(model_name, notes, model=model),
    )
    replies = iter(([topic_reply] if topic_reply is not None else []) + ["/pause", "extends"])
    prompts = []

    def reply(prompt):
        prompts.append(prompt)
        return next(replies)

    monkeypatch.setattr("builtins.input", reply)
    database = str(tmp_path / "quiz.db")
    assert main(["--live", "--questions", "1", "--database", database, *arguments]) == 0
    output = capsys.readouterr()
    assert f"QuizPilot · {expected_topic} · Session" in output.out
    assert question.text in output.out
    assert "Reference:" not in output.out
    assert ("model's knowledge" in output.out) == (notes_text is None)
    session = re.search(r"Session ([a-f0-9]+)", output.out).group(1)
    with SqliteSaver.from_conn_string(database) as saver:
        saved = saver.get_tuple({"configurable": {"thread_id": session}})
        state = saved.checkpoint["channel_values"]
        assert state["topic"] == expected_topic
        assert state["notes"] == (notes_text or "")

    # Resuming keeps the original lesson even if the input file changes, and
    # goes straight to the pending answer instead of asking for another topic.
    notes_path.write_text("# Different lesson\nUnrelated content.", encoding="utf-8")
    assert main(["--resume", session, "--database", database]) == 0
    output = capsys.readouterr()
    assert f"QuizPilot · {expected_topic} · Session" in output.out
    assert "Score: 2/2" in output.out
    assert sum(prompt.startswith("Quiz topic") for prompt in prompts) == (
        1 if topic_reply is not None else 0
    )
    assert len(model.calls) == 6
    coach_context = json.loads(model.calls[0]["messages"][-1].content)
    assert coach_context["topic"] == expected_topic
    assert coach_context["lesson_concepts"] == (["Inheritance"] if notes_text else [])
    grader_start = next(call for call in model.calls if "Grade" in call["tools"])
    assert json.loads(grader_start["messages"][-1].content)["topic"] == expected_topic
    note_results = [
        message.content
        for call in model.calls
        for message in call["messages"]
        if isinstance(message, ToolMessage) and message.name == "read_notes"
    ]
    assert note_results and all(value == (notes_text or "") for value in note_results)
    assert all(
        "Python basics" not in str(message.content)
        for call in model.calls
        for message in call["messages"]
    )
