import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';

// ─── Quality Tiers ───────────────────────────────────────────────────────
// Controls geometry density, shader complexity, DPR, and light count
// based on viewport width (a reliable proxy for device class).
export type QualityTier = 'high' | 'medium' | 'low';

export interface QualitySettings {
  tier: QualityTier;
  /** Device pixel ratio range passed to Canvas `dpr` */
  dpr: [number, number];
  /** Ocean plane segments (width, height) */
  oceanSegments: number;
  /** Oil slick radial segments */
  oilRadialSegs: number;
  /** Oil slick ring segments */
  oilRingSegs: number;
  /** Oil trail length segments */
  trailLengthSegs: number;
  /** Oil trail width segments */
  trailWidthSegs: number;
  /** FBM octave count for noise shaders */
  fbmOctaves: number;
  /** Whether to render decorative point lights (brand beacon, oil glow, etc.) */
  showDecoLights: boolean;
  /** Whether to render ship nav point lights (red/green running lights) */
  showNavLights: boolean;
  /** Whether to render the procedural ship wake */
  showWake: boolean;
}

// ─── Tier Presets ─────────────────────────────────────────────────────────
const QUALITY_HIGH: QualitySettings = {
  tier: 'high',
  dpr: [1, 2],
  oceanSegments: 280,
  oilRadialSegs: 64,
  oilRingSegs: 8,
  trailLengthSegs: 30,
  trailWidthSegs: 6,
  fbmOctaves: 5,
  showDecoLights: true,
  showNavLights: true,
  showWake: true,
};

const QUALITY_MEDIUM: QualitySettings = {
  tier: 'medium',
  dpr: [1, 1.5],
  oceanSegments: 120,
  oilRadialSegs: 36,
  oilRingSegs: 6,
  trailLengthSegs: 18,
  trailWidthSegs: 4,
  fbmOctaves: 4,
  showDecoLights: true,
  showNavLights: true,
  showWake: true,
};

const QUALITY_LOW: QualitySettings = {
  tier: 'low',
  dpr: [1, 1],
  oceanSegments: 64,
  oilRadialSegs: 20,
  oilRingSegs: 4,
  trailLengthSegs: 10,
  trailWidthSegs: 3,
  fbmOctaves: 3,
  showDecoLights: false,
  showNavLights: false,
  showWake: false,
};

// ─── Breakpoint Detection ─────────────────────────────────────────────────
function getTierForWidth(width: number): QualityTier {
  if (width <= 768) return 'low';
  if (width <= 1024) return 'medium';
  return 'high';
}

function getSettingsForTier(tier: QualityTier): QualitySettings {
  switch (tier) {
    case 'low':
      return QUALITY_LOW;
    case 'medium':
      return QUALITY_MEDIUM;
    default:
      return QUALITY_HIGH;
  }
}

// ─── React Context ────────────────────────────────────────────────────────
const QualityContext = createContext<QualitySettings>(QUALITY_HIGH);

/** Read current quality settings from any child component inside the 3D scene. */
export const useQuality = () => useContext(QualityContext);

/** Provider that detects screen width and broadcasts the appropriate tier. */
export const QualityProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [tier, setTier] = useState<QualityTier>(() =>
    typeof window !== 'undefined' ? getTierForWidth(window.innerWidth) : 'high'
  );

  useEffect(() => {
    const handleResize = () => {
      const newTier = getTierForWidth(window.innerWidth);
      setTier((prev) => (prev !== newTier ? newTier : prev));
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const settings = useMemo(() => getSettingsForTier(tier), [tier]);

  return (
    <QualityContext.Provider value={settings}>
      {children}
    </QualityContext.Provider>
  );
};
