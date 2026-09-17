import React, { useRef, useMemo, useState, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { useQuality } from './QualityContext';

interface ShipProps {
  position?: [number, number, number];
  rotation?: [number, number, number];
  scale?: number;
}

// ─── Procedural Wake trailing behind the vessel ──────────────────────────
const ShipWake: React.FC<{ length?: number; width?: number }> = ({
  length = 22,
  width = 6,
}) => {
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
    }),
    []
  );

  useFrame(({ clock }) => {
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value = clock.getElapsedTime();
    }
  });

  const vertexShader = `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `;

  const fragmentShader = `
    uniform float uTime;
    varying vec2 vUv;

    void main() {
      // vUv.y goes from 0 (at stern) to 1 (trailing far behind)
      float progress = vUv.y;
      float centerDist = abs(vUv.x - 0.5) * 2.0; // 0 at center, 1 at outer edges

      // V-shaped wake envelope spreading outward
      float wakeWidth = 0.15 + progress * 0.85;
      if (centerDist > wakeWidth) {
        discard;
      }

      // V-angle wake edges (Kelvin wake arms) — more defined
      float armDistance = abs(centerDist - (0.12 + progress * 0.72));
      float wakeArms = smoothstep(0.1, 0.0, armDistance) * 0.8;

      // Central turbulent propeller wash — stronger
      float washDistance = abs(centerDist);
      float propWash = smoothstep(0.3, 0.0, washDistance) * (1.0 - progress * 0.7);

      // Foam churning ripples — more dynamic
      float churn = sin(progress * 55.0 - uTime * 5.0) * 0.3 + 0.7;
      float microFoam = sin((vUv.x + vUv.y) * 100.0 + uTime * 3.0) * 0.2;
      float turbulence = sin(progress * 25.0 + vUv.x * 30.0 - uTime * 2.5) * 0.15;

      float foamIntensity = (wakeArms + propWash * churn + microFoam + turbulence) * (1.0 - progress * 0.8);

      // Soft fading near edges and trailing end
      float edgeFade = smoothstep(wakeWidth, wakeWidth - 0.12, centerDist);
      float alpha = clamp(foamIntensity * edgeFade * 0.35, 0.0, 0.45);

      if (alpha < 0.01) discard;

      // Bright sea foam with sunset warmth
      vec3 foamColor = mix(vec3(0.6, 0.65, 0.72), vec3(0.88, 0.82, 0.75), propWash);
      gl_FragColor = vec4(foamColor, alpha);
    }
  `;

  return (
    <mesh
      // Ship base world Y is -2.0. Ocean is at -2.5. Wake at ocean level = -0.5 local.
      position={[0, -0.5, -length / 2 - 1.2]}
      rotation={[-Math.PI / 2, 0, Math.PI]}
    >
      <planeGeometry args={[width, length, 16, 32]} />
      <shaderMaterial
        ref={materialRef}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
};

// ─── Real GLB Tanker Model ───────────────────────────────────────────────
const GLBModel: React.FC = () => {
  // Load model from /models/tanker.glb
  const { scene } = useGLTF('/models/tanker.glb');

  // Clone scene so it can be re-rendered cleanly and modify properties
  const clonedScene = useMemo(() => {
    const clone = scene.clone(true);

    clone.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        mesh.castShadow = true;
        mesh.receiveShadow = true;

        // Ensure materials interact realistically with maritime scene lighting
        if (mesh.material) {
          const mat = (mesh.material as THREE.MeshStandardMaterial).clone();
          mat.roughness = Math.max(mat.roughness ?? 0.5, 0.45);
          mat.metalness = Math.min(mat.metalness ?? 0.2, 0.5);
          mesh.material = mat;
        }
      }
    });

    return clone;
  }, [scene]);

  // Model bounding box centering:
  // Model size is ~45.3 (W) x 62.9 (H) x 274.2 (L)
  // Center is [-2.62, 31.96, 2.14], keel at Y=0.52.
  // We offset X by +2.62, Z by -2.14 to center horizontally.
  // We offset Y by -12 so the loaded waterline sits right at the ocean surface!
  // In the GLB model, bow is at -Z. We rotate 180 deg (Math.PI) so bow points forward (+Z).
  return (
    <group
      position={[0.1, -0.45, 0]}
      rotation={[0, Math.PI, 0]}
      scale={0.038}
    >
      <primitive object={clonedScene} position={[2.62, -12.0, -2.14]} />
    </group>
  );
};

