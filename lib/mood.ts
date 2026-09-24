import type { Difficulty } from "./types";

/**
 * The scene reacts to the quiz rather than decorating it: difficulty sets the
 * palette, and what the agents are doing sets the motion.
 */
export type Mood = "idle" | "thinking" | "grading" | "correct" | "partial" | "wrong" | "done";

export type Visuals = {
  colorA: string;
  colorB: string;
  turbulence: number;
  speed: number;
  pulse: number;
};

const DIFFICULTY_PALETTE: Record<Difficulty, [string, string]> = {
  easy: ["#22d3ee", "#3b82f6"],
  medium: ["#a78bfa", "#6366f1"],
  hard: ["#f472b6", "#a855f7"],
};

// Grading deepens to a burnt ember rather than brightening, because the base
// palette is already amber and a brighter amber would not register as a change.
// The three verdicts keep their conventional meaning; green and rose both stay
// legible against a warm ground, where a second orange would not.
// The verdicts keep their conventional meaning, and all three read clearly
// against the cool base the difficulty palette sets.
const MOOD_PALETTE: Partial<Record<Mood, [string, string]>> = {
  grading: ["#fbbf24", "#f97316"],
  correct: ["#4ade80", "#10b981"],
  partial: ["#fcd34d", "#f59e0b"],
  wrong: ["#fb7185", "#ef4444"],
};

const MOTION: Record<Mood, { turbulence: number; speed: number; pulse: number }> = {
  idle: { turbulence: 0.1, speed: 0.45, pulse: 0 },
  thinking: { turbulence: 0.85, speed: 2.4, pulse: 0.15 },
  grading: { turbulence: 0.6, speed: 1.7, pulse: 0.1 },
  correct: { turbulence: 0.38, speed: 1.1, pulse: 1 },
  partial: { turbulence: 0.34, speed: 0.95, pulse: 0.6 },
  wrong: { turbulence: 0.3, speed: 0.85, pulse: 0.8 },
  done: { turbulence: 0.16, speed: 0.6, pulse: 0.2 },
};

export function visualsFor(mood: Mood, difficulty: Difficulty, energy: number): Visuals {
  const [colorA, colorB] = MOOD_PALETTE[mood] ?? DIFFICULTY_PALETTE[difficulty];
  const motion = MOTION[mood];
  return {
    colorA,
    colorB,
    // A strong run makes the orb a little livelier without changing its colour.
    turbulence: motion.turbulence + energy * 0.08,
    speed: motion.speed + energy * 0.25,
    pulse: motion.pulse,
  };
}

/** Tint for the CSS backdrop, which is all that shows under reduced motion. */
export const MOOD_TINT: Record<Mood, string> = {
  idle: "#dbeafe",
  thinking: "#ddd6fe",
  grading: "#fef3c7",
  correct: "#bbf7d0",
  partial: "#fef08a",
  wrong: "#fecdd3",
  done: "#e0e7ff",
};
