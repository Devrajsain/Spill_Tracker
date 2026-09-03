import React, { useState } from 'react';
import { Upload, X, CheckCircle, AlertTriangle, FileText, Cpu, Compass, Ship, ArrowRight, Play, RefreshCw, Eye, Download } from 'lucide-react';

interface WorkflowUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectCase: (caseId: string) => void;
}

export const WorkflowUploadModal: React.FC<WorkflowUploadModalProps> = ({ isOpen, onClose, onSelectCase }) => {
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [uploadedImageName, setUploadedImageName] = useState<string>('sentinel1_kutch_sar_20260902.tif');
  const [uploadedCsvName, setUploadedCsvName] = useState<string>('ais_vessel_telemetry_gulf_kutch.csv');
  const [selectedPreset, setSelectedPreset] = useState<string>('SLK-2291');

  if (!isOpen) return null;

  const handleSimulatePipeline = () => {
    setIsProcessing(true);
    let step = 1;
    const interval = setInterval(() => {
      step += 1;
      if (step <= 4) {
        setCurrentStep(step);
      } else {
        clearInterval(interval);
        setIsProcessing(false);
        setCurrentStep(4);
      }
    }, 800);
  };

  const presetCases = [
    {
      id: 'SLK-2291',
      name: 'Gulf of Kutch Maritime Disagree Incident',
      location: 'Gujarat Coast (Lat: 22° 28\' N, Lon: 69° 12\' E)',
      img: 'sentinel1_sar_kutch.png',
      csv: 'ais_kutch_tankers_2026.csv',
      confidence: '94.2%',
      area: '41.8 km²',
      topSuspect: 'MT Kaveri Star (MMSI: 419008421)'
    },
    {
      id: 'SLK-2288',
      name: 'Mumbai Offshore Platform Zone Spill',
      location: 'Bombay High Platform (Lat: 19° 24\' N, Lon: 71° 20\' E)',
      img: 'sentinel1_sar_mumbai.png',
      csv: 'ais_mumbai_high_traffic.csv',
      confidence: '88.5%',
      area: '28.4 km²',
      topSuspect: 'Aegean Trader (MMSI: 636019284)'
    },
    {
      id: 'SLK-2274',
      name: 'Ennore Port Chennai Bunkering Slick',
      location: 'Coromandel Coast (Lat: 13° 14\' N, Lon: 80° 20\' E)',
      img: 'sentinel2_optical_ennore.png',
      csv: 'ais_ennore_port_telemetry.csv',
      confidence: '91.0%',
      area: '16.2 km²',
      topSuspect: 'Hai Feng 9 (MMSI: 477553900)'
    }
  ];

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-navy-900/80 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border-2 border-navy-800 rounded-gov shadow-2xl w-full max-w-4xl overflow-hidden">
        {/* Modal Top Header */}
        <div className="bg-navy-800 text-white px-6 py-4 flex items-center justify-between border-b border-navy-700">
          <div className="flex items-center space-x-3">
            <div className="p-1.5 bg-navy-900 rounded text-amber-400 border border-navy-700">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold font-sans">
                Evidence Submission &amp; Forensic Analysis Pipeline
              </h3>
              <p className="text-xs text-gray-300">
                SlickTrace AI Satellite Segmentation &amp; AIS Hydrodynamic Attribution Engine
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-gray-300 hover:text-white p-1 rounded hover:bg-navy-700 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 5-Step Process Bar */}
        <div className="bg-gov-light border-b border-gov-border px-6 py-3">
          <div className="flex items-center justify-between text-xs">
            {[
              { num: 1, label: 'Upload Evidence', icon: Upload },
              { num: 2, label: 'AI Segmentation', icon: Cpu },
              { num: 3, label: 'Drift Backtrack', icon: Compass },
              { num: 4, label: 'AIS Attribution', icon: Ship },
            ].map((s) => (
              <div 
                key={s.num}
                onClick={() => setCurrentStep(s.num)}
                className={`flex items-center space-x-2 cursor-pointer py-1 px-3 rounded-gov border ${
                  currentStep === s.num
                    ? 'bg-navy-800 text-white border-navy-800 font-bold'
                    : currentStep > s.num
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-300 font-medium'
                    : 'bg-white text-gov-muted border-gov-border hover:bg-gray-100'
                }`}
              >
                <span className="w-5 h-5 rounded-full bg-current/20 flex items-center justify-center text-[10px] font-mono">
                  {s.num}
                </span>
                <span className="hidden sm:inline">{s.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Modal Body View */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
          {/* STEP 1: Upload Evidence */}
          {currentStep === 1 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <h4 className="text-base font-bold text-navy-800">
                  Step 1: Upload Satellite Imagery &amp; AIS Telemetry Dataset
                </h4>
                <p className="text-xs text-gov-muted">
                  Drag and drop satellite SAR files (.tif, .png) along with vessel AIS movement records (.csv) containing timestamps, MMSI numbers, and coordinates.
                </p>
              </div>

              {/* Drag & Drop Dual Zones */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Zone 1: Satellite Image */}
                <div className="border-2 border-dashed border-gov-border hover:border-navy-800 rounded-gov p-6 bg-gov-light text-center space-y-3 transition-colors cursor-pointer group">
                  <div className="w-12 h-12 bg-white rounded-full mx-auto flex items-center justify-center border border-gov-border text-navy-800 group-hover:scale-105 transition-transform shadow-sm">
                    <Upload className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-navy-800">Satellite SAR / Optical Image</p>
                    <p className="text-[11px] text-gov-muted mt-0.5">GeoTIFF, PNG, JPEG up to 250MB</p>
                  </div>
                  <div className="pt-2">
                    <span className="inline-block px-3 py-1 bg-white border border-gov-border rounded-gov text-[11px] font-mono text-navy-800 font-semibold shadow-xs">
                      {uploadedImageName}
                    </span>
                  </div>
                </div>

                {/* Zone 2: CSV Data */}
                <div className="border-2 border-dashed border-gov-border hover:border-navy-800 rounded-gov p-6 bg-gov-light text-center space-y-3 transition-colors cursor-pointer group">
                  <div className="w-12 h-12 bg-white rounded-full mx-auto flex items-center justify-center border border-gov-border text-navy-800 group-hover:scale-105 transition-transform shadow-sm">
                    <FileText className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-navy-800">AIS Telemetry (.CSV)</p>
                    <p className="text-[11px] text-gov-muted mt-0.5">Vessel tracks with MMSI, Lat, Lon, SOG, COG</p>
                  </div>
                  <div className="pt-2">
                    <span className="inline-block px-3 py-1 bg-white border border-gov-border rounded-gov text-[11px] font-mono text-navy-800 font-semibold shadow-xs">
                      {uploadedCsvName}
                    </span>
                  </div>
                </div>
              </div>

              {/* Sample Preset Cases Selection */}
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-navy-800 uppercase tracking-wider">
                    Or Select Pre-Loaded Test Case Preset
                  </span>
                  <span className="text-[11px] text-gov-muted">Click any preset to auto-load</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {presetCases.map((preset) => (
                    <div
                      key={preset.id}
                      onClick={() => {
                        setSelectedPreset(preset.id);
                        setUploadedImageName(preset.img);
                        setUploadedCsvName(preset.csv);
                      }}
                      className={`p-3 rounded-gov border text-left cursor-pointer transition-all ${
                        selectedPreset === preset.id
                          ? 'border-navy-800 bg-navy-800/5 ring-1 ring-navy-800'
                          : 'border-gov-border bg-white hover:border-gray-400'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 bg-navy-800 text-white rounded">
                          {preset.id}
                        </span>
                        <span className="text-[10px] text-emerald-700 font-bold">{preset.confidence}</span>
                      </div>
                      <p className="text-xs font-bold text-navy-800 line-clamp-1">{preset.name}</p>
                      <p className="text-[11px] text-gov-muted mt-1">{preset.location}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* STEP 2: AI Analysis Engine */}
          {currentStep === 2 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <h4 className="text-base font-bold text-navy-800">
                  Step 2: Deep Learning Satellite Boundary Segmentation
                </h4>
                <p className="text-xs text-gov-muted">
                  The SlickTrace UNet+ ResNet50 segmentation model has processed the SAR C-Band microwave backscatter gradients.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
                <div className="md:col-span-7 bg-navy-950 rounded-gov p-3 border border-navy-800 relative">
                  <div className="h-64 bg-slate-900 rounded relative overflow-hidden flex items-center justify-center border border-navy-700">
                    {/* Simulated Satellite Image & Overlay */}
                    <div className="absolute inset-0 bg-gradient-to-tr from-slate-950 via-slate-900 to-slate-800 opacity-90"></div>
                    <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:20px_20px] opacity-40"></div>
                    
                    {/* Detected Slick Contour */}
                    <div className="relative w-48 h-24 bg-red-600/30 border-2 border-red-500 rounded-full rotate-12 flex flex-col items-center justify-center p-2 shadow-[0_0_20px_rgba(239,68,68,0.4)]">
                      <span className="text-[10px] font-mono text-red-200 bg-red-950/90 px-1 border border-red-500 rounded font-bold">
                        SLICK CONTOUR IDENTIFIED
                      </span>
                      <span className="text-[9px] text-red-300 font-mono mt-1">41.8 km² area</span>
                    </div>

                    <div className="absolute bottom-2 left-2 bg-navy-950/90 border border-navy-700 text-[10px] font-mono text-gray-300 p-1.5 rounded">
                      <div>Pass: Sentinel-1A (2026-09-02 04:11Z)</div>
                      <div>Mode: IW / VV Polarization</div>
                    </div>
                  </div>
                </div>

                <div className="md:col-span-5 space-y-4">
                  <div className="bg-gov-light border border-gov-border rounded-gov p-4 space-y-3">
                    <h5 className="text-xs font-bold text-navy-800 uppercase tracking-wider">
                      Segmentation Diagnostics
                    </h5>

                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between py-1 border-b border-gov-border">
                        <span className="text-gov-muted">Slick Area:</span>
                        <span className="font-bold text-navy-800">41.8 km²</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gov-border">
                        <span className="text-gov-muted">Detection Confidence:</span>
                        <span className="font-bold text-emerald-600">94.2% (High Confidence)</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gov-border">
                        <span className="text-gov-muted">Est. Heavy Crude Volume:</span>
                        <span className="font-bold text-navy-800">7,350 barrels</span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-gov-muted">Slick Age Estimate:</span>
                        <span className="font-bold text-navy-800">11.4 Hours</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-gov text-xs text-emerald-900 flex items-start space-x-2">
                    <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                    <span>Boundary geometry formatted into GeoJSON polygon for hydrodynamic drift modeling.</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: Environmental Drift Modeling */}
          {currentStep === 3 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <h4 className="text-base font-bold text-navy-800">
                  Step 3: MetOcean Hydrodynamic Drift Reconstruction
                </h4>
                <p className="text-xs text-gov-muted">
                  INCOIS surface ocean currents (0.82 m/s @ 214°) and ECMWF wind field vectors (14.2 kts @ 230°) reverse-simulated over -18h window.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-gov-light border border-gov-border rounded-gov p-4 space-y-3">
                  <h5 className="text-xs font-bold text-navy-800 uppercase tracking-wider">
                    Hydrodynamic Parameters
                  </h5>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-gov-border">
                      <span className="text-gov-muted">MetOcean Source:</span>
                      <span className="font-mono font-bold text-navy-800">INCOIS High-Res Ocean Feed</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gov-border">
                      <span className="text-gov-muted">Wind Drag Drift Coefficient:</span>
                      <span className="font-mono text-navy-800">3.5% (Heavy Oil)</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gov-border">
                      <span className="text-gov-muted">Calculated Origin Coordinates:</span>
                      <span className="font-mono font-bold text-gov-blue">22° 28' 14" N, 69° 12' 40" E</span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-gov-muted">Origin Timestamp (UTC):</span>
                      <span className="font-mono font-bold text-navy-800">2026-09-01 17:20:00 UTC</span>
                    </div>
                  </div>
                </div>

                <div className="bg-navy-950 text-white rounded-gov p-4 border border-navy-800 flex flex-col justify-between">
                  <div className="space-y-2">
                    <div className="flex items-center space-x-2 text-amber-400 font-mono text-xs font-bold">
                      <Compass className="w-4 h-4" />
                      <span>DRIFT TRAJECTORY HINDCAST COMPLETE</span>
                    </div>
                    <p className="text-xs text-gray-300 leading-relaxed">
                      Lagrangian backtrack model successfully generated origin region with a spatial uncertainty radius of 850 meters.
                    </p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-navy-800 text-[11px] font-mono text-emerald-400">
                    STATUS: READY FOR AIS TRACK CROSS-CORRELATION
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 4: AIS Correlation & Attribution */}
          {currentStep === 4 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <h4 className="text-base font-bold text-navy-800">
                  Step 4: AIS Correlation &amp; Suspect Vessel Ranking
                </h4>
                <p className="text-xs text-gov-muted">
                  5 candidate vessels evaluated against origin coordinates, speed drop events, course deviations, and AIS silence gaps.
                </p>
              </div>

              {/* Suspect Vessels Table */}
              <div className="border border-gov-border rounded-gov overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-gov-light text-navy-800 font-bold border-b border-gov-border uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="py-2.5 px-3">Rank / Vessel</th>
                      <th className="py-2.5 px-3">MMSI / Type</th>
                      <th className="py-2.5 px-3">Proximity</th>
                      <th className="py-2.5 px-3">Trajectory</th>
                      <th className="py-2.5 px-3">Anomalies</th>
                      <th className="py-2.5 px-3 text-right">Score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gov-border bg-white">
                    <tr className="bg-red-50/50">
                      <td className="py-3 px-3 font-bold text-navy-800 flex items-center space-x-2">
                        <span className="w-5 h-5 rounded-full bg-red-600 text-white flex items-center justify-center text-[10px]">1</span>
                        <span>MT Kaveri Star</span>
                      </td>
                      <td className="py-3 px-3 font-mono text-gov-muted">419008421 (Oil Tanker)</td>
                      <td className="py-3 px-3 font-mono text-navy-800">0.4 km @ origin</td>
                      <td className="py-3 px-3 font-mono text-navy-800">98% match</td>
                      <td className="py-3 px-3">
                        <span className="inline-block text-[9px] font-semibold bg-red-100 text-red-800 px-1.5 py-0.5 rounded border border-red-200">
                          AIS Gap 45m + Speed Drop
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right font-extrabold text-red-600 text-sm">
                        92 / 100
                      </td>
                    </tr>

                    <tr>
                      <td className="py-3 px-3 font-bold text-navy-800 flex items-center space-x-2">
                        <span className="w-5 h-5 rounded-full bg-amber-500 text-white flex items-center justify-center text-[10px]">2</span>
                        <span>Aegean Trader</span>
                      </td>
                      <td className="py-3 px-3 font-mono text-gov-muted">636019284 (Oil Tanker)</td>
                      <td className="py-3 px-3 font-mono text-navy-800">3.2 km @ origin</td>
                      <td className="py-3 px-3 font-mono text-navy-800">72% match</td>
                      <td className="py-3 px-3">
                        <span className="inline-block text-[9px] font-semibold bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded border border-amber-200">
                          Near Origin Window
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right font-bold text-amber-600">
                        74 / 100
                      </td>
                    </tr>

                    <tr>
                      <td className="py-3 px-3 font-bold text-navy-800 flex items-center space-x-2">
                        <span className="w-5 h-5 rounded-full bg-slate-400 text-white flex items-center justify-center text-[10px]">3</span>
                        <span>Hai Feng 9</span>
                      </td>
                      <td className="py-3 px-3 font-mono text-gov-muted">477553900 (Container)</td>
                      <td className="py-3 px-3 font-mono text-navy-800">8.1 km @ origin</td>
                      <td className="py-3 px-3 font-mono text-navy-800">54% match</td>
                      <td className="py-3 px-3 text-gov-muted text-[10px]">Normal Transit</td>
                      <td className="py-3 px-3 text-right font-bold text-gov-muted">
                        58 / 100
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Modal Bottom Footer Actions */}
        <div className="bg-gov-light px-6 py-4 border-t border-gov-border flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-xs text-gov-muted flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>Case ID: <strong>{selectedPreset}</strong> | Data verified against ISRO / MetOcean</span>
          </div>

          <div className="flex items-center space-x-3 w-full sm:w-auto">
            {currentStep === 1 ? (
              <button
                onClick={handleSimulatePipeline}
                disabled={isProcessing}
                className="w-full sm:w-auto px-6 py-2.5 bg-navy-800 hover:bg-navy-900 text-white text-xs font-semibold uppercase tracking-wider rounded-gov shadow-sm transition-colors flex items-center justify-center gap-2"
              >
                {isProcessing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Running ML Models...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current" />
                    <span>Process Evidence Case</span>
                  </>
                )}
              </button>
            ) : (
              <button
                onClick={() => {
                  onClose();
                  onSelectCase(selectedPreset);
                }}
                className="w-full sm:w-auto px-6 py-2.5 bg-navy-800 hover:bg-navy-900 text-white text-xs font-semibold uppercase tracking-wider rounded-gov shadow-sm transition-colors flex items-center justify-center gap-2"
              >
                <span>Launch Grid Dashboard with Case</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
