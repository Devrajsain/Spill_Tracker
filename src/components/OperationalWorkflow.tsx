import React, { useState } from 'react';
import { Upload, Satellite, Compass, Target, FileText, ChevronRight, Play } from 'lucide-react';

interface OperationalWorkflowProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const OperationalWorkflow: React.FC<OperationalWorkflowProps> = ({ onNavigate, onOpenUpload }) => {
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    {
      id: 1,
      title: 'Upload SAR + AIS',
      icon: Upload,
      description: 'Ingestion of Sentinel-1 C-Band SAR GeoTIFF imagery paired with MarineCadastre / territorial AIS CSV telemetry stream.',
      points: ['Sentinel-1 SAR IW Dual-Pol', '10m Resolution Grid', 'AIS Class-A Telemetry Log']
    },
    {
      id: 2,
      title: 'Detect U-Net',
      icon: Satellite,
      description: 'Deep convolutional U-Net AI model segments dark radar backscatter patches, distinguishing oil slicks from biogenic lookalikes.',
      points: ['Dual-Polarization (VV+VH)', 'Boundary Polygon Vectorization', 'Area & Perimeter Computation']
    },
    {
      id: 3,
      title: 'Backtrack Lagrangian',
      icon: Compass,
      description: 'Runge-Kutta 4th Order backward particle simulation driven by INCOIS surface currents and ERA5 marine winds up to -48 hours.',
      points: ['INCOIS 1/12° Current Vectors', 'ERA5 10m Atmospheric Winds', 'Origin Locus & Uncertainty Ellipse']
    },
    {
      id: 4,
      title: 'Correlate AIS',
      icon: Target,
      description: 'Spatio-temporal intersection of historical vessel positions with the backtrack corridor, flagging speed drops and loitering.',
      points: ['Closest Point of Approach (CPA)', 'Speed & Course Deviation Filter', 'Multi-Factor Probability Ranking']
    },
    {
      id: 5,
      title: 'Report Forensic PDF',
      icon: FileText,
      description: 'Automated synthesis into tamper-evident forensic intelligence dossier compliant with MARPOL 73/78 for statutory Coast Guard prosecution.',
      points: ['SHA-256 Chain-of-Custody', 'Coordinate & Timestamp Logs', 'Court-Admissible Evidence Export']
    }
  ];

  return (
    <section className="bg-gov-light py-16 border-b border-gov-border" id="workflow">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-12 space-y-3">
          <span className="text-xs font-bold uppercase tracking-wider text-gov-blue bg-gov-blue/10 border border-gov-blue/20 px-3 py-1 rounded-gov inline-block">
            OPERATIONAL PIPELINE (NTRO SIH26143)
          </span>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-navy-800 tracking-tight">
            5-STAGE EVIDENCE PIPELINE
          </h2>
          <p className="text-sm text-gov-muted leading-relaxed">
            End-to-End Forensic Investigation Workflow<br/>
            Standard operating procedure from raw Earth-observation ingestion to statutory tribunal-ready vessel attribution.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-8 items-start">
          {/* Navigation Sidebar */}
          <div className="w-full lg:w-1/3 space-y-2">
            <button
              onClick={() => onNavigate('workflow')}
              className="w-full mb-4 px-4 py-3 bg-navy-800 text-white rounded-gov font-bold text-xs uppercase tracking-wider flex items-center justify-between hover:bg-navy-900 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Play className="w-4 h-4" />
                <span>Execute Workflow Runner</span>
              </div>
            </button>
            {steps.map((step, idx) => (
              <button
                key={step.id}
                onClick={() => setActiveStep(idx)}
                className={`w-full text-left px-4 py-3 rounded-gov border transition-all duration-200 flex items-center justify-between ${
                  activeStep === idx 
                    ? 'bg-white border-gov-blue shadow-sm text-navy-800' 
                    : 'bg-transparent border-transparent text-gov-muted hover:bg-white/50 hover:border-gov-border'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-mono font-bold ${activeStep === idx ? 'text-gov-blue' : 'text-gov-muted'}`}>
                    {step.id}
                  </span>
                  <span className="text-sm font-bold uppercase tracking-wide">
                    {step.title}
                  </span>
                </div>
                {activeStep === idx && <ChevronRight className="w-4 h-4 text-gov-blue" />}
              </button>
            ))}
          </div>

          {/* Active Step Content */}
          <div className="w-full lg:w-2/3 bg-white border border-gov-border rounded-gov p-8 shadow-sm">
            <div className="flex items-center gap-4 mb-6 pb-6 border-b border-gov-border">
              <div className="p-4 bg-gov-light rounded-full text-navy-800 border border-gov-border">
                {React.createElement(steps[activeStep].icon, { className: "w-8 h-8" })}
              </div>
              <div>
                <span className="text-xs font-bold text-gov-blue uppercase tracking-wider mb-1 block">
                  STAGE {steps[activeStep].id}
                </span>
                <h3 className="text-2xl font-bold text-navy-800">
                  {steps[activeStep].title}
                </h3>
              </div>
            </div>

            <p className="text-sm text-gov-text leading-relaxed mb-8">
              {steps[activeStep].description}
            </p>

            <div className="space-y-3">
              {steps[activeStep].points.map((point, i) => (
                <div key={i} className="flex items-center gap-3 bg-gov-light border border-gov-border px-4 py-3 rounded-gov">
                  <div className="w-1.5 h-1.5 rounded-full bg-gov-blue shrink-0" />
                  <span className="text-sm font-semibold text-navy-800">{point}</span>
                </div>
              ))}
            </div>
          </div>
        </div>


      </div>
    </section>
  );
};
