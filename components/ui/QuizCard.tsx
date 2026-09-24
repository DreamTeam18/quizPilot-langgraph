"use client";

import { useEffect, useRef, useState } from "react";
import type { QuestionEvent } from "@/lib/types";
import { Track } from "./Status";

export function QuizCard({
  question,
  busy,
  hinting,
  onSubmit,
  onHint,
  onStop,
}: {
  question: QuestionEvent;
  busy: boolean;
  hinting: boolean;
  onSubmit: (text: string) => void;
  onHint: () => void;
  onStop: () => void;
}) {
  const [answer, setAnswer] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setAnswer("");
    field.current?.focus();
  }, [question.number, question.question]);

  const ready = answer.trim().length > 0 && !busy;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (ready) onSubmit(answer);
  }

  return (
    <form className="panel" onSubmit={submit}>
      <Track done={question.number - 1} total={question.total} />

      <p className="eyebrow">
        <span>
          Question {question.number} of {question.total}
        </span>
        <span className="chip" data-level={question.difficulty}>
          {question.difficulty}
        </span>
      </p>

      <h2 className="question">{question.question}</h2>

      {question.hint && (
        <dl className="note">
          <dt>Hint</dt>
          <dd>{question.hint}</dd>
        </dl>
      )}

      {question.error && <p className="muted">{question.error}</p>}

      <label>
        Your answer
        <textarea
          ref={field}
          value={answer}
          maxLength={4000}
          disabled={busy}
          placeholder="Answer in your own words — the grader reads for meaning, not exact wording."
          onChange={(event) => setAnswer(event.target.value)}
          onKeyDown={(event) => {
            // Enter inserts a newline; the shortcut mirrors most chat inputs.
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && ready) {
              event.preventDefault();
              onSubmit(answer);
            }
          }}
        />
      </label>

      <div className="actions">
        <button type="submit" className="primary" disabled={!ready}>
          Submit answer
        </button>
        <button
          type="button"
          className="ghost"
          onClick={onHint}
          disabled={busy || Boolean(question.hint)}
        >
          {hinting ? "Fetching…" : question.hint ? "Hint shown" : "Give me a hint"}
        </button>
        <span className="spacer" />
        <button type="button" className="quiet" onClick={onStop} disabled={busy}>
          End quiz
        </button>
      </div>
    </form>
  );
}
