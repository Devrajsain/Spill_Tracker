import React from 'react';
import { Shield, Mail, Map, FileText, ArrowUpRight, Lock, Server } from 'lucide-react';

interface FooterProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const Footer: React.FC<FooterProps> = ({ onNavigate, onOpenUpload }) => {
  return (
    <footer className="bg-navy-900 border-t border-navy-800 text-white pb-12 pt-16 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Top Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-12 lg:gap-8 mb-12 border-b border-navy-800 pb-12">
          
          {/* Brand & Mission Statement (col span 4) */}
          <div className="lg:col-span-5 space-y-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gov-blue/20 rounded border border-gov-blue/30">
                <Shield className="w-6 h-6 text-gov-blue" />
              </div>
              <div>
                <h3 className="text-xl font-bold tracking-tight text-white uppercase">NEERAKSH</h3>
                <p className="text-[10px] font-bold text-gov-blue uppercase tracking-wider">
                  National Maritime Environmental Intelligence Platform
                </p>
              </div>
            </div>
            <p className="text-xs text-gov-muted leading-relaxed">
              Commissioned as a National Technical Research Organisation (NTRO) Smart India Hackathon (SIH26143) operational prototype. NEERAKSH aggregates Sentinel-1 SAR observations, INCOIS ocean currents, ECMWF ERA5 winds, and MarineCadastre AIS telemetry to deliver automated maritime anomaly detection, reverse hydrodynamic origin localization, and statutory legal attribution dossiers.
            </p>
            <div className="flex items-center gap-4 text-[10px] font-mono text-emerald-400/80 pt-4">
              <span className="flex items-center gap-1.5"><Lock className="w-3 h-3" /> AES-256 Encrypted Protocol</span>
              <span className="text-navy-700">•</span>
              <span className="flex items-center gap-1.5"><Server className="w-3 h-3" /> NIC Interoperable Architecture</span>
            </div>
          </div>

          {/* System Modules (col span 3) */}
          <div className="lg:col-span-3 lg:col-start-7">
            <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-5 pb-2 border-b border-navy-800">
              System Modules
            </h4>
            <ul className="space-y-3">
              <li>
                <button onClick={() => onNavigate('home')} className="group flex items-center text-xs text-gov-muted hover:text-white transition-colors">
                  <span className="w-1.5 h-1.5 bg-gov-blue rounded-full mr-3 group-hover:scale-150 transition-transform"></span>
                  Mission Mandate & Doctrine
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('dashboard')} className="group flex items-center text-xs text-gov-muted hover:text-white transition-colors">
                  <span className="w-1.5 h-1.5 bg-gov-blue rounded-full mr-3 group-hover:scale-150 transition-transform"></span>
                  Surveillance Command Grid <span className="ml-2 text-[9px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded border border-red-500/30">LIVE</span>
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('workflow')} className="group flex items-center text-xs text-gov-muted hover:text-white transition-colors">
                  <span className="w-1.5 h-1.5 bg-gov-blue rounded-full mr-3 group-hover:scale-150 transition-transform"></span>
                  5-Stage Forensic Workflow
                </button>
              </li>
              <li>
                <button onClick={onOpenUpload} className="group flex items-center text-xs text-gov-muted hover:text-white transition-colors">
                  <span className="w-1.5 h-1.5 bg-gov-blue rounded-full mr-3 group-hover:scale-150 transition-transform"></span>
                  Evidence Dossier Ingestion
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('home')} className="group flex items-center text-xs text-gov-muted hover:text-white transition-colors">
                  <span className="w-1.5 h-1.5 bg-gov-blue rounded-full mr-3 group-hover:scale-150 transition-transform"></span>
                  Operational Capability Matrix
                </button>
              </li>
            </ul>
          </div>

          {/* Governance & Disclaimer (col span 3) */}
          <div className="lg:col-span-3">
            <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-5 pb-2 border-b border-navy-800">
              Statutory Governance & Compliance
            </h4>
            <div className="bg-navy-800/30 border border-navy-700/50 p-4 rounded text-[11px] text-gov-muted leading-relaxed space-y-2">
              <p className="font-bold text-white flex items-center gap-2">
                <Shield className="w-3.5 h-3.5 text-gov-blue" />
                Analytical Decision Support Disclaimer
              </p>
              <p>
                NEERAKSH provides analytical evidence support. Final enforcement decisions require Coast Guard verification and physical investigation.
              </p>
            </div>
          </div>
        </div>

        {/* Bottom Footer Links */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex flex-wrap items-center justify-center md:justify-start gap-4 sm:gap-6 text-[11px] text-gov-muted">
            <a href="#" className="hover:text-white transition-colors">Privacy Policy</a>
            <span className="hidden sm:inline w-1 h-1 bg-navy-700 rounded-full"></span>
            <a href="#" className="hover:text-white transition-colors">Accessibility Statement</a>
            <span className="hidden sm:inline w-1 h-1 bg-navy-700 rounded-full"></span>
            <a href="#" className="hover:text-white transition-colors">Contact Portal Admin</a>
            <span className="hidden sm:inline w-1 h-1 bg-navy-700 rounded-full"></span>
            <a href="#" className="hover:text-white transition-colors flex items-center gap-1">
              Site Directory <ArrowUpRight className="w-3 h-3" />
            </a>
          </div>

          <div className="text-center md:text-right">
            <p className="text-[11px] text-gov-muted font-semibold mb-1">
              National Maritime Environmental Intelligence Platform • NTRO SIH26143 Prototype
            </p>
            <p className="text-[10px] text-navy-400">
              © 2026 NEERAKSH Intelligence Command. All Rights Reserved.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
};
