import React, { useRef, useMemo, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useQuality } from './QualityContext';

// ─── Coordinate System Notes ──────────────────────────────────────────────
// Ocean plane: position=[0,-2.5,-5], rotation=[-PI/2.05,0,0]
//   The ocean plane is slightly tilted so the displacement in local Z
//   maps to world-Y via the tilt factor: cos(PI/2.05) ≈ 0.0768
//   Effective ocean surface world Y ≈ -2.5 + wave_amplitude * tilt_factor
//
// Ship: position=[5.2,-1.9,-2.5], rotation=[0,-PI/3.4,0]
//   Stern (rear) of the ship in ship's local space is at Z ≈ -4.5
//   After applying yaw -PI/3.4 ≈ -52.9°:
//     stern_world = ship_pos + R_yaw * [0, 0, -4.5]
//     sin(-PI/3.4)≈ -0.836, cos(-PI/3.4)≈ 0.549
//     stern_world_x = 5.2 + (-0.836 * -4.5 * 0 + 0.549 * -4.5... wait sin/cos:
//     dx = sin(yaw) * (-4.5) = -0.836 * (-4.5) = +3.76
//     dz = cos(yaw) * (-4.5) = 0.549 * (-4.5) = -2.47
//     stern_world ≈ [5.2+3.76, -1.9, -2.5-2.47] = [8.96, -1.9, -4.97]
//
// Oil spill sits slightly ABOVE ocean surface at Y = -2.35 (with epsilon clearance)
// and displaces its Y per-vertex matching the ocean wave function.

// ─── Shared Ocean Wave Function (must match Ocean.tsx exactly) ───────────
// This string is injected into both the oil spill vertex shaders so the mesh
// deforms identically to the ocean surface it lies upon.
const OCEAN_WAVE_GLSL = `
  // NOTE: Time is pre-scaled by 0.75 in Ocean.tsx useFrame.
  // We replicate the same scaled time here so oil stays in phase with waves.
  float oceanElevation(vec2 pos, float t) {
    float e = 0.0;
    // Primary swells — matches Ocean.tsx exactly (at 75% time)
    e += sin(pos.x * 0.04 + t * 0.45) * 1.2;
    e += cos(pos.y * 0.05 + t * 0.50) * 0.9;
    // Secondary cross-swell
    e += sin((pos.x * 0.55 + pos.y * 0.32) * 0.13 + t * 0.85) * 0.45;
    e += cos((pos.x * -0.38 + pos.y * 0.72) * 0.16 + t * 0.95) * 0.38;
    // Medium chop
    e += sin((pos.x * 0.7 - pos.y * 0.45) * 0.28 + t * 1.3) * 0.18;
    e += cos((pos.x * 0.28 + pos.y * 0.85) * 0.35 + t * 1.55) * 0.14;
    return e * 0.42;
  }

  // Ocean plane: position=[0,-2.5,-5], rotation=[-PI/2+0.03, 0, 0]
  // The plane is nearly horizontal (only 0.03 rad tilt from flat).
  // Displacement in local Z maps to world Y via cos(PI/2 - 0.03) = sin(0.03) ≈ 0.03
  // So world delta Y from elevation ≈ elev * 0.03 (very small vertical shift).
  // The dominant contribution to visual wave height actually comes from the
  // viewer perspective, not world-Y. Oil sits at a fixed slightly-above-water Y.
  float worldYFromOcean(vec2 worldXZ, float t) {
    vec2 oceanLocal = worldXZ - vec2(0.0, -5.0);
    float elev = oceanElevation(oceanLocal, t);
    // Very small vertical amplitude since plane is nearly horizontal
    return -2.32 + elev * 0.03;
  }
`;


// ─── FBM Noise GLSL ───────────────────────────────────────────────────────
const getFBMNoiseGLSL = (octaves: number) => `
  // Hash / value noise
  float hash(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    p += dot(p, p + 19.19);
    return fract(p.x * p.y);
  }

  float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i + vec2(0,0)), hash(i + vec2(1,0)), u.x),
      mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x),
      u.y
    );
  }

  // Fractional Brownian Motion
  float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    vec2 shift = vec2(100.0);
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
    for (int i = 0; i < ${octaves}; i++) {
      v += a * vnoise(p);
      p = rot * p * 2.0 + shift;
      a *= 0.5;
    }
    return v;
  }
`;

