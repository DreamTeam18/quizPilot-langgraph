"use client";

import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";
import { visualsFor } from "@/lib/mood";
import type { Difficulty } from "@/lib/types";
import type { Mood } from "@/lib/mood";
import { Orb } from "./Orb";
import { Parallax } from "./Parallax";
import { Particles } from "./Particles";
import { usePointer } from "./usePointer";
import { usePageHidden, useSceneProfile } from "./useSceneProfile";

const CAMERA: [number, number, number] = [0, 0, 6.8];

/**
 * The ambient layer. It sits behind every control and is never interactive:
 * all text and inputs live in the DOM above it, so the quiz stays selectable,
 * focusable and readable by a screen reader.
 */
export function QuizScene({
  mood,
  difficulty,
  energy,
}: {
  mood: Mood;
  difficulty: Difficulty;
  energy: number;
}) {
  const profile = useSceneProfile();
  const hidden = usePageHidden();
  const pointer = usePointer();
  const visuals = useMemo(
    () => visualsFor(mood, difficulty, energy),
    [mood, difficulty, energy],
  );

  if (!profile.enabled) {
    // Reduced motion, or no WebGL: the CSS backdrop in globals.css carries the
    // look on its own, tinted to match the current mood.
    return null;
  }

  return (
    <Canvas
      className="scene"
      aria-hidden
      dpr={profile.dpr}
      frameloop={hidden ? "never" : "always"}
      camera={{ position: CAMERA, fov: 40 }}
      // Bloom used to hide the silhouette's stair-stepping; on a pale page it shows.
      gl={{ antialias: true, powerPreference: "high-performance" }}
    >
      <Parallax pointer={pointer} origin={CAMERA} />
      <Orb visuals={visuals} energy={energy} detail={profile.detail} />
      <Particles visuals={visuals} count={profile.particles} pixelRatio={profile.dpr[1]} />
    </Canvas>
  );
}
