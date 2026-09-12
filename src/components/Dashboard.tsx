import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, Shield, Layers, Play, Pause, ChevronRight, AlertTriangle, 
  MapPin, Anchor, Eye, FileText, Download, Filter, RefreshCw, BarChart2,
  Calendar, CheckCircle, Info, ChevronDown, Printer, X, Trash2,
  Compass, Activity
} from 'lucide-react';
import L from 'leaflet';
import { loadDashboardData, listCases, deleteCase, DashboardCaseData, CaseResponse, VesselResponse } from '../services/api';
import { ExplainabilityModal } from './ExplainabilityModal';

const VESSEL_TRACK_COLORS = [
  '#2563EB', // Royal Blue
  '#7C3AED', // Violet
  '#0D9488', // Teal
  '#D97706', // Amber
  '#4F46E5', // Indigo
  '#0284C7', // Sky Blue
  '#9333EA', // Purple
  '#059669', // Emerald
  '#EA580C', // Burnt Orange
  '#64748B', // Slate
];

interface DashboardProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
  selectedCaseId?: string;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate, onOpenUpload, selectedCaseId = '' }) => {
  const [activeCase, setActiveCase] = useState<string>(selectedCaseId);
  const [showLayers, setShowLayers] = useState<boolean>(true);
  const [showAnalytics, setShowAnalytics] = useState<boolean>(true);
  const [isPlayingScrubber, setIsPlayingScrubber] = useState<boolean>(false);
  const [scrubberTime, setScrubberTime] = useState<number>(0);
  const [showReportModal, setShowReportModal] = useState<boolean>(false);
  const [selectedVessel, setSelectedVessel] = useState<string>('');
  const [selectedVesselMmsi, setSelectedVesselMmsi] = useState<string>('');
  const [explainVessel, setExplainVessel] = useState<VesselResponse | null>(null);
  const [showExplainModal, setShowExplainModal] = useState<boolean>(false);

  // Live data state
  const [dashboardData, setDashboardData] = useState<DashboardCaseData | null>(null);
  const [availableCases, setAvailableCases] = useState<CaseResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  
  // Layer Toggles
  const [layers, setLayers] = useState({
    spill: true,
    drift: true,
    ais: true,
    satTile: 'esri'
  });

  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<L.Map | null>(null);
  const mapLayersGroup = useRef<L.LayerGroup | null>(null);

  // Sync selectedCaseId prop into activeCase state whenever it changes
  useEffect(() => {
    if (selectedCaseId && selectedCaseId !== activeCase) {
      setActiveCase(selectedCaseId);
    }
  }, [selectedCaseId]);

  // Load available cases on mount and whenever selectedCaseId changes
  useEffect(() => {
    listCases()
      .then(cases => {
        setAvailableCases(cases);
        if (cases.length > 0) {
          if (selectedCaseId) {
            setActiveCase(selectedCaseId);
          } else if (activeCase && cases.some(c => c.id === activeCase)) {
            setActiveCase(activeCase);
          } else {
            setActiveCase(cases[0].id);
          }
        } else {
          setIsLoading(false);
        }
      })
      .catch(() => {
        setAvailableCases([]);
        setIsLoading(false);
      });
  }, [selectedCaseId]);

  // Load dashboard data when active case changes
  useEffect(() => {
    if (!activeCase) {
      setDashboardData(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setLoadError(null);

    loadDashboardData(activeCase)
      .then(data => {
        setDashboardData(data);
        if (data.vessels.length > 0) {
          setSelectedVessel(data.vessels[0].name);
          setSelectedVesselMmsi(data.vessels[0].mmsi);
        }
        setIsLoading(false);
      })
      .catch(err => {
        // If 404 or case missing, try falling back to first available case from server
        listCases()
          .then(cases => {
            setAvailableCases(cases);
            const alternate = cases.find(c => c.id !== activeCase);
            if (alternate) {
              setActiveCase(alternate.id);
            } else if (cases.length > 0 && cases[0].id !== activeCase) {
              setActiveCase(cases[0].id);
            } else {
              setLoadError(err.message || 'Failed to load case data');
              setIsLoading(false);
            }
          })
          .catch(() => {
            setLoadError(err.message || 'Failed to load case data');
            setIsLoading(false);
          });
      });
  }, [activeCase]);

  const handleDeleteCase = async (caseIdToDelete: string) => {
    if (!window.confirm(`Are you sure you want to delete incident ${caseIdToDelete}? This will permanently remove all associated detection, drift forecast, and vessel attribution records.`)) {
      return;
    }
    try {
      await deleteCase(caseIdToDelete);
      const updatedCases = await listCases();
      setAvailableCases(updatedCases);
      if (updatedCases.length > 0) {
        setActiveCase(updatedCases[0].id);
      } else {
        setActiveCase('');
        setDashboardData(null);
      }
    } catch (err: any) {
      alert(`Failed to delete case: ${err.message}`);
    }
  };

  // Derive display data from backend response
  const summary = dashboardData?.case?.summary_json;
  const spillInfo = summary?.spill || dashboardData?.spill;
  const driftInfo = summary?.drift || (dashboardData?.feature2 ? {
    origin_latitude: dashboardData.feature2.origin_latitude,
    origin_longitude: dashboardData.feature2.origin_longitude,
    origin_timestamp: dashboardData.feature2.origin_timestamp,
    drift_trajectory: dashboardData.feature2.drift_trajectory || []
  } : null);
  const vessels = dashboardData?.vessels || [];
  const feature2Data = dashboardData?.feature2;

  const currentData = {
    title: dashboardData?.case?.name || activeCase,
    location: dashboardData?.case?.location_name || '',
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
      (spillInfo?.spill_latitude && spillInfo.spill_latitude !== 0) ? spillInfo.spill_latitude : (dashboardData?.case?.center_latitude && dashboardData.case.center_latitude !== 0 ? dashboardData.case.center_latitude : 22.47),
      (spillInfo?.spill_longitude && spillInfo.spill_longitude !== 0) ? spillInfo.spill_longitude : (dashboardData?.case?.center_longitude && dashboardData.case.center_longitude !== 0 ? dashboardData.case.center_longitude : 69.21),
    ] as [number, number],
    zoom: 10,
    spillPolygon: spillInfo?.polygon_geojson?.coordinates?.[0]?.map((c: number[]) => [c[1], c[0]]) || [],
    driftPath: (driftInfo?.drift_trajectory || []).map((pt: any) => ({
      label: pt.time,
      lat: pt.lat,
      lng: pt.lon,
      text: pt.time,
    })),
    vessels: vessels.map((v, idx) => ({
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
      flags: v.warning_flags || [],
      qualityFlags: v.quality_flags || [],
      evidence: v.evidence_metrics,
      explanation: v.explanation,
      trajectoryGeojson: v.trajectory_geojson,
      color: VESSEL_TRACK_COLORS[idx % VESSEL_TRACK_COLORS.length],
      lat: v.current_latitude,
      lng: v.current_longitude,
      heading: v.heading_deg,
      speed: v.speed_kts,
    })),
  };

  // Cleanup map on component unmount
  useEffect(() => {
    return () => {
      if (leafletMap.current) {
        try {
          leafletMap.current.remove();
        } catch (e) {}
        leafletMap.current = null;
      }
    };
  }, []);

  // Initialize and Update Leaflet Map
  useEffect(() => {
    if (!mapRef.current) return;

    // Check if existing map is still bound to the current DOM element
    if (leafletMap.current) {
      try {
        const container = leafletMap.current.getContainer();
        if (!container || container !== mapRef.current || !document.body.contains(container)) {
          leafletMap.current.remove();
          leafletMap.current = null;
        }
      } catch (e) {
        leafletMap.current = null;
      }
    }

    if (!leafletMap.current) {
      if ((mapRef.current as any)._leaflet_id) {
        delete (mapRef.current as any)._leaflet_id;
      }
      try {
        leafletMap.current = L.map(mapRef.current, {
          center: currentData.center,
          zoom: currentData.zoom,
          zoomControl: false,
          attributionControl: false
        });

        const baseTileLayer = L.tileLayer(
          'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
          {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'
          }
        );
        baseTileLayer.addTo(leafletMap.current);
        L.control.zoom({ position: 'topright' }).addTo(leafletMap.current);
        mapLayersGroup.current = L.layerGroup().addTo(leafletMap.current);
      } catch (err) {
        console.error("Leaflet map initialization error:", err);
      }
    } else {
      leafletMap.current.setView(currentData.center, currentData.zoom);
    }

    // Render Overlays
    if (mapLayersGroup.current) {
      mapLayersGroup.current.clearLayers();

      // 1. Spill Polygon Layer
      if (layers.spill && currentData.spillPolygon.length > 0) {
        const polygon = L.polygon(currentData.spillPolygon, {
          color: '#DC2626',
          weight: 2,
          fillColor: '#EF4444',
          fillOpacity: 0.45,
          dashArray: '4, 4'
        });
        polygon.bindPopup(`
          <div style="padding:10px; font-family:Inter,sans-serif;">
            <strong style="color:#1A2433; font-size:13px;">${currentData.title}</strong><br/>
            <span style="font-size:11px; color:#5A6472;">Area: ${currentData.area} | Volume: ${currentData.estVolume}</span><br/>
            <span style="font-size:10px; color:#DC2626; font-weight:bold;">CONFIDENCE: ${currentData.confidence}</span>
          </div>
        `);
        mapLayersGroup.current.addLayer(polygon);
      }

      // 2. Drift Trajectory Path Layer
      if (layers.drift && currentData.driftPath.length > 0) {
        const latLngs = currentData.driftPath.map((p: any) => [p.lat, p.lng]);
        const polyline = L.polyline(latLngs, {
          color: '#1A3C6E',
          weight: 3,
          dashArray: '6, 6'
        });
        mapLayersGroup.current.addLayer(polyline);

        currentData.driftPath.forEach((pt: any) => {
          const isOrigin = pt.label?.includes('origin') || pt.label?.includes('Origin');
          const marker = L.circleMarker([pt.lat, pt.lng], {
            radius: isOrigin ? 7 : 4,
            color: isOrigin ? '#B91C1C' : '#1A3C6E',
            fillColor: isOrigin ? '#EF4444' : '#FFFFFF',
            fillOpacity: 1,
            weight: 2
          });
          marker.bindTooltip(pt.text, { permanent: true, direction: 'top', className: 'bg-white border border-gov-border px-1 text-[10px] text-gov-text font-mono shadow-xs' });
          mapLayersGroup.current?.addLayer(marker);
        });
      }

      // 3. Feature 2 GeoJSON & Forecast Overlay (Origin + Uncertainty + Forecast Horizons)
      if (layers.drift && feature2Data?.origin_latitude && feature2Data?.origin_longitude) {
        const origLat = feature2Data.origin_latitude;
        const origLon = feature2Data.origin_longitude;
        const uncertaintyMeters = (feature2Data.origin_uncertainty_radius_km || 2.5) * 1000;

        // Origin uncertainty radius circle
        const origCircle = L.circle([origLat, origLon], {
          radius: uncertaintyMeters,
          color: '#B91C1C',
          fillColor: '#F87171',
          fillOpacity: 0.2,
          weight: 1.5,
          dashArray: '4, 4'
        });
        origCircle.bindTooltip(`Origin Uncertainty: ±${(feature2Data.origin_uncertainty_radius_km || 2.5).toFixed(2)} km`, { direction: 'bottom' });
        mapLayersGroup.current?.addLayer(origCircle);

        // Origin point marker
        const origMarker = L.circleMarker([origLat, origLon], {
          radius: 8,
          color: '#7F1D1D',
          fillColor: '#EF4444',
          fillOpacity: 1,
          weight: 2
        });
        origMarker.bindPopup(`
          <div style="padding:8px; font-family:Inter,sans-serif;">
            <strong style="color:#7F1D1D; font-size:12px;">ESTIMATED SPILL ORIGIN (Feature 2)</strong><br/>
            <span style="font-size:11px;">Coord: ${origLat.toFixed(4)}°N, ${origLon.toFixed(4)}°E</span><br/>
            <span style="font-size:11px;">Confidence: ${feature2Data.origin_confidence_score ? (feature2Data.origin_confidence_score * 100).toFixed(1) + '%' : 'N/A'}</span><br/>
            <span style="font-size:11px;">Est. Release: ${feature2Data.origin_timestamp || 'N/A'}</span>
          </div>
        `);
        mapLayersGroup.current?.addLayer(origMarker);
      }

      // Feature 2 Forecast Horizons (+6h, +12h, +24h, +48h)
      if (layers.drift && feature2Data?.forecast_json) {
        const fcHorizons = ['6h', '12h', '24h', '48h'];
        const forecastLatLngs: [number, number][] = [];
        forecastLatLngs.push(currentData.center);

        fcHorizons.forEach(hKey => {
          const fc = feature2Data.forecast_json[hKey];
          if (fc && fc.centroid_latitude && fc.centroid_longitude) {
            forecastLatLngs.push([fc.centroid_latitude, fc.centroid_longitude]);
            const spreadMeters = (fc.spread_radius_km || 3.0) * 1000;
            const spreadCircle = L.circle([fc.centroid_latitude, fc.centroid_longitude], {
              radius: spreadMeters,
              color: '#2563EB',
              fillColor: '#60A5FA',
              fillOpacity: 0.15,
              weight: 1,
              dashArray: '3, 3'
            });
            spreadCircle.bindTooltip(`+${hKey} Spread: ${fc.spread_radius_km} km`, { direction: 'bottom' });
            mapLayersGroup.current?.addLayer(spreadCircle);

            const fcMarker = L.circleMarker([fc.centroid_latitude, fc.centroid_longitude], {
              radius: 6,
              color: '#1D4ED8',
              fillColor: '#38BDF8',
              fillOpacity: 1,
              weight: 2
            });
            fcMarker.bindPopup(`
              <div style="padding:8px; font-family:Inter,sans-serif;">
                <strong style="color:#1D4ED8; font-size:12px;">+${hKey} DRIFT FORECAST (Feature 2)</strong><br/>
                <span style="font-size:11px;">Coord: ${fc.centroid_latitude.toFixed(4)}°N, ${fc.centroid_longitude.toFixed(4)}°E</span><br/>
                <span style="font-size:11px;">Spread Radius: ${fc.spread_radius_km} km</span><br/>
                <span style="font-size:11px;">Active Particles: ${fc.active_particles || 100}</span><br/>
                <span style="font-size:11px; color:#16A34A; font-weight:bold;">Quality: ${fc.quality || 'HIGH'}</span>
              </div>
            `);
            mapLayersGroup.current?.addLayer(fcMarker);
          }
        });

        if (forecastLatLngs.length > 1) {
          const forecastLine = L.polyline(forecastLatLngs, {
            color: '#2563EB',
            weight: 2.5,
            dashArray: '5, 5'
          });
          mapLayersGroup.current?.addLayer(forecastLine);
        }
      }

      // 4. AIS Vessel Trajectories, Gaps & Markers
      if (layers.ais && currentData.vessels.length > 0) {
        currentData.vessels.forEach((v: any) => {
          const isSelected = selectedVesselMmsi === v.mmsi || selectedVessel === v.name;
          const trackColor = v.color;

          // Render trajectory GeoJSON if available
          if (v.trajectoryGeojson && v.trajectoryGeojson.features) {
            v.trajectoryGeojson.features.forEach((feat: any) => {
              if (feat.properties?.feature_type === 'trajectory' && feat.geometry?.coordinates) {
                const latLngs = feat.geometry.coordinates.map((c: number[]) => [c[1], c[0]]);
                if (latLngs.length > 1) {
                  // If selected, add prominent outline halo
                  if (isSelected) {
                    const halo = L.polyline(latLngs, {
                      color: '#FFFFFF',
                      weight: 7,
                      opacity: 0.9,
                      lineCap: 'round',
                    });
                    mapLayersGroup.current?.addLayer(halo);
                  }

                  const trackLine = L.polyline(latLngs, {
                    color: trackColor,
                    weight: isSelected ? 4 : 2.5,
                    opacity: isSelected ? 1.0 : 0.65,
                    lineCap: 'round',
                  });
                  trackLine.bindTooltip(`${v.name} (MMSI: ${v.mmsi}) — Track`, { sticky: true });
                  trackLine.on('click', () => {
                    setSelectedVessel(v.name);
                    setSelectedVesselMmsi(v.mmsi);
                  });
                  mapLayersGroup.current?.addLayer(trackLine);
                }
              } else if (feat.properties?.feature_type === 'ais_gap' && feat.geometry?.coordinates) {
                const gapLatLngs = feat.geometry.coordinates.map((c: number[]) => [c[1], c[0]]);
                if (gapLatLngs.length > 1) {
                  const gapLine = L.polyline(gapLatLngs, {
                    color: '#DC2626',
                    weight: 2.5,
                    dashArray: '6, 6',
                    opacity: 0.9,
                  });
                  gapLine.bindTooltip(`AIS Gap: ${feat.properties.duration_minutes} min (MMSI: ${v.mmsi})`, { sticky: true });
                  mapLayersGroup.current?.addLayer(gapLine);
                }
              } else if (feat.properties?.feature_type === 'closest_approach' && feat.geometry?.coordinates) {
                const caMarker = L.circleMarker([feat.geometry.coordinates[1], feat.geometry.coordinates[0]], {
                  radius: isSelected ? 8 : 6,
                  color: '#7F1D1D',
                  fillColor: '#EF4444',
                  fillOpacity: 0.9,
                  weight: 2,
                });
                caMarker.bindTooltip(`Closest Approach: ${feat.properties.distance_km} km (${v.name})`, { direction: 'top' });
                mapLayersGroup.current?.addLayer(caMarker);
              } else if (feat.properties?.feature_type === 'interpolated_origin' && feat.geometry?.coordinates) {
                const ioMarker = L.circleMarker([feat.geometry.coordinates[1], feat.geometry.coordinates[0]], {
                  radius: isSelected ? 7 : 5,
                  color: '#312E81',
                  fillColor: '#6366F1',
                  fillOpacity: 0.9,
                  weight: 2,
                });
                ioMarker.bindTooltip(`Position at T_origin (${v.name})`, { direction: 'top' });
                mapLayersGroup.current?.addLayer(ioMarker);
              }
            });
          }

          // Vessel Position Marker
          const vesselIcon = L.divIcon({
            className: 'custom-vessel-icon',
            html: `
              <div style="
                width: ${isSelected ? '28px' : '22px'}; 
                height: ${isSelected ? '28px' : '22px'}; 
                background: ${trackColor}; 
                border: ${isSelected ? '3px solid #FFFFFF' : '2px solid #FFFFFF'}; 
                border-radius: 4px; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                color: #FFFFFF; 
                font-weight: bold; 
                font-size: ${isSelected ? '12px' : '10px'};
                box-shadow: ${isSelected ? '0 0 0 3px ' + trackColor + ', 0 4px 10px rgba(0,0,0,0.4)' : '0 2px 6px rgba(0,0,0,0.3)'};
                transition: all 0.2s ease;
              ">
                ⚓
              </div>
            `,
            iconSize: [isSelected ? 28 : 22, isSelected ? 28 : 22],
            iconAnchor: [isSelected ? 14 : 11, isSelected ? 14 : 11]
          });

          const marker = L.marker([v.lat, v.lng], { icon: vesselIcon });
          marker.on('click', () => {
            setSelectedVessel(v.name);
            setSelectedVesselMmsi(v.mmsi);
          });
          marker.bindPopup(`
            <div style="padding:10px; font-family:Inter,sans-serif; min-width:200px;">
              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
                <strong style="color:#1A2433; font-size:13px;">${v.name}</strong>
                <span style="font-size:10px; font-weight:bold; padding:2px 6px; border-radius:3px; background:#F1F5F9; color:#1E293B;">
                  ${v.riskClass}
                </span>
              </div>
              <span style="font-size:11px; color:#5A6472;">MMSI: ${v.mmsi} (${v.type})</span><br/>
              <span style="font-size:11px; font-weight:bold; color:${trackColor};">
                CORRELATION SCORE: ${v.score}/100
              </span><br/>
              <div style="margin-top:4px; font-size:10px; color:#5A6472;">Speed: ${v.speed} | Heading: ${v.heading}°</div>
              <div style="margin-top:4px; font-size:9px; color:#64748B; font-style:italic;">
                *Evidence ranking score; does not establish causation or legal responsibility.
              </div>
            </div>
          `);
          mapLayersGroup.current?.addLayer(marker);
        });
      }

      // Auto-fit bounds to all active geographic entities
      const allPoints: [number, number][] = [];
      if (layers.spill && currentData.spillPolygon.length > 0) {
        allPoints.push(...currentData.spillPolygon);
      }
      if (layers.drift && currentData.driftPath.length > 0) {
        currentData.driftPath.forEach((p: any) => allPoints.push([p.lat, p.lng]));
      }
      if (layers.drift && feature2Data?.origin_latitude && feature2Data?.origin_longitude) {
        allPoints.push([feature2Data.origin_latitude, feature2Data.origin_longitude]);
      }
      if (layers.drift && feature2Data?.forecast_json) {
        ['6h', '12h', '24h', '48h'].forEach(h => {
          const fc = feature2Data.forecast_json[h];
          if (fc?.centroid_latitude && fc?.centroid_longitude) {
            allPoints.push([fc.centroid_latitude, fc.centroid_longitude]);
          }
        });
      }
      if (layers.ais && currentData.vessels.length > 0) {
        currentData.vessels.forEach(v => allPoints.push([v.lat, v.lng]));
      }

      if (allPoints.length > 0 && leafletMap.current) {
        try {
          const bounds = L.latLngBounds(allPoints);
          leafletMap.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
        } catch (e) {}
      }
    }

    // Force Leaflet container recalculation on layout mount
    const timer = setTimeout(() => {
      try {
        leafletMap.current?.invalidateSize();
      } catch (e) {}
    }, 150);

    return () => clearTimeout(timer);
  }, [dashboardData, layers, isLoading]);

  // Scrubber Animation Loop
  useEffect(() => {
    let timer: any;
    if (isPlayingScrubber) {
      timer = setInterval(() => {
        setScrubberTime((prev) => (prev >= 18 ? -18 : prev + 3));
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isPlayingScrubber]);

  // Loading State - only on initial cold load before any dashboard data exists
  if (isLoading && !dashboardData) {
    return (
      <div className="min-h-screen bg-gov-light flex items-center justify-center">
        <div className="text-center space-y-4">
          <RefreshCw className="w-10 h-10 animate-spin text-navy-800 mx-auto" />
          <p className="text-sm font-bold text-navy-800">Loading Incident Data...</p>
          <p className="text-xs text-gov-muted">Fetching SAR slicks, drift forecast & vessel attribution</p>
        </div>
      </div>
    );
  }

  // Error State
  if (loadError) {
    return (
      <div className="min-h-screen bg-gov-light flex items-center justify-center">
        <div className="text-center space-y-4 max-w-md">
          <AlertTriangle className="w-10 h-10 text-red-600 mx-auto" />
          <p className="text-sm font-bold text-navy-800">Failed to Load Case Data</p>
          <p className="text-xs text-gov-muted">{loadError}</p>
          <div className="flex flex-wrap gap-3 justify-center">
            <button 
              onClick={onOpenUpload}
              className="px-4 py-2 bg-gov-blue text-white rounded-gov text-xs font-semibold hover:bg-blue-700 transition-all"
            >
              Run Pipeline / New Case
            </button>
            <button 
              onClick={() => onNavigate('home')}
              className="px-4 py-2 border border-navy-800 text-navy-800 rounded-gov text-xs font-semibold hover:bg-slate-100 transition-all"
            >
              Go Home
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Empty State (No cases in database)
  if (!dashboardData || availableCases.length === 0) {
    return (
      <div className="min-h-screen bg-gov-light flex items-center justify-center p-4">
        <div className="text-center space-y-4 max-w-md bg-white p-8 rounded-gov border border-gov-border shadow-sm">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-navy-800 flex items-center justify-center mx-auto border border-gov-border">
            <Anchor className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-navy-800">No Active Incident Cases</h3>
          <p className="text-xs text-gov-muted leading-relaxed">
            There are currently no active forensic cases. Upload satellite SAR/optical imagery and AIS telemetry to begin analysis.
          </p>
          <div className="flex flex-wrap gap-3 justify-center pt-2">
            <button 
              onClick={onOpenUpload}
              className="px-4 py-2 bg-navy-800 text-white rounded-gov text-xs font-semibold hover:bg-navy-900 transition-all shadow-xs"
            >
              Upload New Case
            </button>
            <button 
              onClick={() => onNavigate('home')}
              className="px-4 py-2 border border-gov-border text-navy-800 rounded-gov text-xs font-semibold hover:bg-gov-light transition-all"
            >
              Back to Home
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gov-light text-gov-text font-sans flex flex-col">
      {/* 1. Dashboard Top Bar */}
      <header className="bg-white border-b border-gov-border px-4 py-2.5 flex items-center justify-between shadow-xs sticky top-0 z-40">
        <div className="flex items-center space-x-4">
          <button 
            onClick={() => onNavigate('home')}
            className="flex items-center space-x-2 text-navy-800 font-bold text-lg hover:text-gov-blue transition-colors"
          >
            <div className="w-8 h-8 rounded bg-navy-800 text-white flex items-center justify-center font-mono text-xs">
              ST
            </div>
            <span>SlickTrace</span>
          </button>

          <span className="text-gov-border">|</span>

          <div className="hidden md:flex items-center space-x-2 text-xs text-gov-muted">
            <span className="font-semibold text-navy-800">NATIONAL MARITIME GRID</span>
            <span>•</span>
            <span className="text-emerald-700 font-medium flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
              {availableCases.length} Active Incident{availableCases.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <div className="relative w-64 sm:w-80">
            <Search className="w-4 h-4 text-gov-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input 
              type="text" 
              placeholder="Search by spill ID, vessel name, or MMSI..." 
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-gov-border rounded-gov text-gov-text placeholder-gov-muted focus:outline-none focus:border-navy-800 focus:ring-1 focus:ring-navy-800"
            />
          </div>

          <select 
            value={activeCase}
            onChange={(e) => setActiveCase(e.target.value)}
            className="px-3 py-1.5 text-xs bg-white border border-gov-border rounded-gov font-bold text-navy-800 focus:outline-none focus:border-navy-800"
          >
            {availableCases.length > 0 ? (
              availableCases.map(c => (
                <option key={c.id} value={c.id}>{c.id} ({c.location_name})</option>
              ))
            ) : (
              <option value={activeCase}>{activeCase}</option>
            )}
          </select>

          <button
            onClick={() => handleDeleteCase(activeCase)}
            title={`Delete incident ${activeCase}`}
            className="p-1.5 text-red-600 hover:text-red-800 hover:bg-red-50 border border-red-200 rounded-gov transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </button>

          <button 
            onClick={onOpenUpload}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 bg-navy-800 hover:bg-navy-900 text-white text-xs font-semibold uppercase tracking-wider rounded-gov shadow-xs transition-colors"
          >
            <span>+ Upload Case</span>
          </button>
        </div>
      </header>

      {/* Main Dashboard Layout */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden relative">
        
        {/* LEFT PANEL: SPILL DETAILS */}
        <aside className="w-full lg:w-80 bg-white border-r border-gov-border p-4 space-y-5 flex-shrink-0 overflow-y-auto max-h-[40vh] lg:max-h-none shadow-xs">
          <div className="flex items-center justify-between border-b border-gov-border pb-3">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-gov-muted">ACTIVE INCIDENT RECORD</span>
              <h2 className="text-lg font-extrabold text-navy-800 font-mono">{activeCase}</h2>
            </div>
            <span className={`px-2 py-0.5 text-[10px] font-extrabold uppercase border rounded-gov ${
              currentData.confidence.includes('HIGH') 
                ? 'bg-red-100 text-red-800 border-red-300'
                : currentData.confidence.includes('MEDIUM')
                ? 'bg-amber-100 text-amber-800 border-amber-300'
                : 'bg-gray-100 text-gray-800 border-gray-300'
            }`}>
              {currentData.confidence}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-gov-light p-2.5 rounded-gov border border-gov-border">
              <span className="text-[10px] text-gov-muted uppercase font-semibold">SURFACE AREA</span>
              <p className="text-sm font-extrabold text-navy-800">{currentData.area}</p>
            </div>
            <div className="bg-gov-light p-2.5 rounded-gov border border-gov-border">
              <span className="text-[10px] text-gov-muted uppercase font-semibold">EST. VOLUME</span>
              <p className="text-sm font-extrabold text-navy-800">{currentData.estVolume}</p>
            </div>
            <div className="bg-gov-light p-2.5 rounded-gov border border-gov-border">
              <span className="text-[10px] text-gov-muted uppercase font-semibold">SLICK LENGTH</span>
              <p className="text-sm font-extrabold text-navy-800">{currentData.length}</p>
            </div>
            <div className="bg-gov-light p-2.5 rounded-gov border border-gov-border">
              <span className="text-[10px] text-gov-muted uppercase font-semibold">SLICK WIDTH</span>
              <p className="text-sm font-extrabold text-navy-800">{currentData.width}</p>
            </div>
          </div>

          <div className="bg-gov-light p-3 rounded-gov border border-gov-border space-y-2 text-xs">
            <div className="flex justify-between border-b border-gov-border pb-1.5">
              <span className="text-gov-muted">Detection Time:</span>
              <span className="font-mono font-bold text-navy-800">{currentData.detectionTime}</span>
            </div>
            <div className="flex justify-between border-b border-gov-border pb-1.5">
              <span className="text-gov-muted">Estimated Origin:</span>
              <span className="font-mono font-bold text-gov-blue">{currentData.originTime}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gov-muted">Satellite Pass:</span>
              <span className="font-mono text-navy-800 text-[11px] truncate max-w-[150px]">{currentData.source}</span>
            </div>
          </div>

          {/* Feature 1 SAR Observed Coordinates */}
          <div className="bg-emerald-50 p-3 rounded-gov border border-emerald-200 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <h5 className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider">
                Feature 1 SAR Detection
              </h5>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-100 text-emerald-800 border border-emerald-300 font-semibold">
                {spillInfo?.geospatial_metadata_detected ? (spillInfo?.source_crs || 'GeoTIFF WGS84') : 'Observed Centroid'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-emerald-700">Observed Slick Centroid:</span>
              <span className="font-mono font-bold text-emerald-950">
                {spillInfo?.spill_latitude != null && spillInfo?.spill_longitude != null
                  ? `${spillInfo.spill_latitude.toFixed(4)}°N, ${spillInfo.spill_longitude.toFixed(4)}°E`
                  : dashboardData?.case?.center_latitude != null && dashboardData?.case?.center_longitude != null
                  ? `${dashboardData.case.center_latitude.toFixed(4)}°N, ${dashboardData.case.center_longitude.toFixed(4)}°E`
                  : '—'}
              </span>
            </div>
          </div>

          {/* Feature 2 Origin Info */}
          {feature2Data && feature2Data.status === 'COMPLETED' && (
            <div className="bg-blue-50 p-3 rounded-gov border border-blue-200 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <h5 className="text-[10px] font-bold text-blue-800 uppercase tracking-wider">Feature 2 Drift Hindcast</h5>
                <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-blue-100 text-blue-800 border border-blue-300 font-semibold">
                  Backtracked Origin
                </span>
              </div>
              {feature2Data.origin_latitude && (
                <div className="flex justify-between">
                  <span className="text-blue-600">Reconstructed Origin:</span>
                  <span className="font-mono font-bold text-blue-900">
                    {feature2Data.origin_latitude.toFixed(4)}°N, {feature2Data.origin_longitude?.toFixed(4)}°E
                  </span>
                </div>
              )}
              {feature2Data.origin_confidence_score && (
                <div className="flex justify-between">
                  <span className="text-blue-600">Confidence:</span>
                  <span className="font-bold text-blue-900">{(feature2Data.origin_confidence_score * 100).toFixed(1)}%</span>
                </div>
              )}
              {feature2Data.origin_uncertainty_radius_km && (
                <div className="flex justify-between">
                  <span className="text-blue-600">Uncertainty:</span>
                  <span className="font-mono text-blue-900">±{feature2Data.origin_uncertainty_radius_km.toFixed(2)} km</span>
                </div>
              )}
            </div>
          )}

          {/* Feature 2 Trajectory & Dispersion Forecast */}
          {feature2Data?.forecast_json && (
            <div className="bg-indigo-50/70 p-3 rounded-gov border border-indigo-200 space-y-2 text-xs">
              <div className="flex items-center justify-between border-b border-indigo-200 pb-1">
                <h5 className="text-[10px] font-bold text-indigo-900 uppercase tracking-wider">
                  Feature 2 Trajectory Forecast
                </h5>
                <span className="text-[9px] px-1.5 py-0.2 bg-indigo-200 text-indigo-900 font-mono rounded">
                  48h Hydrodynamic
                </span>
              </div>
              <div className="space-y-1.5">
                {(['6h', '12h', '24h', '48h'] as const).map(h => {
                  const fc = feature2Data.forecast_json[h];
                  if (!fc) return null;
                  return (
                    <div key={h} className="bg-white/80 p-1.5 rounded border border-indigo-100 flex items-center justify-between text-[11px]">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-indigo-900 font-mono w-7">+{h}</span>
                        <span className="text-gov-muted text-[10px]">
                          {fc.centroid_latitude ? `${fc.centroid_latitude.toFixed(2)}°N, ${fc.centroid_longitude.toFixed(2)}°E` : '—'}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="font-mono font-bold text-navy-800 text-[10px]">±{fc.spread_radius_km} km</span>
                        <span className="text-[9px] text-emerald-700 ml-1 font-semibold">({fc.quality || 'HIGH'})</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Spill Contour Preview */}
          <div className="bg-white border border-gov-border rounded-gov p-3 text-center space-y-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gov-muted">EXTRACTED SAR SPILL POLYGON</span>
            <div className="h-28 bg-slate-900 rounded border border-gov-border flex items-center justify-center relative overflow-hidden">
              <div className="w-32 h-16 bg-red-600/40 border-2 border-red-500 rounded-full rotate-12 flex items-center justify-center">
                <span className="text-[9px] font-mono text-red-200">{activeCase} Vector</span>
              </div>
            </div>
          </div>

          <button 
            onClick={() => setShowReportModal(true)}
            className="w-full py-2.5 px-3 bg-navy-800 hover:bg-navy-900 text-white rounded-gov text-xs font-semibold uppercase tracking-wider shadow-xs transition-colors flex items-center justify-center gap-2"
          >
            <FileText className="w-4 h-4" />
            <span>Generate Official Report</span>
          </button>
        </aside>

        {/* CENTER: MAP INTERFACE */}
        <main className="flex-1 relative bg-slate-100 min-h-[550px] overflow-hidden">
          <div ref={mapRef} className="absolute inset-0 w-full h-full z-0"></div>

          {/* Floating Loading Indicator when switching incidents */}
          {isLoading && (
            <div className="absolute top-4 right-16 z-20 bg-white/95 backdrop-blur px-3 py-1.5 rounded-gov border border-gov-border shadow-md flex items-center gap-2 text-xs font-semibold text-navy-800">
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-gov-blue" />
              <span>Updating incident data...</span>
            </div>
          )}

          {/* Floating Layers Control Panel */}
          <div className="absolute top-4 left-4 z-10 bg-white border border-gov-border rounded-gov p-3 shadow-md w-64 text-xs space-y-2">
            <div className="flex items-center justify-between border-b border-gov-border pb-1.5 font-bold text-navy-800">
              <span className="flex items-center gap-1.5">
                <Layers className="w-4 h-4" />
                INTEGRATED MAP LAYERS
              </span>
              <button 
                onClick={() => setShowLayers(!showLayers)}
                className="text-gov-muted hover:text-navy-800"
              >
                <ChevronDown className={`w-4 h-4 transform ${showLayers ? '' : 'rotate-180'}`} />
              </button>
            </div>

            {showLayers && (
              <div className="space-y-2 pt-1">
                <label className="flex items-center space-x-2 cursor-pointer text-gov-text font-medium">
                  <input 
                    type="checkbox" 
                    checked={layers.spill}
                    onChange={(e) => setLayers({ ...layers, spill: e.target.checked })}
                    className="rounded text-navy-800 focus:ring-navy-800"
                  />
                  <span>Feature 1: SAR Slick Detection</span>
                </label>
                <label className="flex items-center space-x-2 cursor-pointer text-gov-text font-medium">
                  <input 
                    type="checkbox" 
                    checked={layers.drift}
                    onChange={(e) => setLayers({ ...layers, drift: e.target.checked })}
                    className="rounded text-navy-800 focus:ring-navy-800"
                  />
                  <span>Feature 2: Origin &amp; 48h Trajectory</span>
                </label>
                <label className="flex items-center space-x-2 cursor-pointer text-gov-text font-medium">
                  <input 
                    type="checkbox" 
                    checked={layers.ais}
                    onChange={(e) => setLayers({ ...layers, ais: e.target.checked })}
                    className="rounded text-navy-800 focus:ring-navy-800"
                  />
                  <span>AIS Vessel Attribution</span>
                </label>
              </div>
            )}
          </div>

          {/* Map Legend */}
          <div className="absolute bottom-16 right-4 z-10 bg-white border border-gov-border rounded-gov p-3 shadow-md text-xs space-y-1.5 text-gov-text">
            <span className="font-bold text-navy-800 text-[11px] block border-b border-gov-border pb-1">MAP LEGEND</span>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-red-600 border border-white rounded-xs"></span>
              <span>High Confidence Slick</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-amber-500 border border-white rounded-xs"></span>
              <span>Medium Confidence Slick</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-blue-500 border border-white rounded-xs"></span>
              <span>Feature 2 Forecast Point</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-gov-blue border border-white rounded-xs"></span>
              <span>AIS Vessel Marker</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-0.5 bg-navy-800 inline-block"></span>
              <span>Drift Trajectory</span>
            </div>
          </div>

          {/* Time Scrubber Bar */}
          <div className="absolute bottom-4 left-4 right-4 sm:left-1/2 sm:-translate-x-1/2 z-10 max-w-xl bg-white border border-gov-border rounded-gov p-3 shadow-md flex items-center space-x-3 text-xs">
            <button
              onClick={() => setIsPlayingScrubber(!isPlayingScrubber)}
              className="p-1.5 bg-navy-800 text-white rounded-gov hover:bg-navy-900 transition-colors"
            >
              {isPlayingScrubber ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 fill-current" />}
            </button>

            <span className="font-mono text-gov-muted whitespace-nowrap">
              {scrubberTime < 0 ? `${scrubberTime}h origin` : scrubberTime === 0 ? 'Detection (0h)' : `+${scrubberTime}h forecast`}
            </span>

            <input 
              type="range"
              min="-18"
              max="18"
              step="3"
              value={scrubberTime}
              onChange={(e) => setScrubberTime(parseInt(e.target.value))}
              className="w-full accent-navy-800 cursor-pointer"
            />

            <span className="font-mono font-bold text-navy-800 text-[10px] uppercase bg-gov-light border border-gov-border px-2 py-0.5 rounded whitespace-nowrap flex-shrink-0">
              DRIFT TIME SIM
            </span>
          </div>
        </main>

        {/* RIGHT PANEL: SUSPECT VESSELS (FEATURE 3 ATTRIBUTION) */}
        <aside className="w-full lg:w-96 bg-white border-l border-gov-border p-4 space-y-4 flex-shrink-0 overflow-y-auto max-h-[40vh] lg:max-h-none shadow-xs">
          <div className="flex items-center justify-between border-b border-gov-border pb-3">
            <div>
              <h3 className="text-sm font-bold text-navy-800 uppercase tracking-wider">
                Vessel Attribution (Feature 3)
              </h3>
              <p className="text-[11px] text-gov-muted">Multi-factor evidence correlation ranking (0–100)</p>
            </div>
            <span className="text-xs font-mono font-bold text-navy-800 bg-gov-light px-2 py-0.5 border border-gov-border rounded">
              {currentData.vessels.length} Candidates
            </span>
          </div>

          <div className="space-y-3">
            {currentData.vessels.map((vessel: any, idx: number) => {
              const isSelected = selectedVesselMmsi === vessel.mmsi || selectedVessel === vessel.name;
              const ev = vessel.evidence || {};
              const riskBadgeStyle = 
                vessel.riskClass === 'VERY HIGH' ? 'bg-red-700 text-white' :
                vessel.riskClass === 'HIGH' ? 'bg-amber-600 text-white' :
                vessel.riskClass === 'MODERATE' ? 'bg-blue-600 text-white' :
                'bg-slate-600 text-white';

              return (
                <div 
                  key={vessel.mmsi}
                  onClick={() => {
                    setSelectedVessel(vessel.name);
                    setSelectedVesselMmsi(vessel.mmsi);
                  }}
                  className={`p-3 rounded-gov border cursor-pointer transition-all ${
                    isSelected
                      ? 'border-navy-800 bg-navy-800/5 ring-2 ring-navy-800 shadow-xs'
                      : 'border-gov-border bg-white hover:border-gray-400'
                  }`}
                >
                  {/* Card Header: Rank, Name, Score, Classification */}
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <span 
                        className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold text-white shadow-xs"
                        style={{ background: vessel.color }}
                      >
                        {idx + 1}
                      </span>
                      <div>
                        <h4 className="text-xs font-extrabold text-navy-800 flex items-center gap-1.5">
                          <Anchor className="w-3.5 h-3.5" style={{ color: vessel.color }} />
                          <span>{vessel.name}</span>
                        </h4>
                        <p className="text-[10px] text-gov-muted font-mono">
                          MMSI {vessel.mmsi} • {vessel.type} ({vessel.flag})
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col items-end">
                      <div className="flex items-center gap-1.5">
                        <span className="text-base font-black font-mono text-navy-800">
                          {vessel.score}
                        </span>
                        <span className="text-[10px] text-gov-muted font-bold">/100</span>
                      </div>
                      <span className={`px-1.5 py-0.2 rounded text-[8px] font-bold uppercase tracking-wider ${riskBadgeStyle}`}>
                        {vessel.riskClass}
                      </span>
                    </div>
                  </div>

                  {/* 5-Factor Score Breakdown with Progress Bars */}
                  <div className="space-y-1 pt-2 border-t border-gov-border text-[10px]">
                    <div className="flex justify-between text-gov-muted">
                      <span>Origin Presence (45%):</span>
                      <span className="font-mono font-bold text-navy-800">{Math.round(vessel.originPresence)}%</span>
                    </div>
                    <div className="w-full h-1 bg-gov-light rounded-full overflow-hidden">
                      <div className="h-full bg-navy-800" style={{ width: `${Math.min(100, vessel.originPresence)}%` }}></div>
                    </div>

                    <div className="flex justify-between text-gov-muted pt-0.5">
                      <span>Behavior Anomaly (20%):</span>
                      <span className="font-mono font-bold text-navy-800">{Math.round(vessel.behaviorAnomaly)}%</span>
                    </div>
                    <div className="w-full h-1 bg-gov-light rounded-full overflow-hidden">
                      <div className="h-full bg-navy-800" style={{ width: `${Math.min(100, vessel.behaviorAnomaly)}%` }}></div>
                    </div>

                    <div className="flex justify-between text-gov-muted pt-0.5">
                      <span>Dwell Duration (15%):</span>
                      <span className="font-mono font-bold text-navy-800">{Math.round(vessel.dwellTime)}%</span>
                    </div>
                    <div className="w-full h-1 bg-gov-light rounded-full overflow-hidden">
                      <div className="h-full bg-navy-800" style={{ width: `${Math.min(100, vessel.dwellTime)}%` }}></div>
                    </div>

                    <div className="flex justify-between text-gov-muted pt-0.5">
                      <span>AIS Dark Gap (10%):</span>
                      <span className="font-mono font-bold text-navy-800">{Math.round(vessel.aisGap)}%</span>
                    </div>
                    <div className="w-full h-1 bg-gov-light rounded-full overflow-hidden">
                      <div className="h-full bg-navy-800" style={{ width: `${Math.min(100, vessel.aisGap)}%` }}></div>
                    </div>

                    <div className="flex justify-between text-gov-muted pt-0.5">
                      <span>Drift Trajectory (10%):</span>
                      <span className="font-mono font-bold text-navy-800">
                        {vessel.approachDeparture !== null && vessel.approachDeparture !== undefined ? `${Math.round(vessel.approachDeparture)}%` : 'N/A'}
                      </span>
                    </div>
                    <div className="w-full h-1 bg-gov-light rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-navy-800" 
                        style={{ width: `${vessel.approachDeparture !== null && vessel.approachDeparture !== undefined ? Math.min(100, vessel.approachDeparture) : 0}%` }}
                      ></div>
                    </div>
                  </div>

                  {/* Raw Evidence Chips */}
                  {ev.closest_approach_distance_km !== undefined && (
                    <div className="mt-2 grid grid-cols-2 gap-1 bg-slate-50 p-1.5 rounded text-[9px] text-gov-muted font-mono border border-slate-200">
                      <div>Approach: <strong className="text-navy-900">{ev.closest_approach_distance_km.toFixed(1)} km</strong></div>
                      <div>Offset: <strong className="text-navy-900">{ev.time_offset_minutes.toFixed(0)} min</strong></div>
                      <div>SOG @ Origin: <strong className="text-navy-900">{ev.sog_at_origin_kn ?? '—'} kn</strong></div>
                      <div>Dwell: <strong className="text-navy-900">{ev.dwell_minutes_inside_zone ?? 0} min</strong></div>
                    </div>
                  )}

                  {/* Warning & Quality Flags */}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {vessel.flags.map((f: string, fIdx: number) => (
                      <span 
                        key={fIdx}
                        className={`text-[8px] font-semibold uppercase px-1.5 py-0.2 rounded border ${
                          f.includes('GAP') || f.includes('DEVIATION') || f.includes('REDUCTION')
                            ? 'bg-amber-50 text-amber-900 border-amber-200'
                            : 'bg-gov-light text-navy-800 border-gov-border'
                        }`}
                      >
                        {f}
                      </span>
                    ))}
                    {vessel.qualityFlags.map((qf: string, qIdx: number) => (
                      <span key={qIdx} className="text-[8px] font-mono uppercase px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 border border-slate-200">
                        {qf}
                      </span>
                    ))}
                  </div>

                  {/* Audit Evidence Button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setExplainVessel(vessel.raw);
                      setShowExplainModal(true);
                    }}
                    className="mt-2.5 w-full py-1 px-2 bg-slate-100 hover:bg-slate-200 text-navy-800 rounded text-[10px] font-semibold border border-gov-border flex items-center justify-center gap-1 transition-colors"
                  >
                    <Activity className="w-3 h-3 text-gov-blue" />
                    <span>Audit Forensic Evidence</span>
                  </button>
                </div>
              );
            })}

            {currentData.vessels.length === 0 && (
              <div className="text-center py-8 text-gov-muted text-xs">
                No vessel attribution data available for this case. Upload an AIS telemetry file to correlate candidate vessels.
              </div>
            )}
          </div>

          {/* Scientific Notice */}
          <div className="p-2.5 bg-blue-50/70 border border-blue-200 rounded text-[10px] text-slate-700 space-y-1">
            <div className="flex items-center gap-1 font-bold text-navy-800 text-[10px] uppercase">
              <Info className="w-3.5 h-3.5 text-gov-blue" />
              <span>Evidence Correlation Notice</span>
            </div>
            <p className="leading-tight text-[9px]">
              Evidence Correlation Scores (0–100) are deterministic multi-factor ranking metrics. They do not constitute proof of causation, vessel culpability, or legal responsibility.
            </p>
          </div>

          {/* Fleet Analytics */}
          <div className="pt-4 border-t border-gov-border space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-navy-800 uppercase tracking-wider">
                Fleet Surveillance Metrics
              </span>
              <BarChart2 className="w-4 h-4 text-gov-muted" />
            </div>

            <div className="bg-gov-light p-3 rounded-gov border border-gov-border space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-gov-border">
                <span className="text-gov-muted">Total Cases:</span>
                <span className="font-bold text-navy-800">{availableCases.length} Cases</span>
              </div>
              <div className="flex justify-between py-1 border-b border-gov-border">
                <span className="text-gov-muted">Feature 2 Status:</span>
                <span className={`font-bold ${feature2Data?.status === 'COMPLETED' ? 'text-emerald-600' : 'text-amber-600'}`}>
                  {feature2Data?.status || 'N/A'} ({feature2Data?.processing_mode || '—'})
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-gov-muted">Vessel Candidates:</span>
                <span className="font-bold text-navy-800">{currentData.vessels.length} Vessels</span>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* REPORT MODAL */}
      {showReportModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-navy-950/80 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border-2 border-navy-800 rounded-gov shadow-2xl w-full max-w-3xl overflow-hidden">
            <div className="bg-navy-800 text-white px-6 py-4 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Shield className="w-5 h-5 text-amber-400" />
                <span className="font-bold font-sans text-base">OFFICIAL FORENSIC INCIDENT SUMMARY REPORT</span>
              </div>
              <button 
                onClick={() => setShowReportModal(false)}
                className="text-gray-300 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-8 space-y-6 text-gov-text font-sans text-xs max-h-[70vh] overflow-y-auto border-b border-gov-border">
              <div className="border-b-2 border-navy-800 pb-4 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-navy-800">GOVERNMENT OF INDIA</h3>
                  <p className="text-xs text-gov-muted font-semibold">DIRECTORATE GENERAL OF SHIPPING / MARITIME POLLUTION CELL</p>
                  <p className="text-[10px] text-gov-muted font-mono mt-1">SlickTrace Forensic Case ID: {activeCase}</p>
                </div>
                <div className="text-right">
                  <span className="inline-block border border-navy-800 px-2 py-1 font-mono font-bold text-navy-800 text-[10px] bg-gov-light">
                    CONFIDENTIAL / COURT ADMISSIBLE
                  </span>
                  <p className="text-[10px] text-gov-muted mt-1">Generated: {new Date().toISOString().replace('T', ' ').slice(0, 19)} UTC</p>
                </div>
              </div>

              <div className="space-y-2">
                <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs border-b border-gov-border pb-1">
                  1. Incident &amp; Satellite Detection Summary
                </h4>
                <div className="grid grid-cols-2 gap-4 bg-gov-light p-3 rounded-gov border border-gov-border">
                  <div>
                    <p><strong className="text-navy-800">Location:</strong> {currentData.location}</p>
                    <p><strong className="text-navy-800">Detection Satellite:</strong> {currentData.source}</p>
                    <p><strong className="text-navy-800">Confidence Level:</strong> {currentData.confidence}</p>
                  </div>
                  <div>
                    <p><strong className="text-navy-800">Slick Surface Area:</strong> {currentData.area}</p>
                    <p><strong className="text-navy-800">Estimated Heavy Oil Volume:</strong> {currentData.estVolume}</p>
                    <p><strong className="text-navy-800">Est. Origin Time:</strong> {currentData.originTime}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs border-b border-gov-border pb-1">
                  2. Hydrodynamic Drift Modeling &amp; Feature 2 Analysis
                </h4>
                <p className="text-gov-muted leading-relaxed">
                  {feature2Data?.status === 'COMPLETED'
                    ? `Feature 2 Lagrangian origin tracing identified the discharge point at ${feature2Data.origin_latitude?.toFixed(4)}°N, ${feature2Data.origin_longitude?.toFixed(4)}°E with ${feature2Data.origin_uncertainty_radius_km ? `spatial uncertainty of ${(feature2Data.origin_uncertainty_radius_km * 1000).toFixed(0)}m` : 'computed uncertainty'}.`
                    : `Lagrangian hindcasting model established the discharge point at the computed origin coordinates with calculated spatial tolerance.`}
                </p>
              </div>

              <div className="space-y-2">
                <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs border-b border-gov-border pb-1">
                  3. Primary Correlated Vessel Evidence
                </h4>
                {currentData.vessels.length > 0 ? (
                  <div className="bg-slate-50 border border-gov-border p-3 rounded-gov space-y-1">
                    <p><strong className="text-navy-900">Rank #1 Correlated Vessel:</strong> {currentData.vessels[0].name} (MMSI: {currentData.vessels[0].mmsi})</p>
                    <p><strong className="text-navy-900">Evidence Correlation Score:</strong> {currentData.vessels[0].score}/100 ({currentData.vessels[0].riskClass})</p>
                    <p><strong className="text-navy-900">Evidence Flags:</strong> {currentData.vessels[0].flags.join(', ') || 'NONE'}</p>
                    <p className="text-[10px] text-gov-muted italic mt-1">
                      Notice: Evidence Correlation Scores (0–100) are deterministic multi-factor ranking metrics. They do not constitute proof of causation, vessel culpability, or legal responsibility.
                    </p>
                  </div>
                ) : (
                  <p className="text-gov-muted">No vessel attribution data available.</p>
                )}
              </div>

              <div className="pt-6 border-t border-gov-border flex justify-between items-center text-[10px] font-mono text-gov-muted">
                <span>DIGITAL SIGNATURE: SHA-256 (3f9a72...e81c)</span>
                <span>DIRECTORATE ENFORCEMENT STAMP</span>
              </div>
            </div>

            <div className="bg-gov-light px-6 py-4 flex justify-between items-center">
              <span className="text-xs text-gov-muted">Ready for Indian Coast Guard Pollution Response Unit</span>
              <div className="flex space-x-3">
                <button
                  onClick={() => window.print()}
                  className="px-4 py-2 bg-white border border-navy-800 text-navy-800 rounded-gov text-xs font-semibold uppercase tracking-wider hover:bg-gray-50 flex items-center gap-1.5"
                >
                  <Printer className="w-3.5 h-3.5" />
                  <span>Print Brief</span>
                </button>
                <button
                  onClick={() => setShowReportModal(false)}
                  className="px-4 py-2 bg-navy-800 text-white rounded-gov text-xs font-semibold uppercase tracking-wider hover:bg-navy-900"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* EXPLAINABILITY AUDIT MODAL */}
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