// ─── Procedural Irregular Geometry for Oil Slick ─────────────────────────
// We build a custom geometry: a disc-like polar mesh with random
// vertex jitter so there are absolutely no circular or rectangular artefacts.
function createOilSlickGeometry(
  radialSegs: number,
  ringSegs: number,
  maxRadius: number,
  seed: number
): THREE.BufferGeometry {
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  // Simple LCG pseudo-random using seed
  let rng = seed;
  const rand = () => {
    rng = (rng * 1664525 + 1013904223) & 0xffffffff;
    return (rng >>> 0) / 0xffffffff;
  };

  // Build radii per ring with organic variation
  const radii: number[] = [0]; // center
  for (let r = 1; r <= ringSegs; r++) {
    const baseRadius = (r / ringSegs) * maxRadius;
    // Add organic perturbation that increases toward the outer edge
    const jitter = (r / ringSegs) * maxRadius * 0.22;
    radii.push(baseRadius + (rand() - 0.5) * jitter);
  }

  // Center vertex
  positions.push(0, 0, 0);
  uvs.push(0.5, 0.5);
  let vertexIndex = 1;

  // Ring vertices
  for (let r = 1; r <= ringSegs; r++) {
    const radius = radii[r];
    for (let s = 0; s < radialSegs; s++) {
      const angle = (s / radialSegs) * Math.PI * 2;
      // Angular jitter — more toward outer rings
      const angleJitter = (r / ringSegs) * (0.4 / radialSegs) * Math.PI * 2;
      const a = angle + (rand() - 0.5) * angleJitter;
      // Radial jitter per vertex
      const rJitter = (rand() - 0.5) * radius * 0.15;
      const rr = radius + rJitter;

      const x = Math.cos(a) * rr;
      const z = Math.sin(a) * rr;
      positions.push(x, 0, z);
      uvs.push(x / maxRadius * 0.5 + 0.5, z / maxRadius * 0.5 + 0.5);
    }
  }

  // Center cap triangles (ring 1)
  for (let s = 0; s < radialSegs; s++) {
    const curr = 1 + s;
    const next = 1 + ((s + 1) % radialSegs);
    indices.push(0, curr, next);
  }

  // Ring quads
  for (let r = 1; r < ringSegs; r++) {
    const innerStart = 1 + (r - 1) * radialSegs;
    const outerStart = 1 + r * radialSegs;
    for (let s = 0; s < radialSegs; s++) {
      const i0 = innerStart + s;
      const i1 = innerStart + ((s + 1) % radialSegs);
      const o0 = outerStart + s;
      const o1 = outerStart + ((s + 1) % radialSegs);
      indices.push(i0, o0, i1);
      indices.push(i1, o0, o1);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

// ─── Oil Trail Geometry — an elongated strip behind the stern ─────────────
function createOilTrailGeometry(length: number, width: number, segsL: number, segsW: number): THREE.BufferGeometry {
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  // Build an organic elongated strip
  let rng = 99991;
  const rand = () => {
    rng = (rng * 1664525 + 1013904223) & 0xffffffff;
    return (rng >>> 0) / 0xffffffff;
  };

  for (let j = 0; j <= segsL; j++) {
    const t = j / segsL;
    // Trail width tapers from full at start (near ship) to thin at end
    const hw = (width / 2) * (1.0 - t * 0.6);
    for (let i = 0; i <= segsW; i++) {
      const s = i / segsW;
      const x = (s - 0.5) * 2.0 * hw + (rand() - 0.5) * hw * 0.18;
      const z = -t * length + (rand() - 0.5) * width * 0.08;
      positions.push(x, 0, z);
      uvs.push(s, t);
    }
  }

  for (let j = 0; j < segsL; j++) {
    for (let i = 0; i < segsW; i++) {
      const a = j * (segsW + 1) + i;
      const b = a + 1;
      const c = a + segsW + 1;
      const d = c + 1;
      indices.push(a, c, b);
      indices.push(b, c, d);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

// ─── Oil Slick Component ──────────────────────────────────────────────────
interface OilSpillProps {
  // World position of the oil leak point (ship's stern in world coordinates)
  // Updated each frame to follow the ship
  shipPosition: [number, number, number];
  shipRotation: [number, number, number]; // [pitch, yaw, roll] — yaw is [1]
}

const OilSlick: React.FC<OilSpillProps> = ({ shipPosition, shipRotation }) => {
  const meshRef = useRef<THREE.Mesh>(null);
  const quality = useQuality();

  const geo = useMemo(
    () => createOilSlickGeometry(quality.oilRadialSegs, quality.oilRingSegs, 7.5, 42),
    [quality.oilRadialSegs, quality.oilRingSegs]
  );

  // Prevent memory leak by disposing the geometry when the component unmounts
  // or when the quality tier changes.
  useEffect(() => {
    return () => geo.dispose();
  }, [geo]);

  const uniforms = useMemo(() => ({
    uTime:    { value: 0 },
    uCenter:  { value: new THREE.Vector2(0, 0) },  // world XZ of leak point
    uRadius:  { value: 7.5 },
    uGrowth:  { value: 0.0 },
  }), []);

  useFrame(({ clock }) => {
    // Oil spill time runs at the same 75% scale as the ocean
    const rawT = clock.getElapsedTime();
    const t = rawT * 0.65;
    uniforms.uTime.value = t;

    const yaw = shipRotation[1];
    // Stern offset in ship local space — tanker stern is ~4.5 units back from center
    const sternOffsetLocal = -4.5;
    const dx = Math.sin(yaw) * sternOffsetLocal;
    const dz = Math.cos(yaw) * sternOffsetLocal;

    const sternX = shipPosition[0] + dx;
    const sternZ = shipPosition[2] + dz;

    uniforms.uCenter.value.set(sternX, sternZ);

    // Smooth growth curve: starts at 0.25, eases to 1.0 over 45 seconds
    const growthT = Math.min(rawT / 45.0, 1.0);
    // Smoothstep easing for organic feel
    uniforms.uGrowth.value = 0.25 + growthT * growthT * (3.0 - 2.0 * growthT) * 0.75;

    if (meshRef.current) {
      meshRef.current.position.set(sternX, -2.32, sternZ);
    }
  });

  const vertexShader = `
    ${OCEAN_WAVE_GLSL}
    uniform float uTime;
    uniform vec2  uCenter;
    varying vec2  vLocalXZ;
    varying vec2  vWorldXZ;

    void main() {
      vec3 pos = position;
      // World XZ of this vertex = local offset + stern world position
      vec2 worldXZ = vec2(pos.x + uCenter.x, pos.z + uCenter.y);

      // Lift the oil plane to exactly match the ocean wave surface
      float waveY = worldYFromOcean(worldXZ, uTime);
      pos.y = waveY + 0.015; // float 1.5 cm above water surface

      // Pass to fragment shader
      vLocalXZ = vec2(pos.x, pos.z); // local offset from slick center
      vWorldXZ = worldXZ;

      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    }
  `;

  const fragmentShader = `
    ${getFBMNoiseGLSL(quality.fbmOctaves)}
    uniform float uTime;
    uniform float uGrowth;

    varying vec2  vLocalXZ;
    varying vec2  vWorldXZ;

    void main() {
      // Distance from slick center in local space (normalised by max radius)
      float dist = length(vLocalXZ) / 7.5;
      // Clamp dist so it works even if geometry overflows slightly
      dist = clamp(dist, 0.0, 1.2);

      // ── Organic boundary via FBM ──────────────────────────────────────
      // Slow drift to animate boundary
      vec2 noiseCoord = vLocalXZ * 0.22 + vec2(uTime * 0.04, uTime * 0.025);
      float boundary = fbm(noiseCoord);
      // Boundary noise shifts the effective radius, creating organic lobes
      float effectiveRadius = 0.8 + boundary * 0.42;
      // Growth over time — starts at 0.3, reaches 1.0
      effectiveRadius *= (0.3 + uGrowth * 0.7);

      // How far we are relative to the organic boundary
      float relDist = dist / effectiveRadius;

      // Discard pixels outside the boundary
      if (relDist > 1.0) discard;

      // ── Density / opacity profile ─────────────────────────────────────
      // Dense at center, thinning toward edge (physically accurate)
      float centerDensity = smoothstep(1.0, 0.0, relDist);
      // Add turbulent sub-pattern for realistic oil texture
      vec2 turbCoord = vWorldXZ * 0.6 + vec2(uTime * 0.08, -uTime * 0.05);
      float turb = fbm(turbCoord) * 0.5 + 0.5;
      float turbCoarse = fbm(vWorldXZ * 0.18 + vec2(uTime * 0.02)) * 0.5 + 0.5;

      // ── Density / alpha ───────────────────────────────────────────────
      // Edge tendrils / wisps for organic boundary
      float edgeWisp = fbm(noiseCoord * 3.0 + vec2(uTime * 0.08)) * 0.5 + 0.5;
      float outerEdge = smoothstep(0.78, 1.0, relDist);

      // Core density — ramp from center outward, modulated by FBM texture
      float coreDensity = centerDensity * (0.62 + turb * 0.22) * (0.75 + turbCoarse * 0.25);
      // Edge wisps — faint tendrils extending beyond main slick
      float edgeDensity = centerDensity * edgeWisp * 0.35;

      float alpha = mix(coreDensity, edgeDensity, outerEdge);
      // Boost overall visibility — oil is dark but must read against dark water
      alpha = clamp(alpha * 1.65, 0.0, 0.92);

      // ── Oil colour — dark crude, visible against bright daytime water ─────
      // Crude oil base: dark charcoal-green
      vec3 oilBase = vec3(0.018, 0.028, 0.022);

      // Thin-film interference: crude oil produces blue-green-violet sheen
      // Bias the hue toward maritime palette (no red/yellow rainbow)
      float iridescentPhase = turb * 5.8 + uTime * 0.12; // very slow drift
      vec3 iridescent = vec3(
        // Cyan-blue component
        0.28 + 0.22 * sin(iridescentPhase + 0.0),
        // Teal-green component
        0.45 + 0.25 * sin(iridescentPhase + 1.2),
        // Deep blue component
        0.62 + 0.20 * sin(iridescentPhase + 2.8)
      );

      // Iridescence peaks where oil film is thinnest (mid-edge transition)
      float iridFactor = smoothstep(0.05, 0.5, relDist) * smoothstep(1.0, 0.5, relDist);
      iridFactor *= 0.38; // boosted for daytime visibility

      vec3 finalColor = mix(oilBase, iridescent, iridFactor);

      // Sunlight specular reflection on oil surface (smooth surface catches warm light)
      float spec = pow(max(0.0, turb * turbCoarse), 6.0) * 0.22;
      // Warm sunlight colour
      finalColor += vec3(0.95, 0.85, 0.55) * spec;

      // Ambient darkening at center — thick crude absorbs more light
      float thickFactor = smoothstep(0.6, 0.0, relDist);
      finalColor = mix(finalColor, oilBase * 0.5, thickFactor * 0.3);

      gl_FragColor = vec4(finalColor, alpha);
    }
  `;

  return (
    <mesh
      ref={meshRef}
      geometry={geo}
      rotation={[0, 0, 0]}
    >
      <shaderMaterial
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
        blending={THREE.NormalBlending}
      />
    </mesh>
  );
};

// ─── Oil Trail (thin strip from stern tracking with movement) ─────────────
const OilTrail: React.FC<OilSpillProps> = ({ shipPosition, shipRotation }) => {
  const meshRef = useRef<THREE.Mesh>(null);
  const quality = useQuality();

  const geo = useMemo(
    () => createOilTrailGeometry(14, 1.8, quality.trailLengthSegs, quality.trailWidthSegs),
    [quality.trailLengthSegs, quality.trailWidthSegs]
  );

  // Prevent memory leak by disposing geometry
  useEffect(() => {
    return () => geo.dispose();
  }, [geo]);

  const uniforms = useMemo(() => ({
    uTime:   { value: 0 },
    uCenter: { value: new THREE.Vector2(0, 0) },
  }), []);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime() * 0.65;
    uniforms.uTime.value = t;

    const yaw = shipRotation[1];
    const sternOffsetLocal = -4.5;
    const dx = Math.sin(yaw) * sternOffsetLocal;
    const dz = Math.cos(yaw) * sternOffsetLocal;
    const sternX = shipPosition[0] + dx;
    const sternZ = shipPosition[2] + dz;
    uniforms.uCenter.value.set(sternX, sternZ);

    if (meshRef.current) {
      meshRef.current.position.set(sternX, -2.30, sternZ);
      meshRef.current.rotation.y = yaw;
    }
  });

  const vertexShader = `
    ${OCEAN_WAVE_GLSL}
    uniform float uTime;
    uniform vec2  uCenter;
    varying vec2  vUv2;
    varying vec2  vWorldXZ;

    void main() {
      vec3 pos = position;
      // Compute world XZ accounting for mesh's own rotation (done in modelMatrix)
      vec4 worldPos4 = modelMatrix * vec4(pos, 1.0);
      vec2 worldXZ = worldPos4.xz;
      float waveY = worldYFromOcean(worldXZ, uTime);
      pos.y = 0.0; // local Y — actual world Y handled via uniform model matrix
      // We need to set world Y but operate in local space:
      // modelMatrix already has the correct XZ transform, so just adjust local Y
      vec4 localPos = vec4(pos, 1.0);
      // Bake wave lift into clip space via a modified MVP
      // Simplification: just output with wave elevation baked into y
      vec3 worldSpacePos = worldPos4.xyz;
      worldSpacePos.y = waveY + 0.02;
      gl_Position = projectionMatrix * viewMatrix * vec4(worldSpacePos, 1.0);

      vUv2 = uv;
      vWorldXZ = worldXZ;
    }
  `;

  const fragmentShader = `
    ${getFBMNoiseGLSL(quality.fbmOctaves)}
    uniform float uTime;
    varying vec2  vUv2;
    varying vec2  vWorldXZ;

    void main() {
      float progress = vUv2.y; // 0 = near stern, 1 = far behind
      float centerDist = abs(vUv2.x - 0.5) * 2.0; // 0 = center, 1 = outer edge

      // Organic edge from noise
      vec2 nc = vWorldXZ * 0.4 + vec2(uTime * 0.06, uTime * 0.04);
      float noise = fbm(nc);
      float edgeNoise = 0.75 + noise * 0.32;

      float relEdge = centerDist / edgeNoise;
      if (relEdge > 1.0) discard;

      float alpha = (1.0 - progress * 0.88) * (1.0 - relEdge) * 0.55;
      float turbulence = fbm(vWorldXZ * 0.9 + vec2(uTime * 0.04)) * 0.25 + 0.75;
      alpha *= turbulence;
      alpha = clamp(alpha, 0.0, 0.62);
      if (alpha < 0.008) discard;

      // Trail oil is thinner — slightly more iridescent than the main slick
      vec3 oilColor = vec3(0.018, 0.014, 0.010);
      float iri = fbm(vWorldXZ * 0.45 + vec2(uTime * 0.07));
      float iriFactor = (1.0 - progress) * 0.22;
      // Maritime blue-green-violet palette only
      vec3 iridColor = vec3(
        0.25 + 0.18 * sin(iri * 5.5),
        0.48 + 0.22 * sin(iri * 5.5 + 1.3),
        0.68 + 0.18 * sin(iri * 5.5 + 2.9)
      );
      vec3 finalColor = mix(oilColor, iridColor, iriFactor);

      gl_FragColor = vec4(finalColor, alpha);
    }
  `;

  return (
    <mesh ref={meshRef} geometry={geo}>
      <shaderMaterial
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
        blending={THREE.NormalBlending}
      />
    </mesh>
  );
};

// ─── Public OilSpill Component ────────────────────────────────────────────
// Accepts the current ship world position + rotation to stay connected to it.
interface OilSpillComponentProps {
  shipPosition: [number, number, number];
  shipRotation: [number, number, number];
}

export const OilSpill: React.FC<OilSpillComponentProps> = ({
  shipPosition,
  shipRotation,
}) => {
  return (
    <>
      {/* Main expanding irregular slick near the stern */}
      <OilSlick shipPosition={shipPosition} shipRotation={shipRotation} />
      {/* Thin oil trail left behind the vessel as it moves */}
      <OilTrail shipPosition={shipPosition} shipRotation={shipRotation} />
    </>
  );
};

export default OilSpill;
