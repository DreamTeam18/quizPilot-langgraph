export type Mode = "demo" | "live";
export type Difficulty = "easy" | "medium" | "hard";

export type SessionEvent = {
  type: "session";
  sessionId: string;
  mode: Mode;
  topic: string;
  difficulty: Difficulty;
  total: number;
  hasNotes: boolean;
};

export type PhaseEvent = { type: "phase"; node: string; label: string };

export type QuestionEvent = {
  type: "question";
  number: number;
  total: number;
  question: string;
  difficulty: Difficulty;
  hint: string | null;
  error?: string;
};

export type FeedbackEvent = {
  type: "feedback";
  question: string;
  concept: string;
  score: 0 | 1 | 2;
  feedback: string;
  referenceAnswer: string;
  missedConcepts: string[];
  hintUsed: boolean;
};

export type SummaryEvent = {
  type: "summary";
  summary: string;
  answered: number;
  total: number;
  score: number;
  maxScore: number;
  hintsUsed: number;
  review: string[];
  stopped: boolean;
};

export type ErrorEvent = { type: "error"; message: string; canRetry: boolean };

export type QuizEvent =
  | SessionEvent
  | PhaseEvent
  | QuestionEvent
  | FeedbackEvent
  | SummaryEvent
  | ErrorEvent;

export type Snapshot = {
  sessionId: string;
  mode: Mode;
  topic: string;
  difficulty: Difficulty;
  total: number;
  results: FeedbackEvent[];
  question: QuestionEvent | null;
  summary: SummaryEvent | null;
  canRetry: boolean;
};

export type Health = {
  status: string;
  demo: boolean;
  live: boolean;
  liveError: string | null;
  persistence: "postgres" | "sqlite";
  database: string;
};
