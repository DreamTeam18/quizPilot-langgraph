"use client";

import { useFrame } from "@react-three/fiber";
import { damp, dampC } from "maath/easing";
import { useMemo, useRef } from "react";
import { Color, NormalBlending } from "three";
import type { Visuals } from "@/lib/mood";
import { PARTICLE_FRAGMENT, PARTICLE_VERTEX } from "./shaders";

export function Particles({
  visuals,
  count,
  pixelRatio,
}: {
  visuals: Visuals;
  count: number;
  pixelRatio: number;
}) {
  const elapsed = useRef(0);

  const geometry = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const scales = new Float32Array(count);
    const offsets = new Float32Array(count);
    for (let index = 0; index < count; index += 1) {
      // A shell rather than a ball, so the orb is never hidden behind dust.
      const radius = 3.2 + Math.pow(Math.random(), 0.7) * 7.5;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[index * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[index * 3 + 1] = radius * Math.cos(phi) * 0.55;
      positions[index * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
      scales[index] = 0.35 + Math.random() * 0.9;
      offsets[index] = Math.random() * Math.PI * 2;
    }
    return { positions, scales, offsets };
  }, [count]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSpeed: { value: 0.5 },
      uSize: { value: 3.4 },
      uPixelRatio: { value: pixelRatio },
      uColor: { value: new Color("#3b82f6") },
    }),
    [pixelRatio],
  );

  useFrame((_, delta) => {
    const step = Math.min(delta, 0.05);
    elapsed.current += step;
    uniforms.uTime.value = elapsed.current;
    damp(uniforms.uSpeed, "value", visuals.speed, 0.7, step);
    dampC(uniforms.uColor.value, visuals.colorB, 0.55, step);
  });

  return (
    <points key={count}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[geometry.positions, 3]} />
        <bufferAttribute attach="attributes-aScale" args={[geometry.scales, 1]} />
        <bufferAttribute attach="attributes-aOffset" args={[geometry.offsets, 1]} />
      </bufferGeometry>
      <shaderMaterial
        vertexShader={PARTICLE_VERTEX}
        fragmentShader={PARTICLE_FRAGMENT}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        blending={NormalBlending}
      />
    </points>
  );
}
