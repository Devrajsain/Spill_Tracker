import React from 'react';
import { Shield, ExternalLink, Globe, Lock } from 'lucide-react';

interface FooterProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const Footer: React.FC<FooterProps> = ({ onNavigate, onOpenUpload }) => {
  return (
    <footer className="bg-navy-800 text-white border-t-4 border-navy-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 mb-12">
          {/* Column 1: Brand & Mandate */}
          <div className="md:col-span-5 space-y-4">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-full bg-navy-900 border border-navy-700 flex items-center justify-center text-amber-400">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-xl font-bold tracking-tight font-sans text-white">SlickTrace</h3>
                <p className="text-xs text-gray-300 font-medium">Marine Oil Spill Detection &amp; Vessel Attribution System</p>
              </div>
            </div>

            <p className="text-xs text-gray-300 leading-relaxed pr-4">
              Developed for Maritime Environmental Intelligence and Pollution Response Operations. 
              SlickTrace aggregates satellite SAR observations, MetOcean drift hindcasts, and AIS telemetry 
              to provide real-time monitoring and legal attribution evidence against illegal discharges in Indian territorial and EEZ waters.
            </p>

            <div className="pt-2 flex items-center space-x-3 text-[11px] text-gray-400">
              <span className="flex items-center gap-1">
                <Lock className="w-3 h-3 text-emerald-400" />
                Encrypted Data Protocol
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Globe className="w-3 h-3 text-gov-saffron" />
                NIC Interoperable Architecture
              </span>
            </div>
          </div>

          {/* Column 2: Quick Links */}
          <div className="md:col-span-3 space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-300 border-b border-navy-700 pb-2">
              System Modules
            </h4>
            <ul className="space-y-2 text-xs text-gray-300">
              <li>
                <button onClick={() => onNavigate('home')} className="hover:text-white transition-colors">
                  Home Portal Overview
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('dashboard')} className="hover:text-white transition-colors flex items-center gap-1">
                  <span>Surveillance Dashboard</span>
                  <span className="bg-emerald-950 text-emerald-400 text-[9px] px-1 rounded border border-emerald-800">LIVE</span>
                </button>
              </li>
              <li>
                <button onClick={() => onNavigate('workflow')} className="hover:text-white transition-colors">
                  Forensic Pipeline &amp; Workflow
                </button>
              </li>
              <li>
                <button onClick={onOpenUpload} className="hover:text-white transition-colors">
                  Upload Case Evidence (CSV / SAR)
                </button>
              </li>
              <li>
                <a href="#about" onClick={() => onNavigate('home')} className="hover:text-white transition-colors">
                  System Architecture &amp; MetOcean
                </a>
              </li>
            </ul>
          </div>

          {/* Column 3: Legal & Governance */}
          <div className="md:col-span-4 space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-300 border-b border-navy-700 pb-2">
              Statutory Governance &amp; Compliance
            </h4>
            <p className="text-[11px] text-gray-300 leading-relaxed">
              <strong>Analytical Decision Support Disclaimer:</strong> slicktrace output serves as analytical evidence support for operational authorities. Final enforcement actions, vessel detentions, or legal citations must be verified with physical sampling and secondary Coast Guard reconnaissance.
            </p>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-300 pt-2">
              <a href="#privacy" className="hover:text-white underline">Privacy Policy</a>
              <a href="#accessibility" className="hover:text-white underline">Accessibility Statement</a>
              <a href="#contact" className="hover:text-white underline">Contact Portal Admin</a>
              <a href="#sitemap" className="hover:text-white underline">Site Directory</a>
            </div>
          </div>
        </div>

        {/* Subtle Divider & Final Disclaimer */}
        <div className="border-t border-navy-700 pt-6 flex flex-col sm:flex-row items-center justify-between text-[11px] text-gray-400 gap-4">
          <div>
            <span>Government-style prototype interface for maritime environmental monitoring.</span>
          </div>
          <div className="flex items-center space-x-4">
            <span>© 2026 SlickTrace National Intelligence. All Rights Reserved.</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
