"use client";

import dynamic from "next/dynamic";
import { MOOD_TINT } from "@/lib/mood";
import type { Mood } from "@/lib/mood";
import type { Difficulty } from "@/lib/types";

// three.js touches window on import, so the scene never renders on the server.
const QuizScene = dynamic(() => import("./QuizScene").then((module) => module.QuizScene), {
  ssr: false,
});

export function SceneBackdrop({
  mood,
  difficulty,
  energy,
}: {
  mood: Mood;
  difficulty: Difficulty;
  energy: number;
}) {
  return (
    <div className="backdrop" style={{ "--tint": MOOD_TINT[mood] } as React.CSSProperties}>
      <QuizScene mood={mood} difficulty={difficulty} energy={energy} />
    </div>
  );
}
