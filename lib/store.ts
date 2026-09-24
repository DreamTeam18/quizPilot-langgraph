"use client";

import { create } from "zustand";
import {
  ApiError,
  createSession,
  fetchSnapshot,
  rememberAccessCode,
  retrySession,
  sendReply,
} from "./api";
import type { Mood } from "./mood";
import type {
  Difficulty,
  FeedbackEvent,
  Mode,
  QuestionEvent,
  QuizEvent,
  SummaryEvent,
} from "./types";

const SESSION_KEY = "quizpilot.session";
const FLASH_MILLISECONDS = 2400;

function remember(sessionId: string | null) {
  try {
    if (sessionId) window.localStorage.setItem(SESSION_KEY, sessionId);
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Without site data the quiz still runs; it just cannot be resumed.
  }
}

export function savedSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export type StartOptions = {
  mode: Mode;
  topic: string;
  difficulty: Difficulty;
  maxQuestions: number;
};

type State = {
  sessionId: string | null;
  mode: Mode;
  topic: string;
  difficulty: Difficulty;
  total: number;
  question: QuestionEvent | null;
  feedback: FeedbackEvent | null;
  summary: SummaryEvent | null;
  history: FeedbackEvent[];
  phase: string | null;
  busy: boolean;
  hinting: boolean;
  error: { message: string; canRetry: boolean } | null;
  flash: Mood | null;
  pendingQuestion: QuestionEvent | null;
  pendingSummary: SummaryEvent | null;
  start: (options: StartOptions) => Promise<void>;
  submit: (text: string) => Promise<void>;
  hint: () => Promise<void>;
  stop: () => Promise<void>;
  retry: () => Promise<void>;
  resume: (sessionId: string) => Promise<void>;
  advance: () => void;
  reset: () => void;
  setAccessCode: (code: string) => void;
};

/** Spread on every reset. `history` is rebuilt so no two resets share an array. */
const blankState = () => ({
  ...BLANK,
  history: [] as FeedbackEvent[],
});

const BLANK = {
  sessionId: null,
  mode: "demo" as Mode,
  topic: "Python basics",
  difficulty: "easy" as Difficulty,
  total: 5,
  question: null,
  feedback: null,
  summary: null,
  history: [],
  phase: null,
  busy: false,
  hinting: false,
  error: null,
  flash: null,
  pendingQuestion: null,
  pendingSummary: null,
};

const MOOD_BY_SCORE: Record<number, Mood> = { 0: "wrong", 1: "partial", 2: "correct" };

let flashTimer: ReturnType<typeof setTimeout> | undefined;

export const useQuiz = create<State>((set, get) => {
  function apply(event: QuizEvent) {
    switch (event.type) {
      case "session":
        remember(event.sessionId);
        set({
          sessionId: event.sessionId,
          mode: event.mode,
          topic: event.topic,
          difficulty: event.difficulty,
          total: event.total,
        });
        break;
      case "phase":
        set({ phase: event.label });
        break;
      case "question":
        // A question that arrives alongside feedback waits until the learner
        // has read that feedback and asked to continue.
        if (get().feedback) set({ pendingQuestion: event });
        else set({ question: event, difficulty: event.difficulty, phase: null });
        break;
      case "feedback": {
        clearTimeout(flashTimer);
        const mood = MOOD_BY_SCORE[event.score];
        set((state) => ({
          feedback: event,
          question: null,
          history: [...state.history, event],
          flash: mood,
          phase: null,
        }));
        flashTimer = setTimeout(() => set({ flash: null }), FLASH_MILLISECONDS);
        break;
      }
      case "summary":
        if (get().feedback) set({ pendingSummary: event });
        else set({ summary: event, question: null, phase: null });
        break;
      case "error":
        set({ error: { message: event.message, canRetry: event.canRetry }, phase: null });
        break;
    }
  }

  async function consume(stream: AsyncGenerator<QuizEvent>) {
    set({ busy: true, error: null });
    try {
      for await (const event of stream) apply(event);
    } catch (exc) {
      const message =
        exc instanceof ApiError ? exc.message : "Could not reach QuizPilot. Check your connection.";
      const canRetry = exc instanceof ApiError ? exc.status >= 500 : true;
      set({ error: { message, canRetry: canRetry && Boolean(get().sessionId) } });
    } finally {
      set({ busy: false, hinting: false, phase: null });
    }
  }

  return {
    ...BLANK,

    async start(options) {
      // Drop the stored id first. Otherwise a start that fails leaves the
      // previous session resumable, and the next reload walks back into the
      // old quiz carrying its results.
      remember(null);
      set({
        ...blankState(),
        mode: options.mode,
        topic: options.topic,
        difficulty: options.difficulty,
      });
      await consume(
        createSession({
          mode: options.mode,
          topic: options.topic,
          difficulty: options.difficulty,
          maxQuestions: options.maxQuestions,
        }),
      );
    },

    async submit(text) {
      const { sessionId, busy } = get();
      if (!sessionId || busy) return;
      await consume(sendReply(sessionId, { kind: "answer", text }));
    },

    async hint() {
      const { sessionId, busy } = get();
      if (!sessionId || busy) return;
      set({ hinting: true });
      await consume(sendReply(sessionId, { kind: "hint" }));
    },

    async stop() {
      const { sessionId, busy } = get();
      if (!sessionId || busy) return;
      await consume(sendReply(sessionId, { kind: "stop" }));
    },

    async retry() {
      const { sessionId, busy } = get();
      if (!sessionId || busy) return;
      await consume(retrySession(sessionId));
    },

    async resume(sessionId) {
      set({ ...blankState(), busy: true });
      try {
        const snapshot = await fetchSnapshot(sessionId);
        remember(sessionId);
        set({
          sessionId: snapshot.sessionId,
          mode: snapshot.mode,
          topic: snapshot.topic,
          difficulty: snapshot.difficulty,
          total: snapshot.total,
          history: snapshot.results,
          question: snapshot.question,
          summary: snapshot.summary,
          error: snapshot.canRetry
            ? { message: "This quiz stopped partway through a turn.", canRetry: true }
            : null,
        });
      } catch (exc) {
        remember(null);
        const message = exc instanceof ApiError ? exc.message : "That session could not be loaded.";
        set({ ...blankState(), error: { message, canRetry: false } });
      } finally {
        set({ busy: false });
      }
    },

    advance() {
      const { pendingQuestion, pendingSummary } = get();
      set({
        feedback: null,
        question: pendingQuestion,
        summary: pendingSummary,
        difficulty: pendingQuestion?.difficulty ?? get().difficulty,
        pendingQuestion: null,
        pendingSummary: null,
      });
    },

    reset() {
      clearTimeout(flashTimer);
      remember(null);
      set({ ...blankState() });
    },

    setAccessCode(code) {
      rememberAccessCode(code.trim());
    },
  };
});

/** What the WebGL scene should be doing right now. */
export function moodOf(state: State): Mood {
  if (state.flash) return state.flash;
  if (state.busy) return state.phase?.toLowerCase().includes("grading") ? "grading" : "thinking";
  if (state.summary) return "done";
  return "idle";
}

/** 0–1 across the quiz so far, used to give the scene a sense of momentum. */
export function energyOf(state: State): number {
  if (state.history.length === 0) return 0;
  const scored = state.history.reduce((total, item) => total + item.score, 0);
  return scored / (state.history.length * 2);
}
