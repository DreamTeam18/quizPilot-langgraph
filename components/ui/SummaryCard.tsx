"use client";

import type { SummaryEvent } from "@/lib/types";

export function SummaryCard({
  summary,
  onRestart,
}: {
  summary: SummaryEvent;
  onRestart: () => void;
}) {
  const percent = summary.maxScore
    ? Math.round((summary.score / summary.maxScore) * 100)
    : 0;

  return (
    <section className="panel">
      <p className="eyebrow">{summary.stopped ? "Quiz stopped" : "Quiz complete"}</p>
      <h2 className="question">
        {summary.maxScore
          ? `You scored ${summary.score} of ${summary.maxScore} points.`
          : "No answers were graded."}
      </h2>

      {summary.maxScore > 0 && (
        <>
          {/* Spelled out, because "3 of 6" otherwise reads as a count of
              questions rather than of points. */}
          <p className="muted">
            Each answer scores 0, 1 or 2 — so {summary.answered}{" "}
            {summary.answered === 1 ? "question is" : "questions are"} worth {summary.maxScore}.
          </p>

          <dl className="stats">
            <div className="stat">
              <dt>Score</dt>
              <dd>{percent}%</dd>
            </div>
            <div className="stat">
              <dt>Questions</dt>
              <dd>
                {summary.answered}/{summary.total}
              </dd>
            </div>
            <div className="stat">
              <dt>Hints used</dt>
              <dd>{summary.hintsUsed}</dd>
            </div>
          </dl>
        </>
      )}

      <div>
        <p className="eyebrow">Review next</p>
        {summary.review.length > 0 ? (
          <ul className="tags">
            {summary.review.map((concept) => (
              <li key={concept} className="chip">
                {concept}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Every tested concept was answered correctly.</p>
        )}
      </div>

      <div className="actions">
        <button type="button" className="primary" onClick={onRestart}>
          Start another quiz
        </button>
      </div>
    </section>
  );
}
