"""Terminal interface. Displays only deliberate learner-facing projections."""

import argparse
import shlex
import sys
from pathlib import Path
from typing import cast
from uuid import uuid4

from langgraph.types import Command

from quizpilot.agents import LiveAgents
from quizpilot.checkpointing import sqlite_store
from quizpilot.config import (
    DEFAULT_DATABASE,
    DEFAULT_TOPIC,
    configured_model,
    load_environment,
    load_notes,
    topic_from_notes,
    validate_live_config,
)
from quizpilot.demo import DemoAgents
from quizpilot.errors import describe_error
from quizpilot.graph import build_graph
from quizpilot.schemas import QuizResult, QuizState, initial_state


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="QuizPilot — your adaptive quiz coach")
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Offline sample quiz (the default)")
    mode.add_argument("--live", action="store_true", help="Use the LLM configured in .env")
    result.add_argument(
        "--topic", help="Quiz topic (prompted in live mode; default: Python basics)"
    )
    result.add_argument(
        "--notes", type=Path, help="Optional Markdown lesson notes to quiz from (live mode)"
    )
    result.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        help="Starting difficulty (default: easy)",
    )
    result.add_argument(
        "--questions",
        type=int,
        choices=range(1, 6),
        metavar="1..5",
        help="Quiz length (default: 5)",
    )
    result.add_argument("--resume", metavar="SESSION_ID", help="Continue a saved quiz")
    result.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="Session database")
    result.add_argument(
        "--trace", action="store_true", help="Print node names, never private state"
    )
    return result


def read_topic(default: str) -> str | None:
    try:
        return input(f"Quiz topic [{default}] > ").strip() or default
    except (EOFError, KeyboardInterrupt):
        print("\nQuiz cancelled.")
        return None


