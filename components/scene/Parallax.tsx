"use client";

import { useFrame } from "@react-three/fiber";
import { damp3 } from "maath/easing";
import type { RefObject } from "react";
import type { Pointer } from "./usePointer";

/**
 * Leans the camera toward the cursor and keeps it aimed at the orb.
 *
 * Moving the camera rather than the star field is what makes this read as
 * depth: the particles sit at many distances, so the near ones sweep further
 * than the far ones for free, which is real parallax rather than a pan.
 * At rest the camera returns to its authored position, so the framing the
 * scene was composed around is what a still page shows.
 */
export function Parallax({
  pointer,
  origin,
  strength = 0.55,
}: {
  pointer: RefObject<Pointer>;
  origin: [number, number, number];
  strength?: number;
}) {
  useFrame(({ camera }, delta) => {
    const step = Math.min(delta, 0.05);
    const { x, y } = pointer.current;
    damp3(
      camera.position,
      [origin[0] + x * strength, origin[1] + y * strength * 0.6, origin[2]],
      0.55,
      step,
    );
    // Without this the camera would strafe instead of leaning, and the orb
    // would slide off centre as the cursor moves.
    camera.lookAt(0, 0, 0);
  });

  return null;
}
