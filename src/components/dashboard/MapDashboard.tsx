import React, { useState, useEffect } from 'react';
import { loadDashboardData, listCases, deleteCase, CaseResponse, VesselResponse } from '../../services/api';
import { ExplainabilityModal } from '../ExplainabilityModal';
import { RefreshCw, AlertTriangle, Anchor, MapPin, Target, Play, Pause } from 'lucide-react';

import { TopNavbar } from './TopNavbar';
import { LeftContextPanel } from './LeftContextPanel';
import { RightVesselList } from './RightVesselList';
import { VesselPopup } from './VesselPopup';
import { MapCanvas } from './MapCanvas';
import { LayerControl } from './LayerControl';
import { CurrentDashboardData, DashboardEntityState, VesselCandidate } from './types';

const VESSEL_TRACK_COLORS = [
  '#2563EB', '#7C3AED', '#0D9488', '#D97706', '#4F46E5',
  '#0284C7', '#9333EA', '#059669', '#EA580C', '#64748B',
];

interface MapDashboardProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
  selectedCaseId?: string;
}

export const MapDashboard: React.FC<MapDashboardProps> = ({ onNavigate, onOpenUpload, selectedCaseId = '' }) => {
  const [activeCase, setActiveCase] = useState<string>(selectedCaseId);
  const [availableCases, setAvailableCases] = useState<CaseResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [dashboardData, setDashboardData] = useState<any>(null);
  const [currentData, setCurrentData] = useState<CurrentDashboardData | null>(null);

  const [layers, setLayers] = useState({ spill: true, drift: true, ais: true, satTile: 'esri' });
  const [showLayers, setShowLayers] = useState<boolean>(true);

  // Interaction System State
  const [selectedEntity, setSelectedEntity] = useState<DashboardEntityState>({ type: null, id: null });

  const [explainVessel, setExplainVessel] = useState<VesselResponse | null>(null);
  const [showExplainModal, setShowExplainModal] = useState<boolean>(false);

  // Time scrubber state
  const [isPlayingScrubber, setIsPlayingScrubber] = useState<boolean>(false);
  const [scrubberTime, setScrubberTime] = useState<number>(0);

  useEffect(() => {
    if (selectedCaseId && selectedCaseId !== activeCase) {
      setActiveCase(selectedCaseId);
    }
  }, [selectedCaseId]);

  useEffect(() => {
    listCases().then(cases => {
      setAvailableCases(cases);
      if (cases.length > 0) {
        if (selectedCaseId && cases.some(c => c.id === selectedCaseId)) {
          setActiveCase(selectedCaseId);
        } else if (activeCase && cases.some(c => c.id === activeCase)) {
          setActiveCase(activeCase);
        } else {
          setActiveCase(cases[0].id);
        }
      } else {
        setActiveCase('');
        setIsLoading(false);
      }
    }).catch(() => {
      setAvailableCases([]);
      setIsLoading(false);
    });
  }, [selectedCaseId]);

  useEffect(() => {
    if (!activeCase) {
      setDashboardData(null);
      setCurrentData(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setLoadError(null);
    setSelectedEntity({ type: null, id: null }); // Reset selection on case change

    loadDashboardData(activeCase)
      .then(data => {
        setDashboardData(data);

        const summary = data.case?.summary_json;
        const spillInfo = summary?.spill || data.spill;
        const feature2Data = data.feature2;
        const driftInfo = summary?.drift || (feature2Data ? {
          origin_latitude: feature2Data.origin_latitude,
          origin_longitude: feature2Data.origin_longitude,
          origin_timestamp: feature2Data.origin_timestamp,
          drift_trajectory: feature2Data.drift_trajectory || []
        } : null);
        const vessels = data.vessels || [];

        const safeParseJSON = (data: any) => {
          if (typeof data === 'string') {
            try { return JSON.parse(data); } catch (e) { return data; }
          }
          return data;
        };

        const parsedData: CurrentDashboardData = {
          title: data.case?.name || activeCase,
          location: data.case?.location_name || '',
          confidence: spillInfo?.confidence_label || 'PENDING',
          area: spillInfo && spillInfo.area_km2 > 0 ? `${spillInfo.area_km2} km²` : '—',
          length: spillInfo && spillInfo.length_km > 0 ? `${spillInfo.length_km} km` : '—',
          width: spillInfo && spillInfo.width_km > 0 ? `${spillInfo.width_km} km` : '—',
          estVolume: spillInfo && spillInfo.est_volume_bbl > 0 ? `${spillInfo.est_volume_bbl.toLocaleString()} bbl` : '—',
          estAge: '—',
          originTime: driftInfo?.origin_timestamp || feature2Data?.origin_timestamp || '—',
          detectionTime: spillInfo?.detection_timestamp || '—',
          source: spillInfo?.satellite_source || '—',
          center: [
            (spillInfo?.spill_latitude && spillInfo.spill_latitude !== 0) ? spillInfo.spill_latitude : (data.case?.center_latitude && data.case.center_latitude !== 0 ? data.case.center_latitude : 22.47),
            (spillInfo?.spill_longitude && spillInfo.spill_longitude !== 0) ? spillInfo.spill_longitude : (data.case?.center_longitude && data.case.center_longitude !== 0 ? data.case.center_longitude : 69.21),
          ],
          zoom: 10,
          spillPolygon: safeParseJSON(spillInfo?.polygon_geojson)?.coordinates?.[0]?.map((c: number[]) => [c[1], c[0]]) || [],
          driftPath: (safeParseJSON(driftInfo?.drift_trajectory) || []).map((pt: any) => ({
            label: pt.time,
            lat: pt.lat,
            lng: pt.lon,
            text: pt.time,
          })),
          vessels: vessels.map((v: any, idx: number) => ({
            raw: v,
            name: v.name,
            mmsi: v.mmsi,
            type: v.type,
            flag: v.flag,
            score: Math.round(v.composite_score ?? v.overall_score),
            compositeScore: v.composite_score ?? v.overall_score,
            riskClass: v.risk_class || (v.overall_score >= 80 ? 'VERY HIGH' : v.overall_score >= 60 ? 'HIGH' : v.overall_score >= 30 ? 'MODERATE' : 'LOW'),
            scoringMode: v.scoring_mode || 'UNCERTAINTY_AWARE_5_FACTOR',
            originPresence: v.origin_presence_score ?? v.proximity_score,
            behaviorAnomaly: v.behavior_anomaly_score ?? v.behavioral_score,
            dwellTime: v.dwell_time_score ?? 0,
            aisGap: v.ais_gap_score ?? 0,
            approachDeparture: v.approach_departure_score,
            proximity: v.proximity_score,
            trajectory: v.trajectory_score,
            behavioral: v.behavioral_score,
            flags: safeParseJSON(v.warning_flags) || [],
            qualityFlags: safeParseJSON(v.quality_flags) || [],
            evidence: safeParseJSON(v.evidence_metrics),
            explanation: v.explanation,
            trajectoryGeojson: safeParseJSON(v.trajectory_geojson),
            color: VESSEL_TRACK_COLORS[idx % VESSEL_TRACK_COLORS.length],
            lat: v.current_latitude,
            lng: v.current_longitude,
            heading: v.heading_deg,
            speed: v.speed_kts,
          })),
          feature2Data,
          spillInfo,
          activeCase,
        };

        setCurrentData(parsedData);
        setIsLoading(false);
      })
      .catch(err => {
        listCases().then(cases => {
          setAvailableCases(cases);
          const alternate = cases.find(c => c.id !== activeCase);
          if (alternate) setActiveCase(alternate.id);
          else {
            setLoadError(err.message || 'Failed to load case data');
            setIsLoading(false);
          }
        }).catch(() => {
          setLoadError(err.message || 'Failed to load case data');
          setIsLoading(false);
        });
      });
  }, [activeCase]);

  useEffect(() => {
    let timer: any;
    if (isPlayingScrubber) {
      timer = setInterval(() => {
        setScrubberTime((prev) => (prev >= 18 ? -18 : prev + 3));
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isPlayingScrubber]);

  const handleDeleteCase = async (caseIdToDelete: string) => {
    if (!window.confirm(`Are you sure you want to delete incident ${caseIdToDelete}?`)) return;
    try {
      await deleteCase(caseIdToDelete);
      const updatedCases = await listCases();
      setAvailableCases(updatedCases);
      if (updatedCases.length > 0) setActiveCase(updatedCases[0].id);
      else {
        setActiveCase('');
        setDashboardData(null);
        setCurrentData(null);
      }
    } catch (err: any) {
      alert(`Failed to delete case: ${err.message}`);
    }
  };

  const handleSelectEntity = (entity: DashboardEntityState) => {
    setSelectedEntity(entity);
  };

  if (isLoading && !dashboardData) {
    return (
      <div className="min-h-screen bg-gov-light flex items-center justify-center">
        <div className="text-center space-y-4">
          <RefreshCw className="w-10 h-10 animate-spin text-navy-800 mx-auto" />
          <p className="text-sm font-bold text-navy-800">Loading Incident Data...</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="min-h-screen bg-gov-light flex items-center justify-center">
        <div className="text-center space-y-4 max-w-md">
          <AlertTriangle className="w-10 h-10 text-red-600 mx-auto" />
          <p className="text-sm font-bold text-navy-800">Failed to Load Case Data</p>
          <button onClick={onOpenUpload} className="px-4 py-2 bg-gov-blue text-white rounded-gov text-xs">Run Pipeline / New Case</button>
        </div>
      </div>
    );
  }

  if (!dashboardData || availableCases.length === 0) {
    return (
      <div className="min-h-screen bg-gov-light flex items-center justify-center p-4">
        <div className="text-center space-y-4 bg-white p-8 rounded-gov shadow-sm">
          <Anchor className="w-6 h-6 mx-auto" />
          <h3 className="text-base font-bold text-navy-800">No Active Incident Cases</h3>
          <button onClick={onOpenUpload} className="px-4 py-2 bg-navy-800 text-white rounded-gov text-xs">Upload New Case</button>
        </div>
      </div>
    );
  }

  const selectedVesselObj = currentData?.vessels.find(v => v.mmsi === selectedEntity.id) || null;

  return (
    <div className="min-h-screen bg-slate-100 text-gov-text font-sans flex flex-col overflow-hidden">
      <TopNavbar
        onNavigate={onNavigate}
        onOpenUpload={onOpenUpload}
        availableCases={availableCases}
        activeCase={activeCase}
        setActiveCase={setActiveCase}
        handleDeleteCase={handleDeleteCase}
      />

      <main className="flex-1 relative overflow-hidden flex">
        {/* Map fills the entire remaining area */}
        <MapCanvas
          currentData={currentData}
          layers={layers}
          selectedEntity={selectedEntity}
          onSelectEntity={handleSelectEntity}
          isLoading={isLoading}
        />

        <LayerControl
          showLayers={showLayers}
          setShowLayers={setShowLayers}
          layers={layers}
          setLayers={setLayers}
        />

        {/* Sliding left context panel for Spill / Origin details */}
        {currentData && (
          <LeftContextPanel
            selectedEntity={selectedEntity}
            currentData={currentData}
            onGenerateReport={() => { }}
          />
        )}

        {/* Floating Vessel Details Popup */}
        <VesselPopup
          vessel={selectedVesselObj}
          onClose={() => handleSelectEntity({ type: null, id: null })}
          onAuditEvidence={(raw) => {
            setExplainVessel(raw);
            setShowExplainModal(true);
          }}
        />

        {/* Compact Right Panel showing list of vessels */}
        {currentData && currentData.vessels.length > 0 && (
          <RightVesselList
            vessels={currentData.vessels}
            onSelectVessel={(mmsi) => handleSelectEntity({ type: 'vessel', id: mmsi })}
            selectedVesselMmsi={selectedEntity.type === 'vessel' ? selectedEntity.id : null}
          />
        )}

        {/* Time Scrubber Bar removed */}
      </main>

      {showExplainModal && explainVessel && (
        <ExplainabilityModal
          vessel={explainVessel}
          caseId={activeCase}
          onClose={() => setShowExplainModal(false)}
        />
      )}
    </div>
  );
};
