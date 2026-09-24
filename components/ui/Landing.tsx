"use client";

import { useState } from "react";
import type { StartOptions } from "@/lib/store";
import type { Difficulty, Health, Mode } from "@/lib/types";

const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];

export function Landing({
  health,
  busy,
  onStart,
}: {
  health: Health | null;
  busy: boolean;
  onStart: (options: StartOptions) => void;
}) {
  const [mode, setMode] = useState<Mode>("demo");
  const [topic, setTopic] = useState("Python basics");
  const [difficulty, setDifficulty] = useState<Difficulty>("easy");
  const [maxQuestions, setMaxQuestions] = useState(5);

  const liveReady = health?.live ?? false;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    onStart({
      mode,
      topic: mode === "demo" ? "Python basics" : topic,
      difficulty,
      maxQuestions,
    });
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="segmented" role="group" aria-label="Quiz mode">
        <button type="button" aria-pressed={mode === "demo"} onClick={() => setMode("demo")}>
          Demo
        </button>
        <button
          type="button"
          aria-pressed={mode === "live"}
          onClick={() => setMode("live")}
          disabled={!liveReady}
          title={liveReady ? undefined : "This deployment has no model configured."}
        >
          Live
        </button>
      </div>

      <p className="muted">
        {mode === "demo"
          ? "A fixed question bank with semantic grading. No model is called, so it costs nothing."
          : "Agentic coach orchestrator with specialist Question and Grading agents as tools."}
      </p>

      {mode === "live" && (
        <label>
          Topic
          <input
            type="text"
            value={topic}
            maxLength={120}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Java collections"
          />
        </label>
      )}

      <div className="fields">
        <label>
          Starting difficulty
          <select
            value={difficulty}
            onChange={(event) => setDifficulty(event.target.value as Difficulty)}
          >
            {DIFFICULTIES.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
        <label>
          Questions
          <select
            value={maxQuestions}
            onChange={(event) => setMaxQuestions(Number(event.target.value))}
          >
            {[1, 2, 3, 4, 5].map((count) => (
              <option key={count} value={count}>
                {count}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Starting…" : "Begin quiz"}
        </button>
        {mode === "live" && !liveReady && (
          <span className="muted">{health?.liveError ?? "No model is configured."}</span>
        )}
      </div>
    </form>
  );
}
