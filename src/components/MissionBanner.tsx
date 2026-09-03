import React from 'react';
import { Shield, Radio, CheckCircle, FileCheck } from 'lucide-react';

export const MissionBanner: React.FC = () => {
  return (
    <section className="bg-gov-light border-b border-gov-border py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white border border-gov-border rounded-gov p-6 sm:p-8 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex items-start space-x-4 max-w-3xl">
            <div className="p-3 bg-navy-800 text-white rounded-gov flex-shrink-0">
              <Shield className="w-6 h-6" />
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-navy-800 tracking-tight">
                  National Maritime Environmental Intelligence
                </h2>
                <span className="text-[10px] font-bold uppercase tracking-wider bg-gov-blue text-white px-2 py-0.5 rounded-gov">
                  OFFICIAL MANDATE
                </span>
              </div>
              <p className="text-sm text-gov-muted leading-relaxed">
                Empowering the Indian Coast Guard, Pollution Response Teams, Maritime Board Authorities, 
                and Naval Operations Command with satellite-driven anomaly detection, hydro-meteorological drift 
                reconstruction, and court-admissible vessel attribution evidence reports for statutory enforcement under Marpol 73/78.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-4 border-t md:border-t-0 md:border-l border-gov-border pt-4 md:pt-0 md:pl-6 text-xs text-gov-muted w-full md:w-auto justify-between md:justify-start">
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 font-semibold text-navy-800">
                <CheckCircle className="w-4 h-4 text-emerald-600" />
                <span>SAR Oil Slick Detection</span>
              </div>
              <div className="flex items-center gap-1.5 font-semibold text-navy-800">
                <FileCheck className="w-4 h-4 text-gov-blue" />
                <span>Forensic Vessel Attribution</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
