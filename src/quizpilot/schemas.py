"""Validated agent outputs and the shared LangGraph session state."""

from typing import Annotated, Any, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

Difficulty = Literal["easy", "medium", "hard"]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=400)
    concept: str = Field(min_length=1)
    difficulty: Difficulty
    reference_answer: str = Field(min_length=1)
    rubric: list[str] = Field(min_length=1, max_length=5)
    hint: str = Field(min_length=1, description="A useful clue that does not reveal the answer.")


class Grade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: Literal[0, 1, 2] = Field(description="0 = incorrect, 1 = partial, 2 = correct.")
    feedback: str = Field(min_length=1)
    missed_concepts: list[str] = Field(default_factory=list)


class QuizResult(BaseModel):
    question: Question
    answer: str
    grade: Grade
    hint_used: bool


class QuizState(TypedDict):
    topic: str
    notes: str
    mode: Literal["demo", "live"]
    model: str  # Model at session creation, for history only; config selects the live model.
    difficulty: Difficulty
    max_questions: int
    messages: Annotated[list[AnyMessage], add_messages]
    current_question: dict[str, Any] | None
    learner_answer: str | None
    hint_used: bool
    request: Literal["question", "answer", "hint", "stop"]
    results: list[dict[str, Any]]
    next_node: str
    summary: str


def initial_state(
    *,
    topic: str,
    notes: str,
    mode: Literal["demo", "live"],
    model: str = "",
    difficulty: Difficulty = "easy",
    max_questions: int = 5,
) -> QuizState:
    if not 1 <= max_questions <= 5:
        raise ValueError("A quiz must contain between 1 and 5 questions.")
    if difficulty not in ("easy", "medium", "hard"):
        raise ValueError("Difficulty must be easy, medium, or hard.")
    if not topic.strip():
        raise ValueError("A nonempty quiz topic is required.")
    if mode == "demo" and not notes.strip():
        raise ValueError("The demo requires lesson notes.")
    return QuizState(
        topic=topic.strip(),
        notes=notes,
        mode=mode,
        model=model,
        difficulty=difficulty,
        max_questions=max_questions,
        messages=[],
        current_question=None,
        learner_answer=None,
        hint_used=False,
        request="question",
        results=[],
        next_node="coach",
        summary="",
    )
