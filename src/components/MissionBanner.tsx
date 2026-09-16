import React from 'react';
import { Shield, Radio, CheckCircle, FileCheck, ArrowRight, Target, Activity, Satellite } from 'lucide-react';

export const MissionBanner: React.FC = () => {
  return (
    <section className="bg-gov-light border-b border-gov-border py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-10 space-y-3">
          <span className="text-xs font-bold uppercase tracking-wider text-gov-blue bg-gov-blue/10 border border-gov-blue/20 px-3 py-1 rounded-gov inline-block">
            CORE OPERATIONAL INTELLIGENCE DOCTRINE
          </span>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-navy-800 tracking-tight flex items-center justify-center gap-3 flex-wrap">
            <span>DETECT</span> <ArrowRight className="w-5 h-5 text-gov-muted" /> 
            <span>TRACE</span> <ArrowRight className="w-5 h-5 text-gov-muted" /> 
            <span>ATTRIBUTE</span> <ArrowRight className="w-5 h-5 text-gov-muted" /> 
            <span>FORECAST</span>
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Phase 01 */}
          <div className="bg-white border border-gov-border rounded-gov p-6 shadow-sm flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-start mb-4">
                <span className="text-[10px] font-bold text-gov-muted uppercase tracking-wider">PHASE 01</span>
                <Satellite className="w-5 h-5 text-navy-800" />
              </div>
              <h3 className="text-lg font-bold text-navy-800 mb-1">DETECT</h3>
              <p className="text-[11px] font-bold text-gov-blue mb-3">Sentinel-1 SAR + U-Net AI</p>
              <p className="text-xs text-gov-muted leading-relaxed">
                Autonomous orbital detection of mineral oil slicks using C-Band radar backscatter variance, operating unimpeded by monsoon clouds or darkness.
              </p>
            </div>
            <div className="mt-6 pt-4 border-t border-gov-border flex justify-between items-center text-[10px] font-bold uppercase tracking-wider text-emerald-600">
              <span>STAGE 1 OF 4</span>
              <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3" /> VERIFIED</span>
            </div>
          </div>

          {/* Phase 02 */}
          <div className="bg-white border border-gov-border rounded-gov p-6 shadow-sm flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-start mb-4">
                <span className="text-[10px] font-bold text-gov-muted uppercase tracking-wider">PHASE 02</span>
                <Activity className="w-5 h-5 text-navy-800" />
              </div>
              <h3 className="text-lg font-bold text-navy-800 mb-1">TRACE</h3>
              <p className="text-[11px] font-bold text-gov-blue mb-3">Lagrangian Hindcasting</p>
              <p className="text-xs text-gov-muted leading-relaxed">
                Reverse hydrodynamic modeling coupling INCOIS ocean currents and ERA5 wind fields to pinpoint exact discharge coordinates and timestamps.
              </p>
            </div>
            <div className="mt-6 pt-4 border-t border-gov-border flex justify-between items-center text-[10px] font-bold uppercase tracking-wider text-emerald-600">
              <span>STAGE 2 OF 4</span>
              <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3" /> VERIFIED</span>
            </div>
          </div>

          {/* Phase 03 */}
          <div className="bg-white border border-gov-border rounded-gov p-6 shadow-sm flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-start mb-4">
                <span className="text-[10px] font-bold text-gov-muted uppercase tracking-wider">PHASE 03</span>
                <Target className="w-5 h-5 text-navy-800" />
              </div>
              <h3 className="text-lg font-bold text-navy-800 mb-1">ATTRIBUTE</h3>
              <p className="text-[11px] font-bold text-gov-blue mb-3">Probabilistic AIS Scoring</p>
              <p className="text-xs text-gov-muted leading-relaxed">
                Spatial-temporal matching against historical AIS vessel trajectories, speed drops, course deviations, and AIS transmission silence gaps.
              </p>
            </div>
            <div className="mt-6 pt-4 border-t border-gov-border flex justify-between items-center text-[10px] font-bold uppercase tracking-wider text-emerald-600">
              <span>STAGE 3 OF 4</span>
              <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3" /> VERIFIED</span>
            </div>
          </div>

          {/* Phase 04 */}
          <div className="bg-white border border-gov-border rounded-gov p-6 shadow-sm flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-start mb-4">
                <span className="text-[10px] font-bold text-gov-muted uppercase tracking-wider">PHASE 04</span>
                <Radio className="w-5 h-5 text-navy-800" />
              </div>
              <h3 className="text-lg font-bold text-navy-800 mb-1">FORECAST</h3>
              <p className="text-[11px] font-bold text-gov-blue mb-3">+48h Dispersion Vector</p>
              <p className="text-xs text-gov-muted leading-relaxed">
                Predictive forward trajectory dispersion forecasting informing Coast Guard containment booms, sensitive habitat defense, and cleanup logistics.
              </p>
            </div>
            <div className="mt-6 pt-4 border-t border-gov-border flex justify-between items-center text-[10px] font-bold uppercase tracking-wider text-emerald-600">
              <span>STAGE 4 OF 4</span>
              <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3" /> VERIFIED</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
