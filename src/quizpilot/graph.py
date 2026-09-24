"""Visible orchestration: coach -> specialist tool -> coach / learner.

LLMs choose question focus and evaluate answers. Python enforces ordering,
score totals, difficulty transitions, and termination. Only await_answer
interrupts, so resuming cannot re-run a question-generation call.
"""

import json
import re
from typing import Any, cast

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from quizpilot.agents import AgentSuite
from quizpilot.schemas import Difficulty, Grade, Question, QuizResult, QuizState

# A short-answer question that points at choices it never supplies cannot be
# answered. Models reach for multiple-choice phrasing even when told not to,
# so the application refuses the question rather than presenting an impossible
# one to the learner.
DANGLING_REFERENCE = re.compile(
    r"\b(?:of the following"
    r"|the following (?:statement|option|choice|answer)s?"
    r"|(?:option|choice|answer)s? (?:below|above)"
    r"|select all that apply)\b",
    re.IGNORECASE,
)


def self_contained(text: str) -> bool:
    """False when a question refers to choices it does not itself carry."""
    return DANGLING_REFERENCE.search(text) is None


def expected_tool(state: QuizState) -> str:
    if state["current_question"] is None:
        return "generate_question"
    if state["request"] == "hint":
        return "give_hint"
    if state["request"] == "answer" and state["learner_answer"]:
        return "grade_answer"
    raise ValueError("The learner must answer or request a hint before a tool can run.")


def specialist_tools(state: QuizState, agents: AgentSuite) -> dict[str, BaseTool]:
    # State is injected through these closures. The coach cannot replace the
    # learner's answer, rubric, score history, or lesson notes via tool arguments.
    @tool
    def generate_question(focus: str) -> dict:
        """Ask the question specialist for a new question on a lesson concept."""
        return agents.generate_question(state, focus).model_dump()

    @tool
    def grade_answer() -> dict:
        """Ask the grading specialist to evaluate the learner's submitted answer."""
        return agents.grade_answer(state).model_dump()

    @tool
    def give_hint() -> dict:
        """Reveal the prepared clue for the current question without grading it."""
        question = Question.model_validate(state["current_question"])
        return {"hint": question.hint}

    return {item.name: item for item in (generate_question, grade_answer, give_hint)}


def next_difficulty(current: Difficulty, score: int) -> Difficulty:
    levels: tuple[Difficulty, ...] = ("easy", "medium", "hard")
    step = {0: -1, 1: 0, 2: 1}[score]
    return levels[max(0, min(2, levels.index(current) + step))]


def learner_view(state: QuizState) -> dict[str, Any]:
    """Explicit projection: never expose the current reference answer or rubric."""
    question = Question.model_validate(state["current_question"])
    return {
        "number": len(state["results"]) + 1,
        "total": state["max_questions"],
        "question": question.text,
        "difficulty": question.difficulty,
        "hint": question.hint if state["hint_used"] else None,
    }


