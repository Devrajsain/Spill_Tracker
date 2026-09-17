import React from 'react';
import {
  Shield, ArrowRight, Upload, Satellite, Waves, Scale,
  Zap, FileText, Radio, Crosshair, Target,
} from 'lucide-react';
import { ThreeDBackground } from './ThreeDBackground';

interface HeroSectionProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const HeroSection: React.FC<HeroSectionProps> = ({ onNavigate, onOpenUpload }) => {
  return (
    <section className="hero-section relative overflow-hidden">
      {/* ─── 3D Real-time Background ─── */}
      <ThreeDBackground />

      {/* ─── Overlay ─── */}
      <div className="hero-overlay" aria-hidden="true" />

      {/* ─── Content Layer ─── */}
      <div className="relative z-10 max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 pt-24 lg:pt-28 pb-8">

        {/* ═══ TOP BADGES ═══ */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-white/5 backdrop-blur-sm border border-cyan-500/20 rounded-full">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.15em] text-white/90">
              National Maritime Surveillance
            </span>
          </div>
          <span className="text-[11px] font-medium uppercase tracking-[0.2em] text-white/40">
            Satellite &nbsp;+ &nbsp;AI &nbsp;+ &nbsp;Forensics
          </span>
        </div>

        {/* ═══ MAIN GRID ═══ */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-6 items-start">

          {/* ──── LEFT COLUMN (7 cols) ──── */}
          <div className="lg:col-span-7 space-y-5">

            {/* Hero Heading */}
            <h1 className="text-3xl sm:text-4xl lg:text-[2.9rem] xl:text-[3.4rem] font-extrabold text-white leading-[1.25] tracking-tight max-w-[800px]">
              AI-assisted Oil Spill{' '}
              <br className="hidden sm:block" />
              Detection and Vessel{' '}
              <br className="hidden sm:block" />
              Attribution
            </h1>

            {/* Cyan Tagline */}
            <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-cyan-400/80 mt-8 mb-6">
              — &nbsp;Cleaner Seas &nbsp;| &nbsp;Safer Coasts &nbsp;| &nbsp;A Greener Tomorrow
            </p>



            {/* ═══ CTA BUTTONS ═══ */}
            <div className="flex flex-wrap items-center gap-4 pt-8">
              <button
                onClick={() => onNavigate('dashboard')}
                className="cta-primary"
              >
                <span>Launch Dashboard</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                onClick={onOpenUpload}
                className="cta-secondary"
              >
                <Upload className="w-4 h-4" />
                <span>Upload New Case</span>
              </button>
            </div>

            {/* ═══ TRUST INDICATORS ═══ */}
            <div className="flex flex-wrap items-center gap-5 pt-8 text-[11px] text-white/50">
              <span className="flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-emerald-400/70" />
                Integrated with ISRO Bhuvan Tiles
              </span>
              <span className="flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-emerald-400/70" />
                Court-Admissible Forensic Logs
              </span>
              <span className="flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-cyan-400/70" />
                Real-time Surveillance
              </span>
            </div>

            {/* ═══ BOTTOM STATISTICS BAR ═══ */}
            <div className="stats-bar mt-12 inline-flex">
              <div className="stat-item !px-6 !pl-4">
                <span className="stat-value">24/7</span>
                <span className="stat-label">Surveillance</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-item !px-6">
                <span className="stat-value">100m</span>
                <span className="stat-label">SAR Resolution</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-item !px-6">
                <span className="stat-value">&lt; 2 hrs</span>
                <span className="stat-label">Detection to Alert</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-item !px-6 !pr-4">
                <span className="stat-value">Higher</span>
                <span className="stat-label">Attribution Confidence</span>
              </div>
            </div>
          </div>

          {/* ──── RIGHT COLUMN (5 cols) ──── */}
          <div className="lg:col-span-5 space-y-4 relative h-full min-h-[300px]">

            {/* ═══ SUSPECT VESSEL CARD ═══ */}
            <div className="suspect-vessel-card lg:absolute lg:top-[172px] lg:right-[18%] z-20 shadow-[0_0_15px_rgba(239,68,68,0.1)] border border-red-500/20 bg-[#071422]/80 backdrop-blur-md rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="relative flex items-center justify-center">
                  <span className="absolute w-full h-full rounded-full bg-red-500/20 animate-ping" />
                  <Target className="w-4 h-4 text-red-400 relative z-10" />
                </div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-red-400">Suspect Vessel</span>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[10px] font-mono text-white/80">
                <div><span className="text-white/40">MMSI:</span> 415233000</div>
                <div><span className="text-white/40">TYPE:</span> OIL TANKER</div>
                <div><span className="text-white/40">COURSE:</span> 233°</div>
                <div><span className="text-white/40">SPEED:</span> 12.4 kn</div>
              </div>
              {/* Decorative connector line pointing down towards the ship */}
              <div className="hidden lg:block absolute -bottom-32 left-1/2 w-px h-32 bg-red-400/50 pointer-events-none" />
              <div className="hidden lg:block absolute -bottom-[136px] left-1/2 -translate-x-1/2 w-8 h-8 border border-red-500/70 bg-red-500/20 pointer-events-none flex items-center justify-center">
                  <Crosshair className="w-4 h-4 text-red-400/80" />
              </div>
            </div>

          </div>
        </div>

        {/* ═══ RIGHT-SIDE DECORATIVE TEXT ═══ */}
        <div className="hidden xl:block absolute right-6 top-1/2 -translate-y-1/2 z-[5] pointer-events-none">
          <div className="text-[13px] font-bold uppercase tracking-[0.4em] text-white/[0.06] leading-loose text-right">
            Cleaner<br/>Seas<br/>Safer<br/>Tomorrow
          </div>
        </div>



      </div>
    </section>
  );
};
