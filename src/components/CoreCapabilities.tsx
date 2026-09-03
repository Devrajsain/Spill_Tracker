import React from 'react';
import { Satellite, Compass, Anchor, ChevronRight } from 'lucide-react';

interface CoreCapabilitiesProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
}

export const CoreCapabilities: React.FC<CoreCapabilitiesProps> = ({ onNavigate }) => {
  const capabilities = [
    {
      id: 'satellite',
      title: 'Satellite Detection',
      icon: Satellite,
      code: 'SAR-DET-01',
      description: 'Synthetic Aperture Radar (SAR) imagery from Sentinel-1 and optical imagery from Sentinel-2 are automatically ingested and analyzed to identify dark-formation oil slicks regardless of cloud cover or daylight conditions.',
      metrics: ['Synthetic Aperture Radar (SAR)', '10m Spatial Resolution', 'Automated Slick Segmentation']
    },
    {
      id: 'drift',
      title: 'Drift Hindcasting',
      icon: Compass,
      code: 'HYD-HIND-02',
      description: 'High-resolution ocean surface current vectors and ECMWF wind field data are modeled using Lagrangian particle tracking algorithms to reverse-simulate spill transport and pinpoint probable origin coordinates.',
      metrics: ['Lagrangian Backtrack Engine', 'ECMWF & INCOIS Feed', '-48h Origin Simulation']
    },
    {
      id: 'attribution',
      title: 'Vessel Attribution',
      icon: Anchor,
      code: 'AIS-ATTR-03',
      description: 'Historical AIS data streams are spatial-temporally correlated against origin points and drift corridors to score nearby candidate commercial tankers, cargo vessels, and unreported contacts.',
      metrics: ['AIS Track Correlation', 'Course & Speed Anomaly Flags', 'Probabilistic Ranking Engine']
    }
  ];

  return (
    <section className="bg-white py-16 border-b border-gov-border" id="about">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-12 space-y-3">
          <span className="text-xs font-bold uppercase tracking-wider text-gov-blue bg-gov-light border border-gov-border px-3 py-1 rounded-gov">
            SYSTEM ARCHITECTURE
          </span>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-navy-800 tracking-tight">
            Core Operational Capabilities
          </h2>
          <p className="text-sm text-gov-muted">
            End-to-end intelligence framework engineered for national maritime surveillance, environmental law enforcement, and emergency response teams.
          </p>
        </div>

        {/* 3 Equal Bordered Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {capabilities.map((item) => {
            const Icon = item.icon;
            return (
              <div 
                key={item.id}
                className="bg-white border border-gov-border rounded-gov p-6 hover:border-navy-800 hover:-translate-y-1 transition-all duration-200 shadow-sm flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-center justify-between mb-4 pb-3 border-b border-gov-border">
                    <div className="p-2.5 bg-gov-light text-navy-800 border border-gov-border rounded-gov group-hover:bg-navy-800 group-hover:text-white transition-colors">
                      <Icon className="w-6 h-6 stroke-[1.5]" />
                    </div>
                    <span className="text-[11px] font-mono text-gov-muted tracking-wider uppercase font-semibold">
                      {item.code}
                    </span>
                  </div>

                  <h3 className="text-lg font-bold text-navy-800 mb-2 group-hover:text-gov-blue transition-colors">
                    {item.title}
                  </h3>

                  <p className="text-xs text-gov-muted leading-relaxed mb-6">
                    {item.description}
                  </p>
                </div>

                <div>
                  <div className="space-y-1.5 pt-4 border-t border-gov-border">
                    {item.metrics.map((m, idx) => (
                      <div key={idx} className="flex items-center text-[11px] text-gov-text">
                        <span className="w-1.5 h-1.5 rounded-full bg-navy-800 mr-2"></span>
                        <span>{m}</span>
                      </div>
                    ))}
                  </div>

                  <button
                    onClick={() => onNavigate('workflow')}
                    className="mt-6 w-full py-2 px-3 bg-gov-light hover:bg-navy-800 hover:text-white text-navy-800 border border-gov-border rounded-gov text-xs font-semibold uppercase tracking-wider transition-colors flex items-center justify-center gap-1"
                  >
                    <span>View Specifications</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
