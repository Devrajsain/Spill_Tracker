import React from 'react';
import { Terminal, Crosshair, Map, ShieldAlert, Cpu, BarChart2 } from 'lucide-react';

interface CoreCapabilitiesProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
}

export const CoreCapabilities: React.FC<CoreCapabilitiesProps> = ({ onNavigate }) => {
  return (
    <section className="bg-navy-900 text-white py-16 border-b border-navy-800" id="about">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-12 space-y-3">
          <div className="flex justify-center gap-2 mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 bg-cyan-900/30 border border-cyan-800/50 px-2 py-1 rounded">
              NTRO SIH26143 RECON DATASET ENGINE
            </span>
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-900/30 border border-emerald-800/50 px-2 py-1 rounded">
              ZENODO SAR + MARINECADASTRE AIS
            </span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            Operational Ocean Surveillance & Attribution Matrix
          </h2>
          <p className="text-sm text-gov-muted/80 leading-relaxed">
            Real-time multi-source oceanic surveillance combining Sentinel-1 synthetic aperture radar (SAR), backward Lagrangian drift hindcasting, and MarineCadastre AIS track correlation.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 font-mono">
          
          {/* Column 1: Command Grid */}
          <div className="bg-[#0b1b2c] border border-[#1a2e44] p-5 rounded-lg">
            <div className="flex items-center gap-2 mb-4 pb-2 border-b border-[#1a2e44]">
              <Terminal className="w-4 h-4 text-cyan-500" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400">Launch Command Grid</h3>
            </div>
            
            <div className="space-y-4 text-[11px] text-gray-300">
              <div>
                <div className="text-white font-bold">SECTOR RECON: ALPHA-09</div>
                <div className="text-cyan-500/70">LAT: 19°24'N • LON: 69°18'E</div>
              </div>
              
              <div className="space-y-2 pt-2 border-t border-[#1a2e44]/50">
                <div className="flex justify-between"><span>Slick Polygon</span><span className="text-emerald-400">ACTIVE</span></div>
                <div className="flex justify-between"><span>Reverse Drift (-18h)</span><span className="text-emerald-400">COMPUTED</span></div>
                <div className="flex justify-between"><span>Forecast (+48h)</span><span className="text-emerald-400">READY</span></div>
                <div className="flex justify-between"><span>AIS Corridors</span><span className="text-emerald-400">MAPPED</span></div>
              </div>

              <div className="pt-3 border-t border-[#1a2e44]/50 space-y-2">
                <div className="bg-[#122338] p-2 rounded">
                  <div className="text-[9px] text-gray-500">INCOIS SURF-CURR FEED:</div>
                  <div className="text-cyan-400 font-bold">0.34 m/s @ 072°</div>
                </div>
                <div className="bg-[#122338] p-2 rounded">
                  <div className="text-[9px] text-gray-500">ERA5 WIND 10M:</div>
                  <div className="text-cyan-400 font-bold">6.2 m/s @ 245°</div>
                </div>
              </div>
              <div className="text-[10px] text-emerald-500 animate-pulse mt-4">
                FRAME REFRESH: REALTIME HINDCAST
              </div>
            </div>
          </div>

          {/* Column 2: Suspect Contact */}
          <div className="bg-[#100713] border border-red-900/40 p-5 rounded-lg relative overflow-hidden">
            <div className="absolute top-0 right-0 w-24 h-24 bg-red-600/10 rounded-full blur-2xl"></div>
            <div className="flex justify-between items-center mb-4 pb-2 border-b border-red-900/40">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-red-500" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-red-400">PRIMARY SUSPECT CONTACT</h3>
              </div>
              <div className="text-xs font-bold bg-red-900/40 text-red-400 px-2 py-0.5 rounded">94.2% SCORE</div>
            </div>

            <div className="space-y-3 text-[11px] text-gray-300">
              <div className="grid grid-cols-2 gap-2">
                <div><span className="block text-[9px] text-red-500/60">VESSEL NAME:</span><span className="text-white font-bold">MT PACIFIC TRADER</span></div>
                <div><span className="block text-[9px] text-red-500/60">MMSI / IMO:</span><span className="text-white">415233000 / 9382104</span></div>
                <div><span className="block text-[9px] text-red-500/60">VESSEL TYPE:</span><span className="text-white">CRUDE OIL TANKER</span></div>
                <div><span className="block text-[9px] text-red-500/60">FLAG / REGISTRY:</span><span className="text-white">PANAMA [PA]</span></div>
              </div>

              <div className="pt-3 border-t border-red-900/30 space-y-2">
                <div className="flex justify-between items-center"><span className="text-red-300">CLOSEST APPROACH:</span><span className="font-bold text-white">1.8 NM @ T-18.4h</span></div>
                <div className="flex justify-between items-center"><span className="text-red-300">SPEED ANOMALY:</span><span className="font-bold text-red-400">13.2 kn → 8.6 kn (-35%)</span></div>
                <div className="flex justify-between items-center"><span className="text-red-300">AIS SILENCE GAP:</span><span className="font-bold text-red-400">48 MINS UNREPORTED</span></div>
              </div>

              <div className="pt-3 border-t border-red-900/30 space-y-1.5">
                <div>
                  <div className="flex justify-between text-[9px] mb-1"><span>Origin Proximity:</span><span className="text-white">96 / 100</span></div>
                  <div className="w-full bg-[#1a0f18] h-1.5 rounded overflow-hidden"><div className="bg-red-500 h-full w-[96%]"></div></div>
                </div>
                <div>
                  <div className="flex justify-between text-[9px] mb-1"><span>Temporal Correlation:</span><span className="text-white">92 / 100</span></div>
                  <div className="w-full bg-[#1a0f18] h-1.5 rounded overflow-hidden"><div className="bg-red-500 h-full w-[92%]"></div></div>
                </div>
                <div>
                  <div className="flex justify-between text-[9px] mb-1"><span>Trajectory Anomaly:</span><span className="text-white">95 / 100</span></div>
                  <div className="w-full bg-[#1a0f18] h-1.5 rounded overflow-hidden"><div className="bg-red-500 h-full w-[95%]"></div></div>
                </div>
              </div>

              <button 
                onClick={() => onNavigate('dashboard')}
                className="w-full mt-4 py-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-900/50 rounded transition-colors uppercase font-bold tracking-wider text-[10px]"
              >
                Inspect Forensic Evidence Dossier
              </button>
            </div>
          </div>

          {/* Column 3: Sensor Metadata */}
          <div className="bg-[#0b1b2c] border border-[#1a2e44] p-5 rounded-lg">
            <div className="flex items-center gap-2 mb-4 pb-2 border-b border-[#1a2e44]">
              <Cpu className="w-4 h-4 text-emerald-500" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-400">SENSOR ACQUISITION METADATA</h3>
            </div>

            <div className="space-y-4 text-[11px] text-gray-300">
              <div className="space-y-3">
                <div><span className="block text-[9px] text-emerald-500/60">SAR Satellite:</span><span className="text-white font-bold">Sentinel-1B C-SAR IW</span></div>
                <div><span className="block text-[9px] text-emerald-500/60">Polarization:</span><span className="text-white">VV + VH Dual-Pol</span></div>
                <div><span className="block text-[9px] text-emerald-500/60">Spatial Resolution:</span><span className="text-white">10.0m / Pixel</span></div>
                <div><span className="block text-[9px] text-emerald-500/60">Hindcast Model:</span><span className="text-white">Lagrangian RK4 3D</span></div>
                <div><span className="block text-[9px] text-emerald-500/60">Dataset Format:</span><span className="text-white">MarineCadastre AIS + Zenodo</span></div>
              </div>

              <div className="mt-6 pt-4 border-t border-[#1a2e44]/50 flex justify-center">
                <BarChart2 className="w-8 h-8 text-[#1a2e44]" />
              </div>
            </div>
          </div>
          
        </div>
      </div>
    </section>
  );
};
