"""An offline substitute for the models, using the real graph and tool wrappers.

This is intentionally a fixed question bank with keyword grading, not an LLM.
It is useful for exploring orchestration and persistence without API costs.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import BaseTool

from quizpilot.schemas import Difficulty, Grade, Question, QuizState


@dataclass(frozen=True)
class DemoCard:
    question: Question
    checks: tuple[tuple[str, ...], ...]


def card(
    concept: str,
    difficulty: Difficulty,
    text: str,
    answer: str,
    hint: str,
    checks: tuple[tuple[str, ...], ...],
) -> DemoCard:
    return DemoCard(
        Question(
            text=text,
            concept=concept,
            difficulty=difficulty,
            reference_answer=answer,
            rubric=[answer],
            hint=hint,
        ),
        checks,
    )


CARDS = [
    card(
        "Lists and tuples",
        "easy",
        "Which is mutable in Python: a list or a tuple? What does mutable mean?",
        "A list is mutable: its contents can change after creation.",
        "Think about which collection lets you append a new item.",
        (("list",), ("mutable", "change", "modify")),
    ),
    card(
        "Dictionaries",
        "easy",
        "What does user.get('name') return when 'name' is missing and no default is supplied?",
        "It returns None.",
        "Think of Python's value for the absence of a result.",
        (("none",),),
    ),
    card(
        "Loops",
        "easy",
        "Which three numbers does range(3) produce?",
        "It produces 0, 1, and 2.",
        "Start at zero; the stop value is excluded.",
        (("0",), ("1",), ("2",)),
    ),
    card(
        "Functions",
        "easy",
        "Which statement sends a function's result back to its caller?",
        "The return statement sends the result back to the caller.",
        "Displaying a result on screen is different from sending it to the caller.",
        (("return",),),
    ),
    card(
        "Exceptions",
        "easy",
        "What exception does int('cat') raise?",
        "It raises ValueError because 'cat' is not a valid integer representation.",
        "The argument has an acceptable type, but its contents cannot be converted.",
        (("valueerror", "value error"),),
    ),
    card(
        "Lists and tuples",
        "medium",
        "Why can you reassign an element in a list but not in a tuple?",
        "A list supports changes, whereas a tuple is immutable.",
        "Compare the mutability of the two collection types.",
        (("list",), ("immutable", "cannot change", "can't change")),
    ),
    card(
        "Dictionaries",
        "medium",
        "For a missing key, how do user['name'] and user.get('name', 'Guest') differ?",
        "Square-bracket lookup raises KeyError; get returns the default 'Guest'.",
        "One lookup raises an exception; the other has a fallback value.",
        (("keyerror", "key error"), ("guest", "default")),
    ),
    card(
        "Loops",
        "medium",
        "How do break and continue affect a loop differently?",
        "Break exits the loop; continue skips the rest of the current iteration.",
        "One affects the whole loop; the other affects only the current iteration.",
        (("exit", "exits", "end", "ends", "stop", "stops"), ("skip", "skips")),
    ),
    card(
        "Functions",
        "medium",
        "A function prints a value but has no return statement. What does its caller receive?",
        "The caller receives None.",
        "Printed output and the function's return value are separate.",
        (("none",),),
    ),
    card(
        "Exceptions",
        "medium",
        "Why should you catch a specific expected exception instead of catching every exception?",
        "Catching a specific exception keeps unrelated errors visible instead of hiding them.",
        "Consider what happens to an unexpected programming bug.",
        (("specific", "expected"), ("unrelated", "unexpected", "hiding", "hide")),
    ),
    card(
        "Lists and tuples",
        "hard",
        "Can a list stored inside a tuple change? Explain why.",
        "Yes. The tuple fixes its element references, but the contained list is mutable.",
        "Distinguish changing a tuple element from changing the object it references.",
        (("yes", "can"), ("mutable", "list can change")),
    ),
    card(
        "Dictionaries",
        "hard",
        "Why can't a normal Python list be a dictionary key?",
        "A list is mutable and unhashable; dictionary keys must be hashable.",
        "Dictionary keys need a stable hash, even while the dictionary is in use.",
        (("unhashable", "not hashable"), ("mutable", "change")),
    ),
    card(
        "Loops",
        "hard",
        "A loop visits range(4), uses continue when the value is 1, and otherwise prints it. "
        "Which values are printed?",
        "The printed values are 0, 2, and 3.",
        "Remove the skipped iteration and remember that the stop value is excluded.",
        (("0",), ("2",), ("3",)),
    ),
    card(
        "Functions",
        "hard",
        "Why can a default argument like items=[] retain data between calls? How do you fix it?",
        "Defaults are evaluated once, so the list is shared. "
        "Use None and create a fresh list inside.",
        "Think about when default arguments are evaluated, not when the function is called.",
        (("once", "shared", "reused"), ("none",)),
    ),
    card(
        "Exceptions",
        "hard",
        "Does a finally block execute when the try block returns from a function?",
        "Yes. The finally block executes before control returns to the caller.",
        "Consider when Python runs cleanup as control leaves the try statement.",
        (("yes", "before", "always"), ("finally", "cleanup")),
    ),
]


class DemoAgents:
    def select_tool(self, messages: list[AnyMessage], tools: Sequence[BaseTool]) -> AIMessage:
        name = tools[0].name
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": uuid4().hex,
                    "name": name,
                    "args": {"focus": ""} if name == "generate_question" else {},
                }
            ],
        )

    def generate_question(self, state: QuizState, focus: str) -> Question:
        seen = {item["question"]["text"] for item in state["results"]}
        candidates = [
            item.question
            for item in CARDS
            if item.question.difficulty == state["difficulty"] and item.question.text not in seen
        ]
        if not candidates:
            raise ValueError("The demo question bank is exhausted.")
        weak = {
            concept for item in state["results"] for concept in item["grade"]["missed_concepts"]
        }
        return next(
            (item for item in candidates if item.concept in weak or item.concept == focus),
            candidates[0],
        ).model_copy(deep=True)

    def grade_answer(self, state: QuizState) -> Grade:
        question = Question.model_validate(state["current_question"])
        selected = next(item for item in CARDS if item.question.text == question.text)
        answer = (state["learner_answer"] or "").casefold()
        matches = sum(
            any(re.search(r"\b" + re.escape(term) + r"\b", answer) for term in alternatives)
            for alternatives in selected.checks
        )
        score = 2 if matches == len(selected.checks) else 1 if matches else 0
        return Grade(
            score=score,
            feedback=(
                "The demo matched all expected keywords."
                if score == 2
                else "The demo matched some keywords; compare your answer with the reference."
                if score == 1
                else "The demo did not match the expected keywords. Review the reference answer."
            ),
            missed_concepts=[] if score == 2 else [question.concept],
        )
