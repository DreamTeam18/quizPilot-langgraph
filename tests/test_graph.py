import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from quizpilot.config import load_notes
from quizpilot.demo import CARDS, DemoAgents
from quizpilot.graph import build_graph
from quizpilot.schemas import Grade, Question, initial_state


class CountingAgents(DemoAgents):
    def __init__(self):
        self.questions = 0
        self.grades = 0

    def generate_question(self, state, focus):
        self.questions += 1
        return super().generate_question(state, focus)

    def grade_answer(self, state):
        self.grades += 1
        return super().grade_answer(state)


@pytest.fixture
def quiz():
    agents = CountingAgents()
    graph = build_graph(agents, InMemorySaver())
    config = {"configurable": {"thread_id": uuid4().hex}, "recursion_limit": 64}
    state = initial_state(topic="Python basics", notes=load_notes(), mode="demo")
    return agents, graph, config, state


def test_five_question_quiz_grades_once_per_answer_and_stops(quiz):
    agents, graph, config, state = quiz
    output = graph.invoke(state, config)
    questions = []
    for number in range(5):
        assert output["__interrupt__"][0].value["number"] == number + 1
        question = Question.model_validate(output["current_question"])
        questions.append(question)
        output = graph.invoke(
            Command(resume={"kind": "answer", "text": question.reference_answer}), config
        )
    assert "__interrupt__" not in output
    assert not graph.get_state(config).next
    assert agents.questions == agents.grades == 5
    assert len({question.text for question in questions}) == 5
    assert [question.difficulty for question in questions] == [
        "easy",
        "medium",
        "hard",
        "hard",
        "hard",
    ]
    assert "Score: 10/10 (100%)" in output["summary"]


def test_hints_keep_question_and_do_not_grade_or_expose_rubric(quiz):
    agents, graph, config, state = quiz
    output = graph.invoke(state, config)
    question = Question.model_validate(output["current_question"])
    before = json.dumps(output["__interrupt__"][0].value)
    assert question.reference_answer not in before
    assert "rubric" not in before and "reference_answer" not in before
    assert output["__interrupt__"][0].value["hint"] is None

    for _ in range(2):
        output = graph.invoke(Command(resume={"kind": "hint"}), config)
    assert output["__interrupt__"][0].value["hint"] == question.hint
    assert output["current_question"] == question.model_dump()
    assert agents.questions == 1 and agents.grades == 0
    assert output["results"] == []

    output = graph.invoke(
        Command(resume={"kind": "answer", "text": question.reference_answer}), config
    )
    assert output["results"][0]["hint_used"] is True
    assert output["hint_used"] is False  # New question starts without a revealed hint.


@pytest.mark.parametrize(
    "reply", [{"kind": "answer", "text": "  "}, {"kind": "unsupported"}, "not a reply"]
)
def test_invalid_answers_interrupt_again_without_model_calls(quiz, reply):
    agents, graph, config, state = quiz
    graph.invoke(state, config)
    output = graph.invoke(Command(resume=reply), config)
    assert output["__interrupt__"][0].value["error"]
    assert agents.questions == 1 and agents.grades == 0
    assert output["results"] == []


def test_stop_without_answer_does_not_grade(quiz):
    agents, graph, config, state = quiz
    graph.invoke(state, config)
    output = graph.invoke(Command(resume={"kind": "stop"}), config)
    assert output["summary"] == "Quiz stopped. No answers were graded."
    assert agents.grades == 0
    assert not graph.get_state(config).next


def test_sqlite_resume_preserves_question_without_regenerating(tmp_path):
    database = str(tmp_path / "quiz.sqlite3")
    config = {"configurable": {"thread_id": "durable"}}
    agents = CountingAgents()
    state = initial_state(topic="Python basics", notes=load_notes(), mode="demo", max_questions=1)
    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_graph(agents, saver)
        output = graph.invoke(state, config)
        question = Question.model_validate(output["current_question"])

    fresh_agents = CountingAgents()
    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_graph(fresh_agents, saver)
        assert graph.get_state(config).values["current_question"] == question.model_dump()
        output = graph.invoke(
            Command(resume={"kind": "answer", "text": question.reference_answer}), config
        )
    assert fresh_agents.questions == 0
    assert fresh_agents.grades == 1
    assert "Score: 2/2" in output["summary"]


def test_failed_grading_can_resume_without_duplicate_question_or_score(quiz):
    agents, graph, config, state = quiz
    output = graph.invoke(state, config)
    question = Question.model_validate(output["current_question"])
    original = agents.grade_answer

    def fail_once(state):
        agents.grade_answer = original
        raise ConnectionError("simulated provider outage")

    agents.grade_answer = fail_once
    with pytest.raises(ConnectionError):
        graph.invoke(Command(resume={"kind": "answer", "text": question.reference_answer}), config)
    assert graph.get_state(config).values["results"] == []
    assert agents.questions == 1
    output = graph.invoke(None, config)
    assert len(output["results"]) == 1
    assert agents.grades == 1
    assert agents.questions == 2


def test_coach_cannot_grade_before_learner_answers(quiz):
    agents, _, config, state = quiz

    def invalid_selection(messages, tools):
        return AIMessage(
            content="",
            tool_calls=[{"id": uuid4().hex, "name": "grade_answer", "args": {}}],
        )

    agents.select_tool = invalid_selection
    graph = build_graph(agents, InMemorySaver())
    with pytest.raises(RuntimeError, match="valid tool"):
        graph.invoke(state, config)
    assert agents.questions == agents.grades == 0


def test_incorrect_and_partial_answers_adjust_difficulty():
    class ScriptedGrades(DemoAgents):
        def __init__(self):
            self.scores = iter([0, 1])

        def grade_answer(self, state):
            return Grade(score=next(self.scores), feedback="Practice this concept.")

    graph = build_graph(ScriptedGrades(), InMemorySaver())
    config = {"configurable": {"thread_id": "difficulty"}}
    state = initial_state(
        topic="Python basics", notes=load_notes(), mode="demo", difficulty="hard", max_questions=2
    )
    graph.invoke(state, config)
    output = graph.invoke(Command(resume={"kind": "answer", "text": "not sure"}), config)
    assert output["difficulty"] == "medium"
    output = graph.invoke(Command(resume={"kind": "answer", "text": "partly correct"}), config)
    assert output["difficulty"] == "medium"
    assert "Score: 1/4" in output["summary"]
    assert "Lists and tuples" in output["summary"]


@pytest.mark.parametrize("entry", CARDS, ids=lambda entry: entry.question.text)
def test_demo_reference_answers_receive_full_credit(entry):
    state = initial_state(topic="Python basics", notes=load_notes(), mode="demo")
    state["current_question"] = entry.question.model_dump()
    state["learner_answer"] = entry.question.reference_answer
    assert DemoAgents().grade_answer(state).score == 2


@pytest.mark.parametrize("limit", [0, 6])
def test_question_limit_is_enforced(limit):
    with pytest.raises(ValueError, match="between 1 and 5"):
        initial_state(topic="Python basics", notes=load_notes(), mode="demo", max_questions=limit)
