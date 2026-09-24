"use client";

/** The grader's three outcomes, in score order. */
export const VERDICTS = ["Not quite", "Partly there", "Correct"] as const;

/**
 * The 0-1-2 scale the grader works on, shown wherever a score appears.
 * Passing `active` marks the one an answer actually earned.
 */
export function ScoreScale({ active }: { active?: 0 | 1 | 2 }) {
  return (
    <ul className="scale" aria-label="How each answer is scored">
      {VERDICTS.map((label, value) => (
        <li
          key={label}
          data-score={value}
          data-active={value === active ? "" : undefined}
          aria-current={value === active ? "true" : undefined}
        >
          <span className="scale-value" aria-hidden>
            {value}
          </span>
          {label}
        </li>
      ))}
    </ul>
  );
}