// Preload the tanker model
useGLTF.preload('/models/tanker.glb');

// ─── Graceful Fallback Procedural Ship ────────────────────────────────────
const FallbackProceduralShip: React.FC = () => {
  return (
    <group>
      {/* Lower Red Waterline Hull */}
      <mesh position={[0, -0.2, 0]}>
        <boxGeometry args={[1.7, 0.45, 8.2]} />
        <meshStandardMaterial color="#8b1e1e" roughness={0.5} metalness={0.2} />
      </mesh>

      {/* Main Hull Upper Deck */}
      <mesh position={[0, 0.25, 0]}>
        <boxGeometry args={[1.8, 0.5, 8.4]} />
        <meshStandardMaterial color="#171e27" roughness={0.4} metalness={0.4} />
      </mesh>

      {/* Bow */}
      <mesh position={[0, 0.4, 4.4]} rotation={[0.2, 0, 0]}>
        <boxGeometry args={[1.6, 0.5, 1.2]} />
        <meshStandardMaterial color="#1a232e" roughness={0.4} />
      </mesh>

      {/* Superstructure Bridge */}
      <group position={[0, 0.95, -2.8]}>
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[1.5, 0.9, 1.6]} />
          <meshStandardMaterial color="#f1f5f9" roughness={0.3} />
        </mesh>
        <mesh position={[0, 0.65, 0]}>
          <boxGeometry args={[1.8, 0.45, 1.2]} />
          <meshStandardMaterial color="#e2e8f0" roughness={0.3} />
        </mesh>
        <mesh position={[0, 0.9, -0.4]}>
          <cylinderGeometry args={[0.18, 0.22, 0.7, 16]} />
          <meshStandardMaterial color="#ef4444" roughness={0.4} />
        </mesh>
      </group>
    </group>
  );
};

