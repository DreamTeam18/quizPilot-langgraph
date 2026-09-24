"use client";

import { useEffect, useRef, type RefObject } from "react";

export type Pointer = { x: number; y: number };

/**
 * Normalised cursor position (-1 to 1 on both axes), in a ref so that moving
 * the mouse never re-renders React.
 *
 * The listener is on the window rather than on the canvas: the quiz card sits
 * above the scene and would otherwise swallow every move, freezing the
 * parallax exactly where the learner is reading.
 */
export function usePointer(): RefObject<Pointer> {
  const pointer = useRef<Pointer>({ x: 0, y: 0 });

  useEffect(() => {
    const move = (event: PointerEvent) => {
      pointer.current = {
        x: (event.clientX / window.innerWidth) * 2 - 1,
        y: -((event.clientY / window.innerHeight) * 2 - 1),
      };
    };
    // Drift back to centre when the cursor leaves, so the scene settles.
    const recentre = () => {
      pointer.current = { x: 0, y: 0 };
    };

    window.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", recentre);
    window.addEventListener("blur", recentre);
    return () => {
      window.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", recentre);
      window.removeEventListener("blur", recentre);
    };
  }, []);

  return pointer;
}
