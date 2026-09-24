"use client";

import { useEffect, useState } from "react";

export type SceneProfile = {
  /** False when the browser cannot, or the visitor would rather not, animate. */
  enabled: boolean;
  particles: number;
  detail: number;
  dpr: [number, number];
};

const DISABLED: SceneProfile = { enabled: false, particles: 0, detail: 0, dpr: [1, 1] };

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * Decides whether to render the scene at all, and how heavy it may be.
 * Server-side and on the first paint it stays off, so the markup is identical
 * on both sides and the page is readable before any GPU work happens.
 */
export function useSceneProfile(): SceneProfile {
  const [profile, setProfile] = useState<SceneProfile>(DISABLED);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");

    const evaluate = () => {
      if (motion.matches || !supportsWebGL()) {
        setProfile(DISABLED);
        return;
      }
      const narrow = window.innerWidth < 768;
      setProfile({
        enabled: true,
        particles: narrow ? 1600 : 4200,
        detail: narrow ? 12 : 24,
        dpr: narrow ? [1, 1.5] : [1, 2],
      });
    };

    evaluate();
    motion.addEventListener("change", evaluate);
    window.addEventListener("resize", evaluate);
    return () => {
      motion.removeEventListener("change", evaluate);
      window.removeEventListener("resize", evaluate);
    };
  }, []);

  return profile;
}

/** True while the tab is hidden, so the render loop can be parked. */
export function usePageHidden(): boolean {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    const update = () => setHidden(document.hidden);
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return hidden;
}
