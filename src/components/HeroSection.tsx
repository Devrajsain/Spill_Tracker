import React from 'react';
import { Shield, Radio, ArrowRight, Upload, MapPin, Compass, AlertTriangle, Layers } from 'lucide-react';

interface HeroSectionProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const HeroSection: React.FC<HeroSectionProps> = ({ onNavigate, onOpenUpload }) => {
  return (
    <section className="relative bg-white pt-8 pb-16 border-b border-gov-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Official Banner Tag */}
        <div className="mb-6 inline-flex items-center gap-2 px-3 py-1 bg-gov-light border border-gov-border rounded-gov text-xs text-navy-800 font-medium">
          <Shield className="w-3.5 h-3.5 text-navy-800" />
          <span>NATIONAL MARITIME DEFENSE &amp; SURVEILLANCE DIRECTORE</span>
          <span className="text-gray-400">|</span>
          <span className="text-gov-muted font-mono text-[11px]">CLASSIFICATION: UNCLASSIFIED / OFFICIAL USE</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          {/* Left Column: Content */}
          <div className="lg:col-span-7 space-y-6">
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-navy-800 tracking-tight leading-tight">
              AI-assisted Oil Spill Detection and Vessel Attribution for India's Maritime Waters
            </h1>

            <p className="text-base sm:text-lg text-gov-muted leading-relaxed font-normal">
              SlickTrace is the national intelligence grid unifying Earth-observation SAR satellite imagery, 
              hydrodynamic drift hindcasting models, and automatic identification system (AIS) vessel tracking 
              to enable rapid environmental response and forensic legal attribution against non-compliant maritime discharges.
            </p>

            {/* Official Key Capabilities Tags */}
            <div className="grid grid-cols-3 gap-3 py-2">
              <div className="bg-gov-light p-3 border border-gov-border rounded-gov">
                <p className="text-[11px] font-semibold text-gov-muted uppercase tracking-wider">Detection Mode</p>
                <p className="text-sm font-bold text-navy-800">SAR Sentinel-1 / Sentinel-2</p>
              </div>
              <div className="bg-gov-light p-3 border border-gov-border rounded-gov">
                <p className="text-[11px] font-semibold text-gov-muted uppercase tracking-wider">Hydrodynamic Engine</p>
                <p className="text-sm font-bold text-navy-800">18h Origin Backtrack</p>
              </div>
              <div className="bg-gov-light p-3 border border-gov-border rounded-gov">
                <p className="text-[11px] font-semibold text-gov-muted uppercase tracking-wider">Attribution Confidence</p>
                <p className="text-sm font-bold text-navy-800">Probability Scoring</p>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-4 pt-2">
              <button
                onClick={() => onNavigate('dashboard')}
                className="px-6 py-3 text-sm font-semibold uppercase tracking-wider text-white bg-navy-800 hover:bg-navy-900 border border-navy-800 rounded-gov shadow-sm transition-all flex items-center gap-2"
              >
                <span>Launch Dashboard</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                onClick={onOpenUpload}
                className="px-6 py-3 text-sm font-semibold uppercase tracking-wider text-navy-800 bg-white hover:bg-gov-light border border-navy-800 rounded-gov shadow-sm transition-all flex items-center gap-2"
              >
                <Upload className="w-4 h-4 text-navy-800" />
                <span>Upload New Case</span>
              </button>
            </div>

            {/* Verification Metadata Footer */}
            <div className="pt-4 border-t border-gov-border flex items-center space-x-6 text-xs text-gov-muted">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                Integrated with ISRO Bhuvan Tiles
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-navy-800"></span>
                Court-Admissible Forensic Logs
              </span>
            </div>
          </div>

          {/* Right Column: Operational Briefing Cartographic Panel */}
          <div className="lg:col-span-5">
            <div className="bg-navy-900 text-white border-2 border-navy-800 rounded-gov overflow-hidden shadow-md relative">
              {/* GIS Panel Header */}
              <div className="bg-navy-800 px-4 py-2.5 flex items-center justify-between border-b border-navy-700 text-xs">
                <div className="flex items-center space-x-2 font-mono">
                  <Radio className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                  <span className="text-amber-400 font-bold">GRID MON-2291</span>
                  <span className="text-gray-400">|</span>
                  <span className="text-gray-300">GULF OF KUTCH SURVEILLANCE ZONE</span>
                </div>
                <span className="text-[10px] bg-emerald-950 text-emerald-400 px-2 py-0.5 rounded border border-emerald-800 font-mono">
                  LIVE SATELLITE
                </span>
              </div>

              {/* Cartographic GIS View Box */}
              <div className="relative h-96 bg-[#0a192f] overflow-hidden border-b border-navy-700">
                {/* Simulated Coastline GIS Map Texture */}
                <div 
                  className="absolute inset-0 opacity-40 bg-cover bg-center"
                  style={{
                    backgroundImage: `url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1000&q=80')`
                  }}
                ></div>

                {/* Ocean Grid Overlay */}
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#1E293B_1px,transparent_1px),linear-gradient(to_bottom,#1E293B_1px,transparent_1px)] bg-[size:24px_24px] opacity-60"></div>

                {/* Coastline Polygon Path (Vector graphic of Indian West Coast) */}
                <svg className="absolute inset-0 w-full h-full stroke-emerald-500/50 fill-emerald-950/20" viewBox="0 0 500 400">
                  <path d="M0,80 Q120,90 200,160 T350,220 T500,280 L500,0 L0,0 Z" strokeWidth="1.5" />
                  {/* Maritime Boundary Line */}
                  <path d="M50,160 L450,320" stroke="#FF9933" strokeWidth="1.5" strokeDasharray="4,4" />
                </svg>

                {/* Satellite Monitored Slick Polygon */}
                <div className="absolute top-[42%] left-[45%] w-24 h-12 bg-red-600/40 border-2 border-red-500 rounded-full rotate-[15deg] flex items-center justify-center animate-pulse">
                  <span className="text-[9px] font-mono text-red-200 bg-red-950/80 px-1 border border-red-500">
                    SLK-2291 [41.8 km²]
                  </span>
                </div>

                {/* Drift Path Vectors */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none">
                  {/* Drift Vector Arrow */}
                  <defs>
                    <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#38BDF8"/>
                    </marker>
                  </defs>
                  <path d="M 180 140 Q 210 160 235 180" stroke="#38BDF8" strokeWidth="2" strokeDasharray="3,3" markerEnd="url(#arrow)" />
                  <circle cx="180" cy="140" r="4" fill="#F59E0B" />
                  <text x="140" y="135" fill="#F59E0B" fontSize="10" fontFamily="monospace">Origin (-18h)</text>
                </svg>

                {/* Vessel Target 1 (MT Kaveri Star) */}
                <div className="absolute top-[32%] left-[32%] group cursor-pointer">
                  <div className="w-3 h-3 bg-red-500 rotate-45 border border-white"></div>
                  <div className="absolute top-4 left-0 bg-navy-950/90 text-white text-[10px] font-mono p-1 border border-red-500 rounded whitespace-nowrap z-10 shadow">
                    <p className="font-bold text-red-400">MT KAVERI STAR (92%)</p>
                    <p className="text-gray-300">MMSI: 419008421 | 12.4 kts</p>
                  </div>
                </div>

                {/* Vessel Target 2 (Aegean Trader) */}
                <div className="absolute top-[22%] left-[65%]">
                  <div className="w-2.5 h-2.5 bg-amber-400 rotate-45 border border-white"></div>
                  <div className="absolute top-4 left-0 bg-navy-950/80 text-white text-[9px] font-mono p-1 border border-amber-500/50 rounded whitespace-nowrap">
                    <span>AEGEAN TRADER (74%)</span>
                  </div>
                </div>

                {/* Coordinate Markers & Telemetry */}
                <div className="absolute bottom-2 left-2 bg-navy-950/90 p-2 rounded border border-navy-700 text-[10px] font-mono space-y-0.5 text-gray-300">
                  <div className="text-amber-400 font-semibold">LAT: 22° 28' 14" N | LON: 69° 12' 40" E</div>
                  <div>PASS: Sentinel-1A IW / VV | SENSOR: SAR C-BAND</div>
                  <div>SURFACE CURRENT: 0.82 m/s @ 214° SW</div>
                </div>

                {/* North Compass Arrow */}
                <div className="absolute top-3 right-3 bg-navy-950/80 p-1.5 rounded border border-navy-700 text-gray-300 text-center">
                  <Compass className="w-5 h-5 text-amber-400 mx-auto" />
                  <span className="text-[9px] font-mono font-bold">N</span>
                </div>
              </div>

              {/* Panel Telemetry Footer */}
              <div className="bg-navy-950 p-3 flex justify-between items-center text-xs border-t border-navy-800">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                  <span className="text-gray-300 font-mono text-[11px]">DRIFT MODEL HINDCAST MATCH: 98.4%</span>
                </div>
                <button 
                  onClick={() => onNavigate('dashboard')}
                  className="text-amber-400 hover:text-amber-300 font-semibold text-xs font-mono underline flex items-center gap-1"
                >
                  FULL RECONNAISSANCE &rarr;
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
