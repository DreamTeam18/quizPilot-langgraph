"use client";

import type { FeedbackEvent } from "@/lib/types";
import { ScoreScale, VERDICTS } from "./ScoreScale";
import { Track } from "./Status";

export function FeedbackCard({
  feedback,
  number,
  total,
  hasNext,
  busy,
  onContinue,
}: {
  feedback: FeedbackEvent;
  number: number;
  total: number;
  hasNext: boolean;
  busy: boolean;
  onContinue: () => void;
}) {
  return (
    <section className="panel" aria-live="polite">
      <Track done={number} total={total} />

      <div className="verdict">
        {/* Labelled, because a bare "2/2" next to "Correct" reads as a count
            of questions rather than the 0-1-2 score for this one answer. */}
        <div className="score-block">
          <div
            className="score-ring"
            data-score={feedback.score}
            style={{ "--value": feedback.score / 2 } as React.CSSProperties}
            aria-label={`Scored ${feedback.score} out of 2`}
          >
            <span aria-hidden>{feedback.score}/2</span>
          </div>
          <span className="score-label" aria-hidden>
            score
          </span>
        </div>
        <div>
          <p className="eyebrow">
            Question {number} of {total} · {feedback.concept}
          </p>
          <h2 className="question">{VERDICTS[feedback.score]}</h2>
        </div>
      </div>

      <ScoreScale active={feedback.score} />

      <p className="muted" style={{ color: "var(--ink)", fontSize: "1rem" }}>
        {feedback.feedback}
      </p>

      <dl className="note">
        <dt>Reference answer</dt>
        <dd>{feedback.referenceAnswer}</dd>
      </dl>

      {feedback.missedConcepts.length > 0 && (
        <div>
          <p className="eyebrow">Worth reviewing</p>
          <ul className="tags">
            {feedback.missedConcepts.map((concept) => (
              <li key={concept} className="chip">
                {concept}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="actions">
        {/* The grade now arrives before the next question is written, so
            there is a moment where there is nothing yet to continue to. */}
        <button type="button" className="primary" onClick={onContinue} disabled={busy}>
          {busy ? "Preparing…" : hasNext ? "Next question" : "See your results"}
        </button>
        {feedback.hintUsed && <span className="muted">You used a hint on this one.</span>}
      </div>
    </section>
  );
}
