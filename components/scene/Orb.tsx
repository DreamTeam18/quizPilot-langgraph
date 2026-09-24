"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { damp, dampC } from "maath/easing";
import { useMemo, useRef } from "react";
import { Color, type Mesh } from "three";
import type { Visuals } from "@/lib/mood";
import { ORB_FRAGMENT, ORB_VERTEX } from "./shaders";

/** How far in front of the camera the orb sits. */
const DEPTH = -2.2;

export function Orb({
  visuals,
  energy,
  detail,
}: {
  visuals: Visuals;
  energy: number;
  detail: number;
}) {
  const mesh = useRef<Mesh>(null);
  const elapsed = useRef(0);

  // Centred on the content column and parked near the top edge, so it crowns
  // the page above the masthead. Both the offset and the radius are fractions
  // of the visible extent, which keeps the orb and the header's top inset in
  // step at any window shape.
  const { position, radius } = useThree((state) => {
    const view = state.viewport.getCurrentViewport(state.camera, [0, 0, DEPTH]);
    return {
      position: [0, view.height * 0.25, DEPTH] as [number, number, number],
      radius: Math.min(Math.max(Math.min(view.width, view.height) * 0.2, 0.85), 1.5),
    };
  });

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uTurbulence: { value: 0.1 },
      uEnergy: { value: 0 },
      uPulse: { value: 0 },
      uColorA: { value: new Color("#22d3ee") },
      uColorB: { value: new Color("#3b82f6") },
    }),
    [],
  );

  useFrame((_, delta) => {
    // A clamped step keeps a backgrounded tab from jumping when it resumes.
    const step = Math.min(delta, 0.05);

    // Integrating time rather than scaling a clock means a change of pace
    // speeds the surface up smoothly instead of snapping it to a new phase.
    elapsed.current += step * (0.45 + uniforms.uTurbulence.value * 1.7);
    uniforms.uTime.value = elapsed.current;

    damp(uniforms.uTurbulence, "value", visuals.turbulence, 0.5, step);
    damp(uniforms.uPulse, "value", visuals.pulse, 0.4, step);
    damp(uniforms.uEnergy, "value", energy, 0.9, step);
    dampC(uniforms.uColorA.value, visuals.colorA, 0.55, step);
    dampC(uniforms.uColorB.value, visuals.colorB, 0.55, step);

    if (mesh.current) {
      mesh.current.rotation.y += step * 0.07 * (0.5 + uniforms.uTurbulence.value);
      mesh.current.rotation.x = Math.sin(elapsed.current * 0.1) * 0.12;
    }
  });

  return (
    <mesh ref={mesh} position={position}>
      <icosahedronGeometry args={[radius, detail]} />
      <shaderMaterial vertexShader={ORB_VERTEX} fragmentShader={ORB_FRAGMENT} uniforms={uniforms} />
    </mesh>
  );
}
