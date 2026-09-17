import React, { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useQuality } from './QualityContext';

// ─── Sunset Sky Dome with Procedural Clouds ──────────────────────────────
const SkyDome: React.FC = () => {
  const vertexShader = `
    varying vec3 vWorldPosition;
    varying vec2 vUv;
    void main() {
      vec4 worldPos = modelMatrix * vec4(position, 1.0);
      vWorldPosition = worldPos.xyz;
      vUv = vec2(
        atan(worldPos.x, worldPos.z) / (2.0 * 3.14159) + 0.5,
        asin(clamp(worldPos.y / length(worldPos.xyz), -1.0, 1.0)) / 1.57079
      );
      gl_Position = projectionMatrix * viewMatrix * worldPos;
    }
  `;

  const fragmentShader = `
    varying vec3 vWorldPosition;
    varying vec2 vUv;

    float hash(vec2 p) { return fract(1e4 * sin(17.0 * p.x + p.y * 0.1) * (0.1 + abs(sin(p.y * 13.0 + p.x)))); }
    float noise(vec2 x) {
      vec2 i = floor(x);
      vec2 f = fract(x);
      float a = hash(i);
      float b = hash(i + vec2(1.0, 0.0));
      float c = hash(i + vec2(0.0, 1.0));
      float d = hash(i + vec2(1.0, 1.0));
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
    }
    float fbm(vec2 p) {
      float v = 0.0;
      v += noise(p * 4.0) * 0.5;
      v += noise(p * 8.0) * 0.25;
      v += noise(p * 16.0) * 0.125;
      v += noise(p * 32.0) * 0.0625;
      return v;
    }

    void main() {
      float h = max(normalize(vWorldPosition).y, 0.0);

      // Deep blue sky gradient matching reference — narrow warm band at horizon
      vec3 horizonColor = vec3(0.85, 0.50, 0.15);  // warm golden amber at horizon
      vec3 lowSky       = vec3(0.25, 0.45, 0.68);  // pale sky blue just above horizon
      vec3 midSkyColor  = vec3(0.06, 0.22, 0.45);  // rich deep blue
      vec3 zenithColor  = vec3(0.01, 0.04, 0.12);  // very dark navy zenith

      vec3 skyColor = mix(horizonColor, lowSky, smoothstep(0.0, 0.05, h));
      skyColor = mix(skyColor, midSkyColor, smoothstep(0.05, 0.18, h));
      skyColor = mix(skyColor, zenithColor, smoothstep(0.18, 0.55, h));

      // Thin wispy clouds — very subtle
      float cloudVal = fbm(vUv * vec2(12.0, 5.0));
      float cloudMask = smoothstep(0.03, 0.15, h) * smoothstep(0.6, 0.3, h);
      float cloudAlpha = smoothstep(0.48, 0.85, cloudVal) * cloudMask * 0.4;
      vec3 cloudColor = mix(vec3(1.0, 0.85, 0.65), vec3(0.7, 0.75, 0.85), h);

      // Sun disc — bright, tight, with halo glow confined near horizon
      vec3 sunDir = normalize(vec3(0.7, 0.08, -0.7));
      float sunDot = max(dot(normalize(vWorldPosition), sunDir), 0.0);
      // Tight bright sun disc
      float sunDisc = smoothstep(0.9985, 0.9995, sunDot);
      // Wider warm halo around the sun — confined near horizon
      float horizonMask = smoothstep(0.25, 0.0, h); // fades above horizon
      float sunHalo = pow(sunDot, 64.0) * 1.5 * horizonMask;
      // Very wide atmospheric glow — also confined near horizon
      float sunAtmo = pow(sunDot, 8.0) * 0.4 * horizonMask;
      vec3 sunColor = vec3(1.0, 0.95, 0.85) * sunDisc * 3.0
                    + vec3(1.0, 0.8, 0.4) * sunHalo
                    + vec3(0.9, 0.6, 0.2) * sunAtmo;

      // Below-horizon darkening (water area seen through the sphere)
      float belowHorizon = max(-normalize(vWorldPosition).y, 0.0);
      vec3 belowColor = vec3(0.02, 0.06, 0.12);

      vec3 finalColor = mix(skyColor, cloudColor, cloudAlpha) + sunColor;
      finalColor = mix(finalColor, belowColor, smoothstep(0.0, 0.05, belowHorizon));

      gl_FragColor = vec4(finalColor, 1.0);
    }
  `;

  return (
    <mesh>
      <sphereGeometry args={[500, 48, 32]} />
      <shaderMaterial
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        side={THREE.BackSide}
        depthWrite={false}
      />
    </mesh>
  );
};