def build_graph(agents: AgentSuite, checkpointer: BaseCheckpointSaver):
    def coach(state: QuizState) -> dict:
        if state["request"] == "stop" or len(state["results"]) >= state["max_questions"]:
            return {"next_node": "summarize"}

        name = expected_tool(state)
        tools = [specialist_tools(state, agents)[name]]
        context = {
            "task": name,
            "topic": state["topic"],
            "difficulty": state["difficulty"],
            "lesson_concepts": [
                line.removeprefix("## ")
                for line in state["notes"].splitlines()
                if line.startswith("## ")
            ],
            "questions_completed": len(state["results"]),
            "weak_concepts": sorted(
                {
                    concept
                    for item in state["results"]
                    for concept in item["grade"]["missed_concepts"]
                }
            ),
        }
        turn_messages = [HumanMessage(content=json.dumps(context))]
        # A model may answer with prose or issue multiple calls. Give it one
        # corrective turn, then fail without changing scores or executing tools.
        for _ in range(2):
            response = agents.select_tool([*state["messages"], *turn_messages], tools)
            turn_messages.append(response)
            if len(response.tool_calls) == 1 and response.tool_calls[0]["name"] == name:
                return {"messages": turn_messages, "next_node": "tools"}
            for call in response.tool_calls:
                turn_messages.append(
                    ToolMessage(
                        content=f"No tool executed. Call {name} exactly once.",
                        tool_call_id=call["id"],
                    )
                )
            turn_messages.append(HumanMessage(content=f"Call {name} exactly once now."))
        raise RuntimeError(
            "The coach could not select a valid tool. Resume the saved quiz to retry."
        )

    def run_tool(state: QuizState) -> dict:
        response = state["messages"][-1]
        if not isinstance(response, AIMessage) or len(response.tool_calls) != 1:
            raise ValueError("Exactly one coach tool call is required.")
        call = response.tool_calls[0]
        name = expected_tool(state)
        if call["name"] != name:
            raise ValueError(f"Only {name} is allowed in this quiz phase.")
        output = specialist_tools(state, agents)[name].invoke(call["args"])
        update: dict[str, Any] = {
            "messages": [
                ToolMessage(content=json.dumps(output), tool_call_id=call["id"], name=name)
            ]
        }
        if name == "generate_question":
            question = Question.model_validate(output)
            if question.difficulty != state["difficulty"]:
                raise ValueError(
                    "The question agent returned the wrong difficulty. Resume to retry."
                )
            if not self_contained(question.text):
                raise ValueError(
                    "The question agent referred to choices it did not supply. "
                    "Resume to retry."
                )
            previous = {item["question"]["text"].casefold().strip() for item in state["results"]}
            if question.text.casefold().strip() in previous:
                raise ValueError("The question agent repeated a question. Resume to retry.")
            update.update(
                current_question=question.model_dump(),
                learner_answer=None,
                hint_used=False,
                next_node="await_answer",
            )
        elif name == "give_hint":
            update.update(hint_used=True, next_node="await_answer")
        else:
            grade = Grade.model_validate(output)
            result = QuizResult(
                question=Question.model_validate(state["current_question"]),
                answer=cast(str, state["learner_answer"]),
                grade=grade,
                hint_used=state["hint_used"],
            )
            update.update(
                results=[*state["results"], result.model_dump()],
                current_question=None,
                learner_answer=None,
                hint_used=False,
                request="question",
                difficulty=next_difficulty(state["difficulty"], grade.score),
                next_node="coach",
            )
        return update

    def await_answer(state: QuizState) -> dict:
        payload = learner_view(state)
        while True:
            reply = interrupt(payload)
            if isinstance(reply, dict):
                kind = reply.get("kind")
                if kind in ("hint", "stop"):
                    return {"request": kind, "learner_answer": None}
                answer = reply.get("text")
                if kind == "answer" and isinstance(answer, str) and 0 < len(answer.strip()) <= 4000:
                    return {"request": "answer", "learner_answer": answer.strip()}
            payload = {
                **payload,
                "error": "Enter an answer (1–4,000 characters), or request a hint.",
            }

    def summarize(state: QuizState) -> dict:
        results = [QuizResult.model_validate(item) for item in state["results"]]
        if not results:
            return {"summary": "Quiz stopped. No answers were graded."}
        score = sum(item.grade.score for item in results)
        maximum = 2 * len(results)
        review = sorted(
            {
                concept
                for item in results
                if item.grade.score < 2
                for concept in (item.grade.missed_concepts or [item.question.concept])
            }
        )
        status = "Quiz stopped" if state["request"] == "stop" else "Quiz complete"
        review_text = ", ".join(review) if review else "all tested concepts answered correctly"
        summary = (
            f"{status}: {len(results)}/{state['max_questions']} questions answered.\n"
            f"Score: {score}/{maximum} ({score / maximum:.0%}).\n"
            f"Questions with hints: {sum(item.hint_used for item in results)}.\n"
            f"Review next: {review_text}."
        )
        return {"summary": summary}

    builder = StateGraph(QuizState)
    builder.add_node("coach", coach)
    builder.add_node("tools", run_tool)
    builder.add_node("await_answer", await_answer)
    builder.add_node("summarize", summarize)
    builder.add_edge(START, "coach")
    builder.add_conditional_edges(
        "coach", lambda state: state["next_node"], {"tools": "tools", "summarize": "summarize"}
    )
    builder.add_conditional_edges(
        "tools",
        lambda state: state["next_node"],
        {"coach": "coach", "await_answer": "await_answer"},
    )
    builder.add_edge("await_answer", "coach")
    builder.add_edge("summarize", END)
    return builder.compile(checkpointer=checkpointer)
