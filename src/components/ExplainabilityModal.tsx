import React from 'react';
import { 
  Shield, X, AlertTriangle, Anchor, Compass, Clock, MapPin, 
  Activity, CheckCircle2, Info, Printer, Download
} from 'lucide-react';
import { VesselResponse } from '../services/api';

interface ExplainabilityModalProps {
  vessel: VesselResponse;
  caseId: string;
  onClose: () => void;
}

export const ExplainabilityModal: React.FC<ExplainabilityModalProps> = ({ vessel, caseId, onClose }) => {
  const ev = vessel.evidence_metrics || {};
  const score = vessel.composite_score ?? vessel.overall_score;
  const riskClass = vessel.risk_class || (score >= 80 ? 'VERY HIGH' : score >= 60 ? 'HIGH' : score >= 30 ? 'MODERATE' : 'LOW');

  const getRiskBadgeClass = (risk: string) => {
    switch (risk) {
      case 'VERY HIGH':
        return 'bg-red-700 text-white border-red-800';
      case 'HIGH':
        return 'bg-amber-600 text-white border-amber-700';
      case 'MODERATE':
        return 'bg-blue-600 text-white border-blue-700';
      default:
        return 'bg-slate-600 text-white border-slate-700';
    }
  };

  const factorBars = [
    { label: 'Origin Presence', score: vessel.origin_presence_score ?? vessel.proximity_score, desc: 'Spatial & temporal overlap with release zone' },
    { label: 'Behavior Anomaly', score: vessel.behavior_anomaly_score ?? vessel.behavioral_score, desc: 'Speed reduction & maneuvers relative to baseline' },
    { label: 'Dwell Time', score: vessel.dwell_time_score ?? 0, desc: 'Duration spent inside/near uncertainty boundary' },
    { label: 'AIS Telemetry Gap', score: vessel.ais_gap_score ?? 0, desc: 'Event-relevant transponder silence intervals' },
    { 
      label: 'Approach / Departure', 
      score: vessel.approach_departure_score, 
      desc: vessel.approach_departure_score !== null && vessel.approach_departure_score !== undefined 
        ? 'Vector alignment with reverse hydrodynamic drift' 
        : 'Reverse drift unavailable (weight redistributed proportionally without penalty)' 
    },
  ];

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-navy-950/80 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border-2 border-navy-800 rounded-gov shadow-2xl w-full max-w-4xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="bg-navy-800 text-white px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Shield className="w-5 h-5 text-amber-400" />
            <div>
              <h2 className="font-bold text-sm tracking-wide uppercase">
                FORENSIC AIS EVIDENCE AUDIT PACKAGE
              </h2>
              <p className="text-[11px] text-gray-300 font-mono">
                Case: {caseId} • Vessel MMSI: {vessel.mmsi} ({vessel.name})
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={() => window.print()} 
              className="text-gray-300 hover:text-white p-1 rounded hover:bg-navy-700 transition-colors"
              title="Print Audit Package"
            >
              <Printer className="w-4 h-4" />
            </button>
            <button 
              onClick={onClose}
              className="text-gray-300 hover:text-white p-1 rounded hover:bg-navy-700 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 text-gov-text font-sans text-xs max-h-[78vh] overflow-y-auto">
          
          {/* Top Summary Banner */}
          <div className="bg-slate-50 border border-gov-border rounded-gov p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-full border-4 border-navy-800 bg-white flex flex-col items-center justify-center shadow-xs">
                <span className="text-xl font-black text-navy-800 font-mono leading-none">{Math.round(score)}</span>
                <span className="text-[9px] uppercase font-bold text-gov-muted">/ 100</span>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-extrabold text-navy-800">{vessel.name}</h3>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${getRiskBadgeClass(riskClass)}`}>
                    {riskClass} CORRELATION
                  </span>
                </div>
                <p className="text-[11px] text-gov-muted font-mono mt-0.5">
                  MMSI: {vessel.mmsi} • Type: {vessel.type} • Flag: {vessel.flag}
                </p>
                <p className="text-[10px] text-gov-muted mt-1">
                  Scoring Formulation: <span className="font-mono font-semibold text-navy-800">{vessel.scoring_mode || 'UNCERTAINTY_AWARE_5_FACTOR'}</span>
                </p>
              </div>
            </div>

            <div className="text-right sm:border-l sm:border-gov-border sm:pl-4 text-[11px] space-y-1">
              <div className="text-gov-muted">Current Telemetry:</div>
              <div className="font-mono font-bold text-navy-800">{vessel.speed_kts} • {vessel.heading_deg}° COG</div>
              <div className="font-mono text-gov-muted text-[10px]">{vessel.current_latitude.toFixed(4)}°N, {vessel.current_longitude.toFixed(4)}°E</div>
            </div>
          </div>

          {/* 5-Factor Score Breakdown */}
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-gov-border pb-1">
              <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-gov-blue" />
                <span>EVIDENCE FACTOR BREAKDOWN (0–100)</span>
              </h4>
              <span className="text-[10px] text-gov-muted">Proportional Weight Allocation</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {factorBars.map((factor, fIdx) => {
                const isNA = typeof factor.score !== 'number';
                const displayScore = typeof factor.score === 'number' ? Math.round(factor.score) : 'N/A';
                const barPercent = typeof factor.score === 'number' ? Math.max(0, Math.min(100, factor.score)) : 0;

                return (
                  <div key={fIdx} className="bg-white border border-gov-border rounded p-3 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-navy-800 text-[11px]">{factor.label}</span>
                      <span className={`font-mono font-bold text-[11px] ${isNA ? 'text-gov-muted' : 'text-navy-800'}`}>
                        {displayScore} {isNA ? '' : '/ 100'}
                      </span>
                    </div>

                    <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                      <div 
                        className={`h-full transition-all ${isNA ? 'bg-slate-300' : 'bg-navy-800'}`} 
                        style={{ width: `${barPercent}%` }}
                      ></div>
                    </div>

                    <p className="text-[10px] text-gov-muted leading-tight">{factor.desc}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Auditable Raw Metrics Grid */}
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-gov-border pb-1">
              <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs flex items-center gap-1.5">
                <Compass className="w-4 h-4 text-gov-blue" />
                <span>AUDITABLE PHYSICAL &amp; KINEMATIC METRICS</span>
              </h4>
              <span className="text-[10px] text-gov-muted font-mono">Precision Geodetic Computations</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">Closest Approach</span>
                <span className="font-mono font-bold text-navy-800 text-sm">
                  {ev.closest_approach_distance_km !== undefined ? `${ev.closest_approach_distance_km.toFixed(2)} km` : '—'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">to origin centroid</span>
              </div>

              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">Release Time Offset</span>
                <span className="font-mono font-bold text-navy-800 text-sm">
                  {ev.time_offset_minutes !== undefined ? `${ev.time_offset_minutes.toFixed(1)} min` : '—'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">from candidate window</span>
              </div>

              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">Uncertainty Zone</span>
                <span className={`font-bold text-sm ${ev.inside_uncertainty_zone ? 'text-red-700' : 'text-navy-800'}`}>
                  {ev.inside_uncertainty_zone ? 'INSIDE ZONE' : 'OUTSIDE ZONE'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">modeled dispersion boundary</span>
              </div>

              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">SOG at Origin</span>
                <span className="font-mono font-bold text-navy-800 text-sm">
                  {ev.sog_at_origin_kn !== undefined && ev.sog_at_origin_kn !== null ? `${ev.sog_at_origin_kn} kn` : '—'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">speed during transit</span>
              </div>

              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">Baseline SOG</span>
                <span className="font-mono font-bold text-navy-800 text-sm">
                  {ev.baseline_median_sog_kn !== undefined && ev.baseline_median_sog_kn !== null ? `${ev.baseline_median_sog_kn} kn` : 'INSUFFICIENT'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">median outer transit</span>
              </div>

              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">Speed Reduction</span>
                <span className="font-mono font-bold text-navy-800 text-sm">
                  {ev.speed_reduction_ratio !== undefined && ev.speed_reduction_ratio !== null ? `${(ev.speed_reduction_ratio * 100).toFixed(0)}%` : '0%'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">relative deceleration</span>
              </div>

              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">Dwell Duration</span>
                <span className="font-mono font-bold text-navy-800 text-sm">
                  {ev.dwell_minutes_inside_zone !== undefined ? `${ev.dwell_minutes_inside_zone.toFixed(0)} min` : '0 min'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">inside uncertainty boundary</span>
              </div>

              <div className="bg-gov-light p-2.5 rounded border border-gov-border">
                <span className="text-[10px] text-gov-muted uppercase block">AIS Dark Gap</span>
                <span className="font-mono font-bold text-navy-800 text-sm">
                  {ev.gap_duration_minutes !== undefined && ev.gap_duration_minutes !== null ? `${ev.gap_duration_minutes.toFixed(0)} min` : 'NONE'}
                </span>
                <span className="text-[9px] text-gov-muted block mt-0.5">near spill origin</span>
              </div>
            </div>
          </div>

          {/* Quality Flags & Provenance */}
          <div className="space-y-2">
            <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs border-b border-gov-border pb-1 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>DATA QUALITY &amp; AUDIT FLAGS</span>
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {(vessel.warning_flags || []).map((wFlag, wIdx) => (
                <span key={wIdx} className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-amber-50 text-amber-900 border border-amber-300">
                  {wFlag}
                </span>
              ))}
              {(vessel.quality_flags || []).map((qFlag, qIdx) => (
                <span key={qIdx} className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-100 text-slate-800 border border-slate-300">
                  {qFlag}
                </span>
              ))}
              {!vessel.warning_flags?.length && !vessel.quality_flags?.length && (
                <span className="text-gov-muted text-[11px] italic">No warning or quality anomaly flags recorded. Nominal AIS quality.</span>
              )}
            </div>
          </div>

          {/* Full Natural Language Forensic Narrative */}
          {vessel.explanation && (
            <div className="space-y-2">
              <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs border-b border-gov-border pb-1">
                EXPLAINABILITY FORENSIC NARRATIVE
              </h4>
              <div className="bg-slate-50 border border-gov-border rounded p-4 text-[11px] text-navy-900 font-mono whitespace-pre-wrap leading-relaxed max-h-56 overflow-y-auto">
                {vessel.explanation}
              </div>
            </div>
          )}

          {/* Mandatory Scientific Disclaimer */}
          <div className="bg-blue-50 border-l-4 border-gov-blue p-3.5 rounded-r text-xs text-navy-900 flex items-start gap-2.5">
            <Info className="w-5 h-5 text-gov-blue shrink-0 mt-0.5" />
            <div>
              <strong className="block font-bold text-navy-900 text-[11px] uppercase tracking-wide">
                Scientific Integrity &amp; Non-Accusatory Disclaimer
              </strong>
              <p className="text-[11px] text-slate-700 mt-0.5 leading-normal">
                Evidence Correlation Scores (0–100) are deterministic multi-factor ranking metrics based on spatio-temporal overlap, kinematics, and telemetry continuity. They do not constitute proof of causation, vessel culpability, or legal responsibility.
              </p>
            </div>
          </div>

        </div>

        {/* Modal Footer */}
        <div className="bg-slate-50 px-6 py-3 border-t border-gov-border flex items-center justify-between text-xs">
          <span className="text-gov-muted font-mono text-[10px]">
            SlickTrace Engine v1.0 • Deterministic Audit Trail
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-navy-800 hover:bg-navy-900 text-white rounded font-semibold text-xs transition-colors"
          >
            Close Audit
          </button>
        </div>
      </div>
    </div>
  );
};