// ─── Ocean Surface ────────────────────────────────────────────────────────
export const Ocean: React.FC = () => {
  const materialRef = useRef<THREE.MeshPhysicalMaterial>(null);
  const quality = useQuality();

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
    }),
    []
  );

  useFrame(({ clock }) => {
    uniforms.uTime.value = clock.getElapsedTime() * 0.35;
  });

  const onBeforeCompile = (shader: {
    uniforms: Record<string, { value: any }>;
    vertexShader: string;
    fragmentShader: string;
  }) => {
    shader.uniforms.uTime = uniforms.uTime;

    // ── Vertex Shader ─────────────────────────────────────────────────
    shader.vertexShader = `
      uniform float uTime;

      vec3 gerstnerWave(vec4 wave, vec3 p, inout vec3 tangent, inout vec3 binormal) {
          float steepness = wave.z;
          float wavelength = wave.w;
          float k = 6.28318 / wavelength;
          float c = sqrt(9.8 / k);
          vec2 d = normalize(wave.xy);
          float f = k * (dot(d, p.xy) - c * uTime);
          float a = steepness / k;

          tangent += vec3(
              -d.x * d.x * steepness * sin(f),
              -d.x * d.y * steepness * sin(f),
               d.x * a * k * cos(f)
          );
          binormal += vec3(
              -d.x * d.y * steepness * sin(f),
              -d.y * d.y * steepness * sin(f),
               d.y * a * k * cos(f)
          );
          return vec3(d.x * a * cos(f), d.y * a * cos(f), a * sin(f));
      }

      ${shader.vertexShader}
    `;

    shader.vertexShader = shader.vertexShader.replace(
      '#include <beginnormal_vertex>',
      `
      vec3 gridPoint = position;
      vec3 tangent = vec3(1.0, 0.0, 0.0);
      vec3 binormal = vec3(0.0, 1.0, 0.0);
      vec3 p = gridPoint;

      // Realistic open-ocean waves — moderate swell + fine detail ripples
      vec4 waveA = vec4(1.0, 0.3, 0.015, 45.0);   // primary swell
      vec4 waveB = vec4(0.6, -0.8, 0.012, 28.0);   // cross swell
      vec4 waveC = vec4(-0.4, 0.7, 0.02, 12.0);    // medium wave
      vec4 waveD = vec4(0.9, 0.4, 0.018, 7.0);     // choppy detail
      vec4 waveE = vec4(1.0, -0.2, 0.025, 3.5);    // fine ripples
      vec4 waveF = vec4(-0.3, 1.0, 0.022, 1.8);    // micro ripples
      vec4 waveG = vec4(0.5, 0.5, 0.03, 0.9);      // extra micro detail

      p += gerstnerWave(waveA, gridPoint, tangent, binormal);
      p += gerstnerWave(waveB, gridPoint, tangent, binormal);
      p += gerstnerWave(waveC, gridPoint, tangent, binormal);
      p += gerstnerWave(waveD, gridPoint, tangent, binormal);
      p += gerstnerWave(waveE, gridPoint, tangent, binormal);
      p += gerstnerWave(waveF, gridPoint, tangent, binormal);
      p += gerstnerWave(waveG, gridPoint, tangent, binormal);

      vec3 objectNormal = normalize(cross(tangent, binormal));
      `
    );

    shader.vertexShader = shader.vertexShader.replace(
      '#include <begin_vertex>',
      `
      vec3 transformed = p;
      `
    );

    // ── Fragment Shader ───────────────────────────────────────────────
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <dithering_fragment>',
      `
      // View distance for depth-based effects
      float viewDist = length(vViewPosition);
      float depthFade = smoothstep(5.0, 180.0, viewDist);

      // Deep ocean color — matching reference: dark blue, not teal
      vec3 nearWater = vec3(0.02, 0.12, 0.22);   // deep blue near
      vec3 farWater  = vec3(0.01, 0.05, 0.12);    // very dark navy far

      // Blend base color with distance-dependent depth color
      gl_FragColor.rgb = mix(
        mix(gl_FragColor.rgb, nearWater, 0.45),
        farWater,
        depthFade * 0.6
      );

      // ── Sun reflection "road" — bright golden path on the water ──
      vec3 viewDir = normalize(vViewPosition);
      // Sun direction matching SkyDome sun position
      vec2 sunDir2D = normalize(vec2(0.7, -0.7));
      float sunAlignment = dot(normalize(vec2(viewDir.x, viewDir.z)), sunDir2D);

      // Narrow bright core of sun road
      float sunRoadCore = pow(max(sunAlignment, 0.0), 24.0);
      // Wider warm glow around the sun road
      float sunRoadGlow = pow(max(sunAlignment, 0.0), 6.0);

      // Only show sun road toward the horizon
      float sunRoadIntensity = depthFade * (sunRoadCore * 1.2 + sunRoadGlow * 0.25);

      vec3 sunReflectColor = vec3(1.0, 0.82, 0.45);
      gl_FragColor.rgb += sunReflectColor * sunRoadIntensity;

      // Subtle Fresnel darkening at steep viewing angles (near camera)
      float fresnel = pow(1.0 - abs(dot(normalize(vViewPosition), vec3(0.0, 1.0, 0.0))), 3.0);
      gl_FragColor.rgb = mix(gl_FragColor.rgb, gl_FragColor.rgb * 1.15, fresnel * 0.3);

      #include <dithering_fragment>
      `
    );
  };

  const segments = Math.min(Math.max(quality.oceanSegments, 256), 384);

  return (
    <>
      <SkyDome />
      {/* Ocean surface */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -2.5, 0]}
        receiveShadow
      >
        <planeGeometry args={[2000, 2000, segments, segments]} />

        <meshPhysicalMaterial
          ref={materialRef}
          color="#082840"
          emissive="#000305"
          roughness={0.12}
          metalness={0.9}
          ior={1.33}
          reflectivity={0.7}
          envMapIntensity={1.0}
          clearcoat={0.1}
          clearcoatRoughness={0.4}
          onBeforeCompile={(shader) => {
            onBeforeCompile(shader);
          }}
        />
      </mesh>
    </>
  );
};