def read_reply() -> dict | None:
    while True:
        try:
            answer = input("\nYour answer > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer == "/pause":
            return None
        if answer in {"/hint", "/stop"}:
            return {"kind": answer.removeprefix("/")}
        if answer == "/help":
            print("/hint: get a clue · /pause: save and exit · /stop: finish · /help: commands")
        elif answer.startswith("/"):
            print("Unknown command. Type /help for the available commands.")
        elif not answer:
            print("Enter an answer, or type /help for commands.")
        elif len(answer) > 4000:
            print("Please keep your answer to at most 4,000 characters.")
        else:
            return {"kind": "answer", "text": answer}


def display_feedback(item: dict) -> None:
    result = QuizResult.model_validate(item)
    print(f"\nFeedback: {result.grade.score}/2 — {result.grade.feedback}")
    print(f"Reference: {result.question.reference_answer}")


def run(args: argparse.Namespace) -> int:
    load_environment()
    if args.resume and (
        args.live
        or args.demo
        or any(
            value is not None for value in (args.notes, args.topic, args.difficulty, args.questions)
        )
    ):
        raise ValueError(
            "--resume restores saved quiz settings; omit flags that configure a new quiz."
        )
    session_id = args.resume or uuid4().hex[:12]
    resume_arguments = ["quizpilot", "--resume", session_id]
    if args.database != DEFAULT_DATABASE:
        resume_arguments.extend(["--database", str(args.database)])
    resume_command = shlex.join(resume_arguments)
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 64}
    state: QuizState | None = None
    model = ""
    if not args.resume:
        mode = "live" if args.live else "demo"
        if mode == "demo" and (
            args.notes
            or (
                args.topic is not None and args.topic.strip().casefold() != DEFAULT_TOPIC.casefold()
            )
        ):
            raise ValueError("The demo covers Python basics. Use --live for your own topic.")
        model = configured_model() if args.live else ""
        if args.live:
            validate_live_config(model)
        notes = load_notes(args.notes) if args.notes else None
        default_topic = topic_from_notes(notes, args.notes) if args.notes else DEFAULT_TOPIC
        topic = args.topic
        if topic is None:
            topic = read_topic(default_topic) if args.live and sys.stdin.isatty() else default_topic
            if topic is None:
                return 0
        topic = topic.strip()
        if not topic:
            raise ValueError("Choose a nonempty quiz topic.")
        if notes is None:
            notes = load_notes() if topic.casefold() == DEFAULT_TOPIC.casefold() else ""
        state = initial_state(
            topic=topic,
            notes=notes,
            mode=mode,
            model=model,
            difficulty=args.difficulty or "easy",
            max_questions=args.questions if args.questions is not None else 5,
        )
    elif not args.database.is_file():
        raise ValueError(f"No saved sessions found at {args.database}.")

    with sqlite_store(args.database) as store:
        saver = store.saver
        if args.resume:
            saved = saver.get_tuple(config)
            if saved is None:
                raise ValueError(f"No quiz found with session ID {session_id}.")
            state = cast(QuizState, saved.checkpoint["channel_values"])
        assert state is not None
        print(f"\nQuizPilot · {state['topic']} · Session {session_id}")
        # A completed session can be reviewed without a model setting or key.
        if args.resume and state["summary"]:
            if state["results"]:
                display_feedback(state["results"][-1])
            print(f"\n{state['summary']}")
            return 0
        if state["mode"] == "demo":
            print("Offline demo: sample questions and keyword grading; no LLM calls.")
        else:
            if args.resume:
                # Saved model metadata is history, never a configuration source.
                model = configured_model()
                validate_live_config(model)
            print(f"Model: {model}")
            if not state["notes"]:
                print(
                    "Questions use the model's knowledge. Add --notes to quiz from your own lesson."
                )
        agents = DemoAgents() if state["mode"] == "demo" else LiveAgents(model, state["notes"])
        graph = build_graph(agents, saver)
        print("/hint: clue · /pause: save and exit · /stop: finish · /help: commands")

        def advance(value) -> None:
            # Consume updates to drive execution, but never dump their payloads:
            # tool outputs include private rubrics and reference answers.
            for update in graph.stream(value, config=config, stream_mode="updates"):
                if args.trace:
                    for name in update:
                        print(f"[graph] {name}")

        displayed_results = len(state["results"])
        try:
            if not args.resume:
                advance(state)
            else:
                if state["results"]:
                    display_feedback(state["results"][-1])
                snapshot = graph.get_state(config)
                if snapshot.next and not any(task.interrupts for task in snapshot.tasks):
                    # Resume an unfinished node after a model/network error.
                    advance(None)
            while True:
                snapshot = graph.get_state(config)
                for item in snapshot.values["results"][displayed_results:]:
                    display_feedback(item)
                displayed_results = len(snapshot.values["results"])
                if not snapshot.next:
                    print(f"\n{snapshot.values['summary']}")
                    return 0
                pending = [value for task in snapshot.tasks for value in task.interrupts]
                if not pending:
                    raise RuntimeError("The quiz stopped without a learner-input checkpoint.")
                view = pending[0].value
                print(f"\nQuestion {view['number']}/{view['total']} · {view['difficulty']}")
                print(view["question"])
                if view.get("hint"):
                    print(f"Hint: {view['hint']}")
                if view.get("error"):
                    print(view["error"])
                reply = read_reply()
                if reply is None:
                    print(f"\nSaved. Resume with: {resume_command}")
                    return 0
                advance(Command(resume=reply))
        except KeyboardInterrupt:
            print(f"\nSaved progress. Resume with: {resume_command}")
            return 130
        except Exception:
            print(f"\nSession {session_id} saved. Resume with: {resume_command}")
            raise


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return run(args)
    except ImportError as exc:
        print(f"Missing model integration: {exc}", file=sys.stderr)
        print(
            'Install the matching extra, for example: pip install -e ".[openrouter]"',
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"QuizPilot: {describe_error(exc)}", file=sys.stderr)
        return 1
