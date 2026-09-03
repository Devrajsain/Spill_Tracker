import React from 'react';
import { CheckCircle2, FileSpreadsheet, MapPin, ShieldCheck, Database, Award } from 'lucide-react';

export const WhySlickTrace: React.FC = () => {
  const features = [
    {
      title: 'Government-ready workflow',
      description: 'Role-based access control, secure local/on-premise deployment options, and seamless integration with existing defense infrastructure.'
    },
    {
      title: 'Satellite-first detection',
      description: 'Automated SAR C-Band Sentinel-1 and optical satellite ingestion guaranteeing operational monitoring regardless of weather or cloud ceiling.'
    },
    {
      title: 'Forensic drift modeling',
      description: 'Lagrangian particle hydrodynamic back-tracking using INCOIS & ECMWF MetOcean feeds to accurately reconstruct spill origin timelines.'
    },
    {
      title: 'AIS-based vessel attribution',
      description: 'Algorithmic correlation of historical AIS trajectories, speed drops, and course deviations to identify non-compliant commercial contacts.'
    },
    {
      title: 'Evidence-oriented reporting',
      description: 'Automated generation of ISO/MARPOL compliant evidence summary briefs formatted for statutory maritime tribunals and coast guard investigations.'
    }
  ];

  return (
    <section className="bg-white py-16 border-b border-gov-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          {/* Left Side: Features List */}
          <div className="lg:col-span-6 space-y-6">
            <div className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-wider text-gov-blue bg-gov-light border border-gov-border px-3 py-1 rounded-gov">
                NATIONAL SURVEILLANCE PLATFORM
              </span>
              <h2 className="text-2xl sm:text-3xl font-extrabold text-navy-800 tracking-tight">
                Why SlickTrace is Engineered for Maritime Security
              </h2>
              <p className="text-sm text-gov-muted">
                Designed to bridge the operational gap between raw Earth-observation telemetry and enforceable legal prosecution against illegal marine discharges.
              </p>
            </div>

            <div className="space-y-4 pt-2">
              {features.map((item, idx) => (
                <div key={idx} className="flex items-start space-x-3.5 p-3 rounded-gov hover:bg-gov-light border border-transparent hover:border-gov-border transition-colors">
                  <div className="p-1 bg-navy-800 text-white rounded mt-0.5 flex-shrink-0">
                    <CheckCircle2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-navy-800">
                      {item.title}
                    </h3>
                    <p className="text-xs text-gov-muted leading-relaxed mt-0.5">
                      {item.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Side: Framed GIS Peninsula Map Graphic */}
          <div className="lg:col-span-6">
            <div className="bg-white border-2 border-navy-800 rounded-gov p-4 shadow-md space-y-3">
              {/* Document Header */}
              <div className="flex items-center justify-between border-b border-gov-border pb-2 text-xs">
                <div className="flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 text-navy-800" />
                  <span className="font-bold text-navy-800 uppercase tracking-wider font-mono">
                    NATIONAL GIS SURVEY MATRIX — RECON 04
                  </span>
                </div>
                <span className="text-[10px] font-mono bg-gov-light border border-gov-border px-2 py-0.5 text-navy-800">
                  DOC # IND-EEZ-2026
                </span>
              </div>

              {/* GIS Map Frame */}
              <div className="relative h-80 bg-navy-950 rounded border border-navy-700 overflow-hidden">
                {/* Latitude/Longitude Grid Overlay */}
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#132845_1px,transparent_1px),linear-gradient(to_bottom,#132845_1px,transparent_1px)] bg-[size:32px_32px]"></div>

                {/* Vector Silhouette of Indian Peninsula */}
                <svg className="absolute inset-0 w-full h-full text-navy-800 fill-navy-800/40 stroke-navy-700" viewBox="0 0 400 350">
                  {/* Simplified Indian Peninsula Coastline */}
                  <path d="M120,40 L280,40 L300,100 L250,220 L200,320 L150,220 L100,100 Z" strokeWidth="1.5" />
                  {/* Exclusive Economic Zone (EEZ) 200 Nautical Mile Outer Boundary */}
                  <path d="M70,20 L330,20 L360,110 L290,260 L200,350 L110,260 L40,110 Z" stroke="#1A3C6E" strokeWidth="1.5" strokeDasharray="4,4" fill="none" />
                </svg>

                {/* Ocean Names Text Labels */}
                <div className="absolute top-1/2 left-4 text-[10px] font-mono font-bold text-navy-700 uppercase tracking-widest -rotate-90">
                  Arabian Sea
                </div>
                <div className="absolute top-1/2 right-4 text-[10px] font-mono font-bold text-navy-700 uppercase tracking-widest rotate-90">
                  Bay of Bengal
                </div>

                {/* Active Incident Markers */}
                {/* Marker 1: Gulf of Kutch */}
                <div className="absolute top-[28%] left-[22%] flex items-center space-x-1.5 bg-red-950/90 text-red-200 border border-red-500 rounded px-1.5 py-0.5 text-[9px] font-mono">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-ping"></span>
                  <span>SLK-2291 (Gulf of Kutch)</span>
                </div>

                {/* Marker 2: Mumbai Offshore */}
                <div className="absolute top-[48%] left-[30%] flex items-center space-x-1.5 bg-amber-950/90 text-amber-200 border border-amber-500 rounded px-1.5 py-0.5 text-[9px] font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                  <span>SLK-2288 (Mumbai High)</span>
                </div>

                {/* Marker 3: Chennai Coast */}
                <div className="absolute top-[65%] left-[68%] flex items-center space-x-1.5 bg-blue-950/90 text-blue-200 border border-blue-500 rounded px-1.5 py-0.5 text-[9px] font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
                  <span>SLK-2274 (Ennore)</span>
                </div>

                {/* Scale & Grid Info */}
                <div className="absolute bottom-2 right-2 bg-navy-950/90 border border-navy-700 text-gray-300 p-1.5 rounded text-[9px] font-mono">
                  <div>EEZ BOUNDARY: 200 NM MONITORED</div>
                  <div>SURVEILLANCE ACCURACY: &lt; 50M</div>
                </div>
              </div>

              {/* GIS Footer Details */}
              <div className="flex items-center justify-between text-[11px] text-gov-muted font-mono pt-1">
                <span>INCOIS OCEAN METRICS: SYNCHRONIZED</span>
                <span className="font-bold text-navy-800">ISRO CARTOSAT READY</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