// ─── Error Boundary for GLTF Loading ─────────────────────────────────────
interface ErrorBoundaryProps {
  fallback: React.ReactNode;
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class ShipErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: any) {
    console.warn('[ThreeDBackground/Ship] Failed to load GLTF tanker model, rendering fallback ship.', error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

// ─── Reusable Ship Component ─────────────────────────────────────────────
export const Ship: React.FC<ShipProps> = ({
  position = [6.0, -2.3, -2.0], // Corrected waterline — partially submerged
  rotation = [0, Math.PI / 1.5, 0],
  scale = 1.0,
}) => {
  const shipGroupRef = useRef<THREE.Group>(null);
  const quality = useQuality();
  const basePosition = useMemo(() => new THREE.Vector3(...position), [position]);
  const baseRotation = useMemo(() => new THREE.Euler(...rotation), [rotation]);

  // Heading vector calculated from initial yaw rotation:
  // In our setup, forward is along +Z in ship's local coordinates.
  const headingVec = useMemo(() => {
    const yaw = rotation[1];
    // Forward vector in world coordinates
    return new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw)).normalize();
  }, [rotation]);

  // Buoyancy animation + slow forward cruising movement:
  // - Heave (bobbing) — visible but not extreme
  // - Roll and Pitch matching ocean swells
  // - Continuous slow forward cruising movement
  useFrame(({ clock }) => {
    if (!shipGroupRef.current) return;
    const t = clock.getElapsedTime() * 0.5;

    // 1. Continuous slow forward drift — ship cruises steadily forward
    // Gradual forward movement with a very slow sinusoidal variation
    const forwardDrift = Math.sin(t * (2 * Math.PI / 35.0)) * 2.0;
    const currentPos = basePosition.clone().addScaledVector(headingVec, forwardDrift);

    // 2. Heave (bobbing) — noticeable but realistic for a large loaded tanker
    // Multiple sine layers for organic motion
    const heave = Math.sin(t * 0.7) * 0.04
                + Math.cos(t * 1.15) * 0.015
                + Math.sin(t * 2.3) * 0.008;
    shipGroupRef.current.position.set(
      currentPos.x,
      currentPos.y + heave,
      currentPos.z
    );

    // 3. Roll — lateral rocking across swells (visible gentle rocking)
    const roll = Math.sin(t * 0.8) * 0.012
               + Math.cos(t * 1.3) * 0.006
               + Math.sin(t * 2.1) * 0.003;
    // 4. Pitch — bow dipping into swells (subtle forward/back tilt)
    const pitch = Math.cos(t * 0.65) * 0.008
                + Math.sin(t * 1.1) * 0.004;

    shipGroupRef.current.rotation.set(
      baseRotation.x + pitch,
      baseRotation.y,
      baseRotation.z + roll
    );
  });

  return (
    <group ref={shipGroupRef} position={position} rotation={rotation} scale={scale}>
      <ShipErrorBoundary fallback={<FallbackProceduralShip />}>
        <React.Suspense fallback={<FallbackProceduralShip />}>
          <GLBModel />
        </React.Suspense>
      </ShipErrorBoundary>

      {quality.showNavLights && (
        <>
          {/* Port (Left) running light — SOLAS red, 225° arc */}
          <mesh position={[-0.95, 1.4, -2.6]}>
            <sphereGeometry args={[0.035, 8, 8]} />
            <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={1.2} />
          </mesh>
          <pointLight position={[-1.0, 1.4, -2.6]} color="#dc2626" intensity={0.3} distance={4} decay={2} />

          {/* Starboard (Right) running light — SOLAS green, 225° arc */}
          <mesh position={[0.95, 1.4, -2.6]}>
            <sphereGeometry args={[0.035, 8, 8]} />
            <meshStandardMaterial color="#10b981" emissive="#10b981" emissiveIntensity={1.2} />
          </mesh>
          <pointLight position={[1.0, 1.4, -2.6]} color="#059669" intensity={0.3} distance={4} decay={2} />

          {/* Masthead / Steaming light — white, forward arc */}
          <mesh position={[0, 2.1, -1.8]}>
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshStandardMaterial color="#ffffff" emissive="#e0f2fe" emissiveIntensity={1.0} />
          </mesh>

          {/* Stern light — white, visible from astern */}
          <mesh position={[0, 0.7, -4.8]}>
            <sphereGeometry args={[0.03, 8, 8]} />
            <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.9} />
          </mesh>
        </>
      )}

      {/* Key light on ship hull — warm sunset backlight from behind-right */}
      <pointLight
        position={[3, 5, -6]}
        intensity={3.0}
        distance={16}
        decay={1.8}
        color="#ffb347"
      />

      {/* Sunset rim light — golden edge highlight on hull silhouette */}
      <pointLight
        position={[-2, 3, -8]}
        intensity={1.5}
        distance={12}
        decay={2}
        color="#ff9944"
      />

      {/* Contact Shadow / Hull darkening — very subtle */}
      {/* Ship is at -2.0, ocean at -2.5, so shadow at -0.49 local */}
      <mesh position={[0, -0.49, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[2.0, 10]} />
        <meshBasicMaterial color="#021526" transparent opacity={0.2} depthWrite={false} />
      </mesh>

      {/* Visible stern wake — longer trail for cruising feel */}
      {quality.showWake && <ShipWake length={20} width={5} />}
    </group>
  );
};

export default Ship;
