"use client";

import { useEffect, useState } from "react";
import { SceneBackdrop } from "@/components/scene/SceneBackdrop";
import { Architecture } from "@/components/ui/Architecture";
import { FeedbackCard } from "@/components/ui/FeedbackCard";
import { Landing } from "@/components/ui/Landing";
import { QuizCard } from "@/components/ui/QuizCard";
import { SummaryCard } from "@/components/ui/SummaryCard";
import { ErrorNotice, PhaseBanner } from "@/components/ui/Status";
import { fetchHealth } from "@/lib/api";
import { energyOf, moodOf, savedSessionId, useQuiz } from "@/lib/store";
import type { Health } from "@/lib/types";

export default function Page() {
  const state = useQuiz();
  const [health, setHealth] = useState<Health | null>(null);
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    void fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    // The web equivalent of `quizpilot --resume`: a reload rejoins the quiz
    // rather than throwing away a half-finished session.
    const saved = savedSessionId();
    if (saved) void useQuiz.getState().resume(saved);
    setRestored(true);
  }, []);

  // Exactly one card shows at a time; progress appears inside its own panel
  // when there is nothing else on screen, and under the card when there is.
  const showingCard = Boolean(state.question ?? state.feedback ?? state.summary);
  const working = state.busy && !showingCard;

  return (
    <>
      <SceneBackdrop
        mood={moodOf(state)}
        difficulty={state.difficulty}
        energy={energyOf(state)}
      />

      <main className="shell">
        <header className="masthead">
          <h1>QuizPilot</h1>
          <p>
            {state.sessionId
              ? `${state.topic} · ${state.mode === "demo" ? "offline demo" : "live agents"}`
              : "Multi-Agent Quiz Orchestration"}
          </p>
        </header>

        {state.error && (
          <div className="notice-slot">
            <ErrorNotice
              message={state.error.message}
              canRetry={state.error.canRetry}
              busy={state.busy}
              onRetry={state.retry}
            />
          </div>
        )}

        {!restored ? null : state.feedback ? (
          <FeedbackCard
            feedback={state.feedback}
            number={state.history.length}
            total={state.total}
            hasNext={Boolean(state.pendingQuestion)}
            onContinue={state.advance}
          />
        ) : state.summary ? (
          <SummaryCard summary={state.summary} onRestart={state.reset} />
        ) : state.question ? (
          <QuizCard
            question={state.question}
            busy={state.busy}
            hinting={state.hinting}
            onSubmit={state.submit}
            onHint={state.hint}
            onStop={state.stop}
          />
        ) : working ? (
          <section className="panel">
            <PhaseBanner label={state.phase ?? "Waking the agents"} />
            <p className="muted">
              A live turn is several model calls, so this can take a moment. The session is
              saved as it goes.
            </p>
          </section>
        ) : (
          <Landing
            health={health}
            busy={state.busy}
            onStart={state.start}
            onAccessCode={state.setAccessCode}
          />
        )}

        {state.sessionId && !state.summary && (
          <p className="footnote">
            Session <code>{state.sessionId}</code> — saved after every answer. Closing this tab
            and returning picks it up where you left off.{" "}
            <button type="button" onClick={state.reset} disabled={state.busy}>
              Abandon it and start fresh
            </button>
          </p>
        )}

        {state.busy && state.phase && showingCard && <PhaseBanner label={state.phase} />}

        <a className="scroll-cue" href="#how-it-works">
          See how it works <span aria-hidden>↓</span>
        </a>
      </main>

      <Architecture />
    </>
  );
}
