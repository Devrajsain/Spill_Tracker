import React, { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { Ocean } from './Ocean';
import { Ship } from './Ship';
import { Environment } from '@react-three/drei';
import { QualityProvider, useQuality } from './QualityContext';

interface ThreeDBackgroundProps {
  className?: string;
}

// Ship base position and rotation — kept as constants so OilSpill can anchor to them.
// The ship's useFrame animation applies subtle movement *around* these values.
const SHIP_BASE_POSITION: [number, number, number] = [6.0, -2.3, -2.0];
const SHIP_BASE_ROTATION: [number, number, number] = [0, Math.PI / 1.5, 0];

// ─── Inner Scene ─────────────────────────────────────────────────────────
// Separated so it can read QualityContext (which is provided by the wrapper).
const Scene: React.FC = () => {
  const quality = useQuality();

  return (
    <Canvas
      camera={{
        position: [0, 1.5, 13.5],
        fov: 38,
        near: 0.1,
        far: 5000,
      }}
      dpr={quality.dpr}
      gl={{
        antialias: quality.tier !== 'low',
        powerPreference: 'high-performance',
        toneMapping: 4, // THREE.ACESFilmicToneMapping
        toneMappingExposure: 1.1,
      }}
      style={{
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      }}
    >
      <Suspense fallback={null}>
        {/*
         ── LIGHTING RIG ────────────────────────────────────────────────────
         Core lights (ambient + 2 directional) always present.
         Decorative point lights conditionally rendered per quality tier.
         ─────────────────────────────────────────────────────────────────*/}

        {/* 1. Ambient — dim blue-gray base to keep left side dark for text */}
        <ambientLight intensity={0.25} color="#6090b0" />

        {/* 2. Key light — warm sunset from low angle behind-right */}
        <directionalLight
          position={[20, 8, -15]}
          intensity={3.5}
          color="#ffb347"
        />

        {/* 3. Sky fill — cool blue from above-left */}
        <directionalLight
          position={[-14, 12, -8]}
          intensity={0.5}
          color="#5a8ab0"
        />

        {/* 4. Horizon golden bounce — warm fill from behind */}
        <directionalLight
          position={[10, 2, -40]}
          intensity={1.5}
          color="#ff9944"
        />

        {/* ── Decorative point lights — disabled on low tier to save GPU ── */}
        {quality.showDecoLights && (
          <>
            {/* Golden sun glint on water near the tanker */}
            <pointLight
              position={[8, 0.5, -6]}
              intensity={1.5}
              distance={16}
              decay={2}
              color="#ffaa44"
            />

            {/* Cool blue fill from shadowed side */}
            <pointLight
              position={[-4, 2, 2]}
              intensity={0.3}
              distance={14}
              decay={2}
              color="#4488aa"
            />

            {/* Warm highlight on ship superstructure */}
            <pointLight
              position={[6, 4, -3]}
              intensity={0.6}
              distance={12}
              decay={2}
              color="#ffc875"
            />
          </>
        )}



        {/* Environment Map — sunset preset for warm golden reflections */}
        <Environment preset="sunset" />

        {/* 3D Scene Components */}
        <Ocean />
        <Ship
          position={SHIP_BASE_POSITION}
          rotation={SHIP_BASE_ROTATION}
          scale={0.9}
        />
      </Suspense>
    </Canvas>
  );
};

// ─── Public Component ─────────────────────────────────────────────────────
export const ThreeDBackground: React.FC<ThreeDBackgroundProps> = ({
  className = 'hero-3d-canvas',
}) => {
  return (
    <div
      className={className}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 1,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
      aria-hidden="true"
    >
      <QualityProvider>
        <Scene />
      </QualityProvider>
    </div>
  );
};

export default ThreeDBackground;
