import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, Shield, Layers, Play, Pause, ChevronRight, AlertTriangle, 
  MapPin, Anchor, Eye, FileText, Download, Filter, RefreshCw, BarChart2,
  Calendar, CheckCircle, Info, ChevronDown, Printer, X
} from 'lucide-react';
import L from 'leaflet';

interface DashboardProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
  selectedCaseId?: string;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate, onOpenUpload, selectedCaseId = 'SLK-2291' }) => {
  const [activeCase, setActiveCase] = useState<string>(selectedCaseId);
  const [showLayers, setShowLayers] = useState<boolean>(true);
  const [showAnalytics, setShowAnalytics] = useState<boolean>(true);
  const [isPlayingScrubber, setIsPlayingScrubber] = useState<boolean>(false);
  const [scrubberTime, setScrubberTime] = useState<number>(0); // 0 = detection time, -18 to +18
  const [showReportModal, setShowReportModal] = useState<boolean>(false);
  const [selectedVessel, setSelectedVessel] = useState<string>('MT Kaveri Star');
  
  // Layer Toggles
  const [layers, setLayers] = useState({
    spill: true,
    drift: true,
    ais: true,
    satTile: 'esri' // 'esri' | 'osm' | 'carto'
  });

  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<L.Map | null>(null);
  const mapLayersGroup = useRef<L.LayerGroup | null>(null);

  // Case Datasets
  const caseData: Record<string, any> = {
    'SLK-2291': {
      title: 'Gulf of Kutch Maritime Oil Spill',
      location: 'Gulf of Kutch, Gujarat EEZ',
      confidence: 'HIGH CONFIDENCE',
      area: '41.8 km²',
      length: '16.2 km',
      width: '5.4 km',
      estVolume: '7,350 bbl',
      estAge: '11.4 h',
      originTime: '2026-09-01 17:20:00 UTC',
      detectionTime: '2026-09-02 04:18:00 UTC',
      source: 'Sentinel-1A (IW / VV) — pass 2026-09-02 04:11Z',
      center: [22.47, 69.21],
      zoom: 10,
      spillPolygon: [
        [22.45, 69.18],
        [22.48, 69.25],
        [22.44, 69.28],
        [22.42, 69.20]
      ],
      driftPath: [
        { label: 'Origin (-18h)', lat: 22.38, lng: 68.95, text: '-18h origin' },
        { label: '-12h backtrack', lat: 22.41, lng: 69.02, text: '-12h backtrack' },
        { label: '-6h backtrack', lat: 22.44, lng: 69.10, text: '-6h backtrack' },
        { label: 'Detected (0h)', lat: 22.47, lng: 69.21, text: 'detected' },
        { label: '+6h forecast', lat: 22.50, lng: 69.32, text: '+6h forecast' },
        { label: '+12h forecast', lat: 22.53, lng: 69.43, text: '+12h forecast' }
      ],
      vessels: [
        {
          name: 'MT Kaveri Star',
          mmsi: '419008421',
          type: 'Oil Tanker',
          flag: 'India',
          score: 92,
          proximity: 96,
          trajectory: 98,
          behavioral: 88,
          flags: ['AIS GAP DETECTED', 'NEAR ORIGIN WINDOW', 'COURSE DEVIATION'],
          lat: 22.39,
          lng: 68.97,
          heading: 215,
          speed: '12.4 kts'
        },
        {
          name: 'Aegean Trader',
          mmsi: '636019284',
          type: 'Oil Tanker',
          flag: 'Liberia',
          score: 74,
          proximity: 81,
          trajectory: 72,
          behavioral: 66,
          flags: ['NEAR ORIGIN WINDOW', 'SPEED DROP'],
          lat: 22.42,
          lng: 69.08,
          heading: 180,
          speed: '14.1 kts'
        },
        {
          name: 'Hai Feng 9',
          mmsi: '477553900',
          type: 'Container Cargo',
          flag: 'Hong Kong',
          score: 58,
          proximity: 52,
          trajectory: 48,
          behavioral: 60,
          flags: ['NORMAL TRANSIT'],
          lat: 22.51,
          lng: 69.30,
          heading: 95,
          speed: '16.8 kts'
        }
      ]
    },
    'SLK-2288': {
      title: 'Mumbai Offshore Platform Zone Spill',
      location: 'Bombay High Platform Area',
      confidence: 'MEDIUM CONFIDENCE',
      area: '28.4 km²',
      length: '11.8 km',
      width: '3.9 km',
      estVolume: '4,100 bbl',
      estAge: '8.2 h',
      originTime: '2026-09-01 22:00:00 UTC',
      detectionTime: '2026-09-02 06:12:00 UTC',
      source: 'Sentinel-2 Optical — pass 2026-09-02 06:05Z',
      center: [19.40, 71.33],
      zoom: 10,
      spillPolygon: [
        [19.38, 71.30],
        [19.42, 71.36],
        [19.40, 71.38],
        [19.36, 71.32]
      ],
      driftPath: [
        { label: 'Origin (-12h)', lat: 19.30, lng: 71.20, text: '-12h origin' },
        { label: '-6h backtrack', lat: 19.35, lng: 71.26, text: '-6h backtrack' },
        { label: 'Detected (0h)', lat: 19.40, lng: 71.33, text: 'detected' },
        { label: '+6h forecast', lat: 19.45, lng: 71.40, text: '+6h forecast' }
      ],
      vessels: [
        {
          name: 'Aegean Trader',
          mmsi: '636019284',
          type: 'Oil Tanker',
          flag: 'Liberia',
          score: 88,
          proximity: 90,
          trajectory: 86,
          behavioral: 84,
          flags: ['NEAR ORIGIN WINDOW', 'SPEED DROP'],
          lat: 19.32,
          lng: 71.22,
          heading: 190,
          speed: '10.2 kts'
        },
        {
          name: 'INS Taragiri',
          mmsi: '419000102',
          type: 'Patrol Support',
          flag: 'India',
          score: 35,
          proximity: 40,
          trajectory: 30,
          behavioral: 20,
          flags: ['NAVAL PATROL'],
          lat: 19.44,
          lng: 71.38,
          heading: 270,
          speed: '18.0 kts'
        }
      ]
    }
  };

  const currentData = caseData[activeCase] || caseData['SLK-2291'];

  // Initialize Leaflet Map with Esri World Imagery Basemap
  useEffect(() => {
    if (!mapRef.current) return;

    if (!leafletMap.current) {
      // Create map instance
      leafletMap.current = L.map(mapRef.current, {
        center: currentData.center,
        zoom: currentData.zoom,
        zoomControl: false,
        attributionControl: false
      });

      // Add Esri World Imagery Basemap Tile Layer
      const esriSatellite = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
          maxZoom: 18,
          attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
        }
      );
      esriSatellite.addTo(leafletMap.current);

      // Add Leaflet zoom control to top-right
      L.control.zoom({ position: 'topright' }).addTo(leafletMap.current);

      // Create Layer Group for data overlays
      mapLayersGroup.current = L.layerGroup().addTo(leafletMap.current);
    } else {
      leafletMap.current.setView(currentData.center, currentData.zoom);
    }

    // Render Overlays onto Leaflet Map
    if (mapLayersGroup.current) {
      mapLayersGroup.current.clearLayers();

      // 1. Spill Polygon Layer
      if (layers.spill && currentData.spillPolygon) {
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
      if (layers.drift && currentData.driftPath) {
        const latLngs = currentData.driftPath.map((p: any) => [p.lat, p.lng]);
        const polyline = L.polyline(latLngs, {
          color: '#1A3C6E',
          weight: 3,
          dashArray: '6, 6'
        });
        mapLayersGroup.current.addLayer(polyline);

        // Add markers along drift path
        currentData.driftPath.forEach((pt: any) => {
          const isOrigin = pt.label.includes('Origin');
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

      // 3. AIS Vessel Markers
      if (layers.ais && currentData.vessels) {
        currentData.vessels.forEach((v: any) => {
          const isTopSuspect = v.score >= 80;
          const vesselIcon = L.divIcon({
            className: 'custom-vessel-icon',
            html: `
              <div style="
                width: 24px; 
                height: 24px; 
                background: ${isTopSuspect ? '#DC2626' : '#1A3C6E'}; 
                border: 2px solid #FFFFFF; 
                border-radius: 4px; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                color: #FFFFFF; 
                font-weight: bold; 
                font-size: 11px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.3);
              ">
                ⚓
              </div>
            `,
            iconSize: [24, 24],
            iconAnchor: [12, 12]
          });

          const marker = L.marker([v.lat, v.lng], { icon: vesselIcon });
          marker.bindPopup(`
            <div style="padding:10px; font-family:Inter,sans-serif; min-width:180px;">
              <strong style="color:#1A2433; font-size:13px;">${v.name}</strong><br/>
              <span style="font-size:11px; color:#5A6472;">MMSI: ${v.mmsi} (${v.type})</span><br/>
              <span style="font-size:11px; font-weight:bold; color:${isTopSuspect ? '#DC2626' : '#1A3C6E'};">ATTRIBUTION SCORE: ${v.score}%</span><br/>
              <div style="margin-top:4px; font-size:10px; color:#5A6472;">Speed: ${v.speed} | Heading: ${v.heading}°</div>
            </div>
          `);
          mapLayersGroup.current?.addLayer(marker);
        });
      }
    }
  }, [activeCase, layers]);

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

  return (
    <div className="min-h-screen bg-gov-light text-gov-text font-sans flex flex-col">
      {/* 1. Official Government Dashboard Top Bar (Light Theme) */}
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
              2 Active Incident Grids
            </span>
          </div>
        </div>

        {/* Top Bar Search & Filters (Light Theme Inputs) */}
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
            <option value="SLK-2291">SLK-2291 (Gulf of Kutch)</option>
            <option value="SLK-2288">SLK-2288 (Mumbai Offshore)</option>
          </select>

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
        
        {/* LEFT PANEL: SPILL DETAILS & SENSORS (Light Government Theme) */}
        <aside className="w-full lg:w-80 bg-white border-r border-gov-border p-4 space-y-5 flex-shrink-0 overflow-y-auto max-h-[40vh] lg:max-h-none shadow-xs">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gov-border pb-3">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-gov-muted">ACTIVE INCIDENT RECORD</span>
              <h2 className="text-lg font-extrabold text-navy-800 font-mono">{activeCase}</h2>
            </div>
            <span className="px-2 py-0.5 text-[10px] font-extrabold uppercase bg-red-100 text-red-800 border border-red-300 rounded-gov">
              {currentData.confidence}
            </span>
          </div>

          {/* Incident Telemetry Grid */}
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

          {/* Origin & Detection Metadata */}
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

          {/* Spill Contour Preview (Simplified Graphic) */}
          <div className="bg-white border border-gov-border rounded-gov p-3 text-center space-y-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gov-muted">EXTRACTED SAR SPILL POLYGON</span>
            <div className="h-28 bg-slate-900 rounded border border-gov-border flex items-center justify-center relative overflow-hidden">
              <div className="w-32 h-16 bg-red-600/40 border-2 border-red-500 rounded-full rotate-12 flex items-center justify-center">
                <span className="text-[9px] font-mono text-red-200">SLK-2291 Vector</span>
              </div>
            </div>
          </div>

          {/* Action Button: Export Forensic Summary Brief */}
          <button 
            onClick={() => setShowReportModal(true)}
            className="w-full py-2.5 px-3 bg-navy-800 hover:bg-navy-900 text-white rounded-gov text-xs font-semibold uppercase tracking-wider shadow-xs transition-colors flex items-center justify-center gap-2"
          >
            <FileText className="w-4 h-4" />
            <span>Generate Official Report</span>
          </button>
        </aside>

        {/* CENTER: REAL SATELLITE MAP INTERFACE (Leaflet + Esri World Imagery) */}
        <main className="flex-1 relative bg-slate-200 min-h-[500px]">
          {/* Leaflet Map Div Container */}
          <div ref={mapRef} className="w-full h-full min-h-[500px] z-0"></div>

          {/* Floating Layers Control Panel (Light Theme) */}
          <div className="absolute top-4 left-4 z-10 bg-white border border-gov-border rounded-gov p-3 shadow-md w-56 text-xs space-y-2">
            <div className="flex items-center justify-between border-b border-gov-border pb-1.5 font-bold text-navy-800">
              <span className="flex items-center gap-1.5">
                <Layers className="w-4 h-4" />
                MAP LAYERS
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
                  <span>Spill Layer (Red Polygon)</span>
                </label>
                <label className="flex items-center space-x-2 cursor-pointer text-gov-text font-medium">
                  <input 
                    type="checkbox" 
                    checked={layers.drift}
                    onChange={(e) => setLayers({ ...layers, drift: e.target.checked })}
                    className="rounded text-navy-800 focus:ring-navy-800"
                  />
                  <span>Drift Backtrack Vector</span>
                </label>
                <label className="flex items-center space-x-2 cursor-pointer text-gov-text font-medium">
                  <input 
                    type="checkbox" 
                    checked={layers.ais}
                    onChange={(e) => setLayers({ ...layers, ais: e.target.checked })}
                    className="rounded text-navy-800 focus:ring-navy-800"
                  />
                  <span>AIS Vessel Track Overlay</span>
                </label>
              </div>
            )}
          </div>

          {/* Floating Map Legend (Bottom Right) */}
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
              <span className="w-3 h-3 bg-gov-blue border border-white rounded-xs"></span>
              <span>AIS Vessel Marker</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-0.5 bg-navy-800 inline-block"></span>
              <span>Drift Backtrack Trajectory</span>
            </div>
          </div>

          {/* Floating Time Scrubber Bar (Bottom Center) */}
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

            <span className="font-mono font-bold text-navy-800 text-[10px] uppercase bg-gov-light border border-gov-border px-2 py-0.5 rounded">
              DRIFT TIME SIM
            </span>
          </div>
        </main>

        {/* RIGHT PANEL: SUSPECT VESSELS RANKED (Light Government Theme) */}
        <aside className="w-full lg:w-96 bg-white border-l border-gov-border p-4 space-y-4 flex-shrink-0 overflow-y-auto max-h-[40vh] lg:max-h-none shadow-xs">
          <div className="flex items-center justify-between border-b border-gov-border pb-3">
            <div>
              <h3 className="text-sm font-bold text-navy-800 uppercase tracking-wider">
                Suspect Vessels (Ranked)
              </h3>
              <p className="text-[11px] text-gov-muted">Correlated against drift backtrack &amp; origin window</p>
            </div>
            <span className="text-xs font-mono font-bold text-navy-800 bg-gov-light px-2 py-0.5 border border-gov-border rounded">
              {currentData.vessels ? currentData.vessels.length : 0} Candidates
            </span>
          </div>

          {/* Vessel Cards List */}
          <div className="space-y-3">
            {currentData.vessels && currentData.vessels.map((vessel: any, idx: number) => {
              const isTop = idx === 0;
              return (
                <div 
                  key={vessel.mmsi}
                  onClick={() => setSelectedVessel(vessel.name)}
                  className={`p-3 rounded-gov border cursor-pointer transition-all ${
                    selectedVessel === vessel.name
                      ? 'border-navy-800 bg-navy-800/5 ring-1 ring-navy-800'
                      : 'border-gov-border bg-white hover:border-gray-400'
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                        isTop ? 'bg-red-600 text-white' : 'bg-gov-blue text-white'
                      }`}>
                        {idx + 1}
                      </span>
                      <div>
                        <h4 className="text-xs font-extrabold text-navy-800 flex items-center gap-1">
                          <Anchor className="w-3.5 h-3.5 text-gov-blue" />
                          <span>{vessel.name}</span>
                        </h4>
                        <p className="text-[10px] text-gov-muted font-mono">
                          MMSI {vessel.mmsi} • {vessel.type} ({vessel.flag})
                        </p>
                      </div>
                    </div>

                    {/* Score Badge */}
                    <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center font-bold text-xs ${
                      isTop ? 'border-red-600 text-red-600 bg-red-50' : 'border-gov-blue text-gov-blue bg-blue-50'
                    }`}>
                      {vessel.score}
                    </div>
                  </div>

                  {/* Progress Bars Breakdown */}
                  <div className="space-y-1.5 pt-2 border-t border-gov-border text-[10px]">
                    <div>
                      <div className="flex justify-between text-gov-muted mb-0.5">
                        <span>Proximity to Origin:</span>
                        <span className="font-bold text-navy-800">{vessel.proximity}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-gov-light rounded-full overflow-hidden">
                        <div className="h-full bg-navy-800" style={{ width: `${vessel.proximity}%` }}></div>
                      </div>
                    </div>

                    <div>
                      <div className="flex justify-between text-gov-muted mb-0.5">
                        <span>Trajectory Correlator:</span>
                        <span className="font-bold text-navy-800">{vessel.trajectory}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-gov-light rounded-full overflow-hidden">
                        <div className="h-full bg-navy-800" style={{ width: `${vessel.trajectory}%` }}></div>
                      </div>
                    </div>
                  </div>

                  {/* Warning Flags */}
                  <div className="mt-2.5 flex flex-wrap gap-1">
                    {vessel.flags.map((f: string, fIdx: number) => (
                      <span 
                        key={fIdx}
                        className={`text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded border ${
                          f.includes('GAP') || f.includes('DEVIATION')
                            ? 'bg-red-50 text-red-800 border-red-200'
                            : 'bg-gov-light text-navy-800 border-gov-border'
                        }`}
                      >
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Fleet Analytics Toggle Section */}
          <div className="pt-4 border-t border-gov-border space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-navy-800 uppercase tracking-wider">
                Fleet Surveillance Metrics
              </span>
              <BarChart2 className="w-4 h-4 text-gov-muted" />
            </div>

            <div className="bg-gov-light p-3 rounded-gov border border-gov-border space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-gov-border">
                <span className="text-gov-muted">Detections This Week:</span>
                <span className="font-bold text-navy-800">14 Spills</span>
              </div>
              <div className="flex justify-between py-1 border-b border-gov-border">
                <span className="text-gov-muted">Attribution Accuracy:</span>
                <span className="font-bold text-emerald-600">96.8%</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-gov-muted">Monitored Fleet Records:</span>
                <span className="font-bold text-navy-800">18,600 Vessels</span>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* PRINTABLE OFFICIAL INVESTIGATION SUMMARY REPORT MODAL */}
      {showReportModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-navy-950/80 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border-2 border-navy-800 rounded-gov shadow-2xl w-full max-w-3xl overflow-hidden">
            {/* Modal Header */}
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

            {/* Printable Document Body */}
            <div className="p-8 space-y-6 text-gov-text font-sans text-xs max-h-[70vh] overflow-y-auto border-b border-gov-border">
              {/* Document Header Seal */}
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
                  <p className="text-[10px] text-gov-muted mt-1">Generated: 2026-09-03 08:24:10 IST</p>
                </div>
              </div>

              {/* Section 1: Incident Metadata */}
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

              {/* Section 2: Hydrodynamic Backtrack */}
              <div className="space-y-2">
                <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs border-b border-gov-border pb-1">
                  2. Hydrodynamic Drift Modeling Diagnostics
                </h4>
                <p className="text-gov-muted leading-relaxed">
                  Lagrangian hindcasting using INCOIS surface currents (0.82 m/s @ 214°) and ECMWF wind vectors established the discharge point at <strong>22° 28' 14" N, 69° 12' 40" E</strong> with a spatial tolerance of 850m.
                </p>
              </div>

              {/* Section 3: Suspect Vessel Attribution */}
              <div className="space-y-2">
                <h4 className="font-bold text-navy-800 uppercase tracking-wider text-xs border-b border-gov-border pb-1">
                  3. Primary Suspect Vessel Attribution
                </h4>
                <div className="bg-red-50 border border-red-200 p-3 rounded-gov space-y-1">
                  <p><strong className="text-red-900">Rank #1 Suspect Vessel:</strong> MT Kaveri Star (MMSI: 419008421)</p>
                  <p><strong className="text-red-900">Attribution Probability:</strong> 92% Confidence</p>
                  <p><strong className="text-red-900">Correlated Anomalies:</strong> AIS Transmission Silence Gap (45 minutes during origin window), 4.2 knot speed drop, 18° course deviation.</p>
                </div>
              </div>

              {/* Verification Seal Line */}
              <div className="pt-6 border-t border-gov-border flex justify-between items-center text-[10px] font-mono text-gov-muted">
                <span>DIGITAL SIGNATURE: SHA-256 (3f9a72...e81c)</span>
                <span>DIRECTORATE ENFORCEMENT STAMP</span>
              </div>
            </div>

            {/* Modal Actions */}
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
    </div>
  );
};
