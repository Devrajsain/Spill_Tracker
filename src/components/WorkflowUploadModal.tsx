import React, { useState, useRef, useEffect } from 'react';
import { Upload, X, CheckCircle, AlertTriangle, FileText, Cpu, Compass, Ship, ArrowRight, Play, RefreshCw, Eye, Download } from 'lucide-react';
import { createCase, continueCaseFeature2, CaseResponse } from '../services/api';

interface WorkflowUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectCase: (caseId: string) => void;
}

const inferLocationName = (fileName: string): string => {
  const lower = fileName.toLowerCase();
  if (lower.includes('kutch') || lower.includes('slk-2291')) return 'Gulf of Kutch, Gujarat EEZ';
  if (lower.includes('mumbai') || lower.includes('bombay') || lower.includes('slk-2288')) return 'Mumbai High, Offshore Maharashtra';
  if (lower.includes('chennai') || lower.includes('ennore') || lower.includes('slk-2274')) return 'Chennai Coast, Bay of Bengal';
  if (lower.includes('cochin') || lower.includes('kochi')) return 'Cochin Coast, Arabian Sea';
  return 'Operational Maritime Area';
};

export const WorkflowUploadModal: React.FC<WorkflowUploadModalProps> = ({ isOpen, onClose, onSelectCase }) => {
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [uploadedImageFile, setUploadedImageFile] = useState<File | null>(null);
  const [uploadedCsvFile, setUploadedCsvFile] = useState<File | null>(null);
  const [uploadedImageName, setUploadedImageName] = useState<string>('');
  const [uploadedCsvName, setUploadedCsvName] = useState<string>('');
  const [processedCase, setProcessedCase] = useState<CaseResponse | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [processingStep, setProcessingStep] = useState<string>('');

  // Manual coordinate entry state for images without reliable geospatial metadata
  const [manualLatitude, setManualLatitude] = useState<string>('');
  const [manualLongitude, setManualLongitude] = useState<string>('');
  const [coordValidationError, setCoordValidationError] = useState<string | null>(null);

  const imageInputRef = useRef<HTMLInputElement>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setCurrentStep(1);
      setPipelineError(null);
      setIsProcessing(false);
      setProcessingStep('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedImageFile(file);
      setUploadedImageName(file.name);
      setProcessedCase(null);
      setManualLatitude('');
      setManualLongitude('');
      setCoordValidationError(null);
    }
  };

  const handleCsvUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedCsvFile(file);
      setUploadedCsvName(file.name);
    }
  };

  const handleRunPipeline = async () => {
    if (!uploadedImageFile) {
      setPipelineError('Please select a satellite SAR or optical image file to proceed.');
      return;
    }

    setIsProcessing(true);
    setPipelineError(null);
    setProcessedCase(null);
    setCoordValidationError(null);

    try {
      // Step 1 → 2: Uploading evidence & Feature 1 segmentation
      setProcessingStep('Uploading evidence & running AI segmentation...');
      setCurrentStep(2);

      const caseName = uploadedImageName.replace(/\.[^/.]+$/, '') + ' Case';
      const caseLocation = inferLocationName(uploadedImageName);
      const caseResponse = await createCase(
        caseName,
        caseLocation,
        null,
        null,
        uploadedImageFile,
        uploadedCsvFile,
      );

      setProcessedCase(caseResponse);
      onSelectCase(caseResponse.id);

      // Check if Feature 1 requires user to provide coordinates (JPG/PNG or non-georeferenced TIFF)
      const spill = caseResponse.summary_json?.spill;
      const requiresCoords = spill?.requires_coordinates || caseResponse.status === 'AWAITING_COORDINATES';

      if (requiresCoords) {
        // Stop at Step 2 and wait for user coordinates before calling Feature 2
        setIsProcessing(false);
        setProcessingStep('Awaiting geographic coordinates for Feature 2...');
        return;
      }

      // If GeoTIFF metadata was detected, show badge briefly before auto-advancing
      if (spill?.geospatial_metadata_detected) {
        setProcessingStep('GeoTIFF coordinates detected! Advancing to Feature 2 drift modeling...');
        await new Promise(resolve => setTimeout(resolve, 1000));
      } else {
        await new Promise(resolve => setTimeout(resolve, 500));
      }

      // Step 2 → 3: Drift modeling (Feature 2)
      setProcessingStep('Hydrodynamic drift backtracking...');
      setCurrentStep(3);
      await new Promise(resolve => setTimeout(resolve, 600));

      // Step 3 → 4: AIS vessel correlation
      setProcessingStep('AIS vessel correlation & attribution...');
      setCurrentStep(4);
      await new Promise(resolve => setTimeout(resolve, 400));

      setProcessingStep('Pipeline complete!');
      setIsProcessing(false);
    } catch (error: any) {
      setPipelineError(error.message || 'Pipeline execution failed');
      setIsProcessing(false);
      setProcessingStep('');
    }
  };

  const handleContinueToFeature2 = async () => {
    if (!processedCase) return;

    const lat = parseFloat(manualLatitude);
    const lon = parseFloat(manualLongitude);

    if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setCoordValidationError('Invalid latitude/longitude.\nPlease enter valid geographic coordinates.');
      return;
    }

    setCoordValidationError(null);
    setIsProcessing(true);

    try {
      setProcessingStep('Executing Feature 2 drift backtracking...');
      const updatedCase = await continueCaseFeature2(processedCase.id, lat, lon);
      setProcessedCase(updatedCase);
      onSelectCase(updatedCase.id);

      // Advance to Step 3 (Feature 2 drift modeling)
      setCurrentStep(3);
      await new Promise(resolve => setTimeout(resolve, 600));

      // Advance to Step 4 (Attribution)
      setProcessingStep('AIS vessel correlation & attribution...');
      setCurrentStep(4);
      await new Promise(resolve => setTimeout(resolve, 400));

      setProcessingStep('Pipeline complete!');
      setIsProcessing(false);
    } catch (err: any) {
      setPipelineError(err.message || 'Failed to execute Feature 2');
      setIsProcessing(false);
    }
  };

  // Extract results from processed case for display
  const spillResult = processedCase?.summary_json?.spill;
  const driftResult = processedCase?.summary_json?.drift;
  const vesselsResult = processedCase?.summary_json?.vessels;

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
            onClick={() => {
              if (processedCase?.id) {
                onSelectCase(processedCase.id);
              }
              onClose();
            }}
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
                onClick={() => {
                  if (processedCase || currentStep > s.num) {
                    setCurrentStep(s.num);
                  }
                }}
                className={`flex items-center space-x-2 py-1 px-3 rounded-gov border cursor-pointer transition-colors ${
                  currentStep === s.num
                    ? 'bg-navy-800 text-white border-navy-800 font-bold shadow-xs'
                    : currentStep > s.num
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-300 font-medium hover:bg-emerald-100'
                    : 'bg-white text-gov-muted border-gov-border hover:border-gray-400'
                }`}
              >
                <span className="w-5 h-5 rounded-full bg-current/20 flex items-center justify-center text-[10px] font-mono">
                  {currentStep > s.num ? '✓' : s.num}
                </span>
                <span className="hidden sm:inline">{s.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Processing Status Banner */}
        {isProcessing && (
          <div className="bg-navy-800 text-white px-6 py-2 flex items-center gap-3 text-xs">
            <RefreshCw className="w-4 h-4 animate-spin text-amber-400" />
            <span className="font-mono">{processingStep}</span>
          </div>
        )}

        {/* Error Banner */}
        {pipelineError && (
          <div className="bg-red-50 border-b border-red-200 px-6 py-3 flex items-center gap-3 text-xs text-red-800">
            <AlertTriangle className="w-4 h-4 text-red-600" />
            <span><strong>Pipeline Error:</strong> {pipelineError}</span>
            <button onClick={() => { setPipelineError(null); setCurrentStep(1); }} className="ml-auto underline">
              Retry
            </button>
          </div>
        )}

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
                <div 
                  onClick={() => imageInputRef.current?.click()}
                  className="border-2 border-dashed border-gov-border hover:border-navy-800 rounded-gov p-6 bg-gov-light text-center space-y-3 transition-colors cursor-pointer group"
                >
                  <input
                    ref={imageInputRef}
                    type="file"
                    accept=".tif,.tiff,.png,.jpg,.jpeg"
                    onChange={handleImageUpload}
                    className="hidden"
                  />
                  <div className="w-12 h-12 bg-white rounded-full mx-auto flex items-center justify-center border border-gov-border text-navy-800 group-hover:scale-105 transition-transform shadow-sm">
                    <Upload className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-navy-800">Satellite SAR / Optical Image</p>
                    <p className="text-[11px] text-gov-muted mt-0.5">GeoTIFF, PNG, JPEG up to 250MB</p>
                  </div>
                  {uploadedImageName && (
                    <div className="pt-2">
                      <span className="inline-block px-3 py-1 bg-white border border-emerald-300 rounded-gov text-[11px] font-mono text-emerald-800 font-semibold shadow-xs">
                        ✓ {uploadedImageName}
                      </span>
                    </div>
                  )}
                </div>

                {/* Zone 2: CSV Data */}
                <div 
                  onClick={() => csvInputRef.current?.click()}
                  className="border-2 border-dashed border-gov-border hover:border-navy-800 rounded-gov p-6 bg-gov-light text-center space-y-3 transition-colors cursor-pointer group"
                >
                  <input
                    ref={csvInputRef}
                    type="file"
                    accept=".csv"
                    onChange={handleCsvUpload}
                    className="hidden"
                  />
                  <div className="w-12 h-12 bg-white rounded-full mx-auto flex items-center justify-center border border-gov-border text-navy-800 group-hover:scale-105 transition-transform shadow-sm">
                    <FileText className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-navy-800">AIS Telemetry (.CSV)</p>
                    <p className="text-[11px] text-gov-muted mt-0.5">Vessel tracks with MMSI, Lat, Lon, SOG, COG</p>
                  </div>
                  {uploadedCsvName && (
                    <div className="pt-2">
                      <span className="inline-block px-3 py-1 bg-white border border-emerald-300 rounded-gov text-[11px] font-mono text-emerald-800 font-semibold shadow-xs">
                        ✓ {uploadedCsvName}
                      </span>
                    </div>
                  )}
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
                  {spillResult 
                    ? 'The SlickTrace segmentation model has processed the SAR imagery.'
                    : 'Processing SAR C-Band microwave backscatter gradients...'}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
                <div className="md:col-span-7 bg-navy-950 rounded-gov p-3 border border-navy-800 relative">
                  <div className="h-64 bg-slate-900 rounded relative overflow-hidden flex items-center justify-center border border-navy-700">
                    <div className="absolute inset-0 bg-gradient-to-tr from-slate-950 via-slate-900 to-slate-800 opacity-90"></div>
                    <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:20px_20px] opacity-40"></div>
                    
                    <div className="relative w-48 h-24 bg-red-600/30 border-2 border-red-500 rounded-full rotate-12 flex flex-col items-center justify-center p-2 shadow-[0_0_20px_rgba(239,68,68,0.4)]">
                      <span className="text-[10px] font-mono text-red-200 bg-red-950/90 px-1 border border-red-500 rounded font-bold">
                        SLICK CONTOUR IDENTIFIED
                      </span>
                      <span className="text-[9px] text-red-300 font-mono mt-1">
                        {spillResult ? `${spillResult.area_km2} km² area` : 'Analyzing...'}
                      </span>
                    </div>

                    <div className="absolute bottom-2 left-2 bg-navy-950/90 border border-navy-700 text-[10px] font-mono text-gray-300 p-1.5 rounded">
                      <div>Source: {spillResult?.satellite_source || 'Sentinel-1A (IW / VV)'}</div>
                      <div>Detected: {spillResult?.detection_timestamp || 'Processing...'}</div>
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
                        <span className="font-bold text-navy-800">{spillResult?.area_km2 || '—'} km²</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gov-border">
                        <span className="text-gov-muted">Detection Confidence:</span>
                        <span className="font-bold text-emerald-600">
                          {spillResult ? `${(spillResult.confidence_score * 100).toFixed(1)}% (${spillResult.confidence_label})` : '—'}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gov-border">
                        <span className="text-gov-muted">Est. Heavy Crude Volume:</span>
                        <span className="font-bold text-navy-800">
                          {spillResult ? `${spillResult.est_volume_bbl.toLocaleString()} barrels` : '—'}
                        </span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-gov-muted">Slick Dimensions:</span>
                        <span className="font-bold text-navy-800">
                          {spillResult ? `${spillResult.length_km} × ${spillResult.width_km} km` : '—'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Geospatial Metadata Detected Display */}
                  {spillResult?.geospatial_metadata_detected && (
                    <div className="p-4 bg-emerald-50 border border-emerald-300 rounded-gov text-xs text-emerald-950 space-y-2 shadow-xs">
                      <div className="flex items-center space-x-2 font-bold text-emerald-800 text-sm">
                        <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                        <span>✓ Geospatial metadata detected</span>
                      </div>
                      <div className="font-mono text-xs space-y-1 bg-white p-2.5 rounded border border-emerald-200">
                        <div><strong>Latitude:</strong>  {typeof spillResult.spill_latitude === 'number' ? spillResult.spill_latitude.toFixed(6) : spillResult.spill_latitude}</div>
                        <div><strong>Longitude:</strong> {typeof spillResult.spill_longitude === 'number' ? spillResult.spill_longitude.toFixed(6) : spillResult.spill_longitude}</div>
                      </div>
                      <p className="text-[11px] text-emerald-700 italic">
                        Coordinates automatically extracted from GeoTIFF.
                      </p>
                    </div>
                  )}

                  {/* Manual Coordinate Entry for JPG/PNG or unreferenced TIFF */}
                  {(spillResult?.requires_coordinates || processedCase?.status === 'AWAITING_COORDINATES') && (
                    <div className="p-4 bg-amber-50 border border-amber-300 rounded-gov text-xs text-navy-900 space-y-3 shadow-xs">
                      <div className="flex items-start space-x-2 text-amber-900 font-semibold">
                        <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                        <div className="text-xs space-y-1 leading-relaxed">
                          {uploadedImageName.toLowerCase().endsWith('.tif') || uploadedImageName.toLowerCase().endsWith('.tiff') ? (
                            <>
                              <p className="font-bold text-amber-900">⚠ This TIFF does not contain valid geospatial metadata.</p>
                              <p className="text-gray-700">Please enter the approximate oil-spill coordinates manually.</p>
                            </>
                          ) : (
                            <>
                              <p className="font-bold text-amber-900">This image does not contain reliable geospatial coordinates.</p>
                              <p className="text-gray-700">Please enter the approximate location of the oil spill to enable drift prediction.</p>
                            </>
                          )}
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-3 pt-1">
                        <div>
                          <label className="block text-[11px] font-bold text-navy-800 mb-1">Latitude</label>
                          <input
                            type="number"
                            step="any"
                            placeholder="-90 to 90"
                            value={manualLatitude}
                            onChange={(e) => {
                              setManualLatitude(e.target.value);
                              setCoordValidationError(null);
                            }}
                            className="w-full px-2.5 py-1.5 border border-gov-border rounded text-xs font-mono bg-white focus:outline-navy-800"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-bold text-navy-800 mb-1">Longitude</label>
                          <input
                            type="number"
                            step="any"
                            placeholder="-180 to 180"
                            value={manualLongitude}
                            onChange={(e) => {
                              setManualLongitude(e.target.value);
                              setCoordValidationError(null);
                            }}
                            className="w-full px-2.5 py-1.5 border border-gov-border rounded text-xs font-mono bg-white focus:outline-navy-800"
                          />
                        </div>
                      </div>

                      {coordValidationError && (
                        <div className="p-2 bg-red-100 border border-red-300 text-red-800 rounded text-[11px] whitespace-pre-line font-medium">
                          {coordValidationError}
                        </div>
                      )}

                      <button
                        type="button"
                        onClick={handleContinueToFeature2}
                        disabled={isProcessing}
                        className="w-full py-2 bg-navy-800 hover:bg-navy-900 text-white font-bold text-xs rounded transition-colors flex items-center justify-center space-x-2 disabled:opacity-50 cursor-pointer"
                      >
                        {isProcessing ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            <span>Computing Drift...</span>
                          </>
                        ) : (
                          <span>Continue to Feature 2</span>
                        )}
                      </button>
                    </div>
                  )}

                  {!spillResult?.requires_coordinates && processedCase?.status !== 'AWAITING_COORDINATES' && (
                    <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-gov text-xs text-emerald-900 flex items-start space-x-2">
                      <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                      <span>Boundary geometry formatted for hydrodynamic drift modeling.</span>
                    </div>
                  )}
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
                  Surface ocean currents and wind field vectors reverse-simulated to trace spill origin.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-gov-light border border-gov-border rounded-gov p-4 space-y-3">
                  <h5 className="text-xs font-bold text-navy-800 uppercase tracking-wider">
                    Hydrodynamic Parameters
                  </h5>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-gov-border">
                      <span className="text-gov-muted">Data Source:</span>
                      <span className="font-mono font-bold text-navy-800">
                        {processedCase?.summary_json?.feature2?.processing_mode === 'live' ? 'Feature 2 Lagrangian Engine' : 'MetOcean Hindcast Model'}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gov-border">
                      <span className="text-gov-muted">Calculated Origin:</span>
                      <span className="font-mono font-bold text-gov-blue">
                        {driftResult ? `${driftResult.origin_latitude.toFixed(4)}°N, ${driftResult.origin_longitude.toFixed(4)}°E` : '—'}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-gov-muted">Origin Timestamp:</span>
                      <span className="font-mono font-bold text-navy-800">
                        {driftResult?.origin_timestamp || '—'}
                      </span>
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
                      {driftResult 
                        ? `Origin traced to ${driftResult.origin_latitude.toFixed(4)}°N, ${driftResult.origin_longitude.toFixed(4)}°E. ${driftResult.drift_trajectory?.length || 0} trajectory points computed.`
                        : 'Computing backward trajectory...'}
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
                  {vesselsResult
                    ? `${vesselsResult.length} candidate vessels evaluated against origin coordinates, speed drop events, course deviations, and AIS silence gaps.`
                    : 'Evaluating candidate vessels...'}
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
                    {(vesselsResult || []).map((v: any, idx: number) => (
                      <tr key={v.mmsi} className={idx === 0 ? 'bg-red-50/50' : ''}>
                        <td className="py-3 px-3 font-bold text-navy-800 flex items-center space-x-2">
                          <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] text-white ${
                            idx === 0 ? 'bg-red-600' : idx === 1 ? 'bg-amber-500' : 'bg-slate-400'
                          }`}>{idx + 1}</span>
                          <span>{v.name}</span>
                        </td>
                        <td className="py-3 px-3 font-mono text-gov-muted">{v.mmsi} ({v.type})</td>
                        <td className="py-3 px-3 font-mono text-navy-800">{v.proximity_score}%</td>
                        <td className="py-3 px-3 font-mono text-navy-800">{v.trajectory_score}%</td>
                        <td className="py-3 px-3">
                          <div className="flex flex-wrap gap-1">
                            {(v.warning_flags || []).map((f: string, fIdx: number) => (
                              <span 
                                key={fIdx}
                                className={`inline-block text-[9px] font-semibold px-1.5 py-0.5 rounded border ${
                                  f.includes('GAP') || f.includes('DEVIATION')
                                    ? 'bg-red-100 text-red-800 border-red-200'
                                    : 'bg-gov-light text-navy-800 border-gov-border'
                                }`}
                              >
                                {f}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className={`py-3 px-3 text-right font-extrabold ${
                          idx === 0 ? 'text-red-600 text-sm' : idx === 1 ? 'text-amber-600' : 'text-gov-muted'
                        }`}>
                          {v.overall_score} / 100
                        </td>
                      </tr>
                    ))}
                    {!vesselsResult && (
                      <tr>
                        <td colSpan={6} className="py-6 px-3 text-center text-gov-muted">
                          <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-navy-800" />
                          Loading vessel attribution results...
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Modal Bottom Footer Actions */}
        <div className="bg-gov-light px-6 py-4 border-t border-gov-border flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-xs text-gov-muted flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${processedCase ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
            <span>
              Case ID: <strong>{processedCase?.id || '—'}</strong>
              {processedCase && ' | Analysis Complete'}
            </span>
          </div>

          <div className="flex items-center space-x-3 w-full sm:w-auto">
            {currentStep === 1 ? (
              <button
                onClick={handleRunPipeline}
                disabled={isProcessing || !uploadedImageFile}
                className="w-full sm:w-auto px-6 py-2.5 bg-navy-800 hover:bg-navy-900 text-white text-xs font-semibold uppercase tracking-wider rounded-gov shadow-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isProcessing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Running Pipeline...</span>
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
                  if (processedCase?.id) {
                    onSelectCase(processedCase.id);
                  }
                  onClose();
                }}
                disabled={isProcessing || !processedCase?.id}
                className="w-full sm:w-auto px-6 py-2.5 bg-navy-800 hover:bg-navy-900 text-white text-xs font-semibold uppercase tracking-wider rounded-gov shadow-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
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
