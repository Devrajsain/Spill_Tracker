import React from 'react';
import { Shield, Satellite, Compass, Crosshair, FileText, CloudRain } from 'lucide-react';

export const SystemCapabilityMatrix: React.FC = () => {
  const modules = [
    {
      id: '01',
      title: 'DEFENSE ARCHITECTURE',
      subtitle: 'Government-ready',
      description: 'Built for national security operations with role-based access control, cryptographic audit logging, and air-gapped local or secure private cloud deployment protocols.',
      tags: ['RBAC', 'Audit Logs', 'On-prem deployment'],
      icon: Shield
    },
    {
      id: '02',
      title: 'SAR & OPTICAL INGESTION',
      subtitle: 'Satellite-first',
      description: 'Automated satellite pass scheduler and ingestion pipeline for Sentinel-1 Synthetic Aperture Radar and Sentinel-2 multi-spectral observations.',
      tags: ['Sentinel-1', '+ Sentinel-2 ingestion'],
      icon: Satellite
    },
    {
      id: '03',
      title: 'METOCEAN HINDCASTING',
      subtitle: 'Hydrodynamic Model',
      description: 'Lagrangian 3D particle transport simulation coupling INCOIS ocean surface current vectors and ERA5 high-precision marine boundary atmospheric winds.',
      tags: ['INCOIS', '+ ERA5 simulation'],
      icon: Compass
    },
    {
      id: '04',
      title: 'SPATIO-TEMPORAL MATCH',
      subtitle: 'AIS Attribution',
      description: 'Deterministic and probabilistic correlation of historical AIS trajectories, loitering patterns, course deviations, and speed anomalies near reconstructed origin loci.',
      tags: ['Track correlation'],
      icon: Crosshair
    },
    {
      id: '05',
      title: 'STATUTORY DOSSIER',
      subtitle: 'Court-ready Reports',
      description: 'Automated generation of timestamped, tamper-evident forensic intelligence briefs compliant with MARPOL 73/78 for statutory Coast Guard and maritime tribunal action.',
      tags: ['Evidence generation'],
      icon: FileText
    },
    {
      id: '06',
      title: '24/7 ALL-WEATHER RADAR',
      subtitle: 'Weather Independent',
      description: 'Active microwave C-Band radar penetration cuts through dense monsoon cloud decks, atmospheric haze, rain storms, and total darkness without signal degradation.',
      tags: ['SAR through clouds'],
      icon: CloudRain
    }
  ];

  return (
    <section className="bg-white py-16 border-b border-gov-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-12 space-y-3">
          <div className="flex justify-center gap-2 mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gov-blue bg-gov-blue/10 border border-gov-blue/20 px-2 py-1 rounded">
              SYSTEM CAPABILITY MATRIX
            </span>
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 bg-emerald-600/10 border border-emerald-600/20 px-2 py-1 rounded">
              NTRO SIH26143 BENCHMARK
            </span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-navy-800 tracking-tight">
            Why NEERAKSH is Engineered for Maritime Sovereignty
          </h2>
          <p className="text-sm text-gov-muted leading-relaxed">
            Six foundational pillars providing end-to-end intelligence from orbital Earth observation to court-admissible forensic vessel prosecution.
          </p>
          <div className="pt-2 text-xs font-bold text-navy-800 uppercase tracking-widest flex items-center justify-center gap-2">
            SYSTEM READINESS: TRL-7 <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse block"></span> OPERATIONAL PROTOCOL ACTIVE
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {modules.map((mod) => (
            <div key={mod.id} className="bg-gov-light border border-gov-border rounded-gov p-6 hover:border-navy-800 transition-colors shadow-sm">
              <div className="flex justify-between items-start mb-4 pb-4 border-b border-gov-border">
                <div>
                  <span className="text-[10px] font-bold text-gov-muted uppercase tracking-wider block mb-1">MODULE {mod.id}</span>
                  <h3 className="text-sm font-bold text-navy-800">{mod.title}</h3>
                  <span className="text-xs text-gov-blue font-semibold">{mod.subtitle}</span>
                </div>
                <mod.icon className="w-6 h-6 text-navy-800" />
              </div>
              <div className="flex flex-wrap gap-1 mb-4">
                {mod.tags.map(tag => (
                  <span key={tag} className="text-[9px] uppercase tracking-wider font-bold bg-white border border-gov-border text-navy-800 px-2 py-0.5 rounded">
                    {tag}
                  </span>
                ))}
              </div>
              <p className="text-[11px] text-gov-muted leading-relaxed mb-6">
                {mod.description}
              </p>
              <div className="text-[9px] font-bold uppercase tracking-wider text-emerald-600 flex justify-between items-center border-t border-gov-border pt-4">
                <span>NTRO COMPLIANT SPEC</span>
                <span className="flex items-center gap-1">VERIFIED <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 block"></span></span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
