import React from 'react';
import { UploadCloud, Cpu, Compass, Ship, LayoutDashboard, ArrowRight, Play } from 'lucide-react';

interface OperationalWorkflowProps {
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const OperationalWorkflow: React.FC<OperationalWorkflowProps> = ({ onNavigate, onOpenUpload }) => {
  const steps = [
    {
      step: '01',
      title: 'Upload Evidence',
      icon: UploadCloud,
      subtitle: 'Imagery & AIS Dataset Ingestion',
      description: 'Upload high-resolution satellite imagery alongside AIS CSV data containing coordinates, timestamps, and vessel telemetry.'
    },
    {
      step: '02',
      title: 'Satellite Analysis',
      icon: Cpu,
      subtitle: 'AI Boundary Segmentation',
      description: 'Deep neural networks extract slick contours, calculate total surface area, and output detection confidence scores.'
    },
    {
      step: '03',
      title: 'Drift Reconstruction',
      icon: Compass,
      subtitle: 'Hydrodynamic Hindcasting',
      description: 'MetOcean wind and surface current models reverse-simulate transport physics to establish probable origin coordinates.'
    },
    {
      step: '04',
      title: 'AIS Correlation',
      icon: Ship,
      subtitle: 'Probabilistic Attribution',
      description: 'Vessel track histories are spatio-temporally matched against drift corridors to score candidate ships by likelihood.'
    },
    {
      step: '05',
      title: 'Investigation Report',
      icon: LayoutDashboard,
      subtitle: 'Operational Briefing',
      description: 'Interactive dashboard displays drift paths, suspect ranking, telemetry logs, and court-ready forensic reports.'
    }
  ];

  return (
    <section className="bg-gov-light py-16 border-b border-gov-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-12">
          <div className="space-y-2">
            <span className="text-xs font-bold uppercase tracking-wider text-gov-blue bg-white border border-gov-border px-3 py-1 rounded-gov">
              FORENSIC PIPELINE
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-navy-800 tracking-tight">
              Operational Evidence Workflow
            </h2>
            <p className="text-sm text-gov-muted max-w-2xl">
              A 5-stage automated evidence pipeline designed to process satellite captures, model hydrodynamic drift, and generate court-admissible vessel attribution evidence.
            </p>
          </div>

          <div className="mt-4 md:mt-0 flex items-center space-x-3">
            <button
              onClick={onOpenUpload}
              className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white bg-navy-800 hover:bg-navy-900 rounded-gov transition-colors flex items-center gap-2 shadow-sm"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Execute Workflow Demo</span>
            </button>
          </div>
        </div>

        {/* Process Diagram: Horizontal steps with thin connecting lines */}
        <div className="relative">
          {/* Thin connecting horizontal line behind cards (desktop) */}
          <div className="hidden lg:block absolute top-1/2 left-0 right-0 h-0.5 bg-gov-border -translate-y-6 z-0"></div>

          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6 relative z-10">
            {steps.map((item, index) => {
              const Icon = item.icon;
              return (
                <div 
                  key={item.step}
                  onClick={onOpenUpload}
                  className="bg-white border border-gov-border rounded-gov p-5 shadow-sm hover:border-navy-800 hover:shadow-md transition-all cursor-pointer group flex flex-col justify-between"
                >
                  <div>
                    {/* Header: Step Number & Icon */}
                    <div className="flex items-center justify-between mb-4">
                      <span className="text-xs font-mono font-bold text-gov-blue bg-gov-light px-2 py-0.5 rounded border border-gov-border">
                        STEP {item.step}
                      </span>
                      <div className="p-2 bg-gov-light text-navy-800 rounded-gov border border-gov-border group-hover:bg-navy-800 group-hover:text-white transition-colors">
                        <Icon className="w-5 h-5 stroke-[1.5]" />
                      </div>
                    </div>

                    <h3 className="text-base font-bold text-navy-800 mb-1 group-hover:text-gov-blue transition-colors">
                      {item.title}
                    </h3>

                    <p className="text-[11px] font-semibold text-gov-blue uppercase tracking-wider mb-3">
                      {item.subtitle}
                    </p>

                    <p className="text-xs text-gov-muted leading-relaxed">
                      {item.description}
                    </p>
                  </div>

                  <div className="pt-4 mt-4 border-t border-gov-border flex items-center justify-between text-[11px] text-gov-muted group-hover:text-navy-800">
                    <span className="font-mono">STAGE {index + 1}/5</span>
                    <ArrowRight className="w-3.5 h-3.5 transform group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Workflow Callout Box */}
        <div className="mt-8 bg-white border border-gov-border rounded-gov p-4 flex flex-col sm:flex-row items-center justify-between text-xs text-gov-muted gap-4">
          <div className="flex items-center space-x-3">
            <span className="w-3 h-3 rounded-full bg-emerald-500 flex-shrink-0 animate-ping"></span>
            <span>
              <strong className="text-navy-800">Interactive Pipeline Ready:</strong> You can upload test evidence images and CSV datasets directly into the workflow runner.
            </span>
          </div>
          <button
            onClick={onOpenUpload}
            className="text-navy-800 font-bold uppercase tracking-wider hover:underline flex items-center gap-1 whitespace-nowrap"
          >
            <span>Run Interactive Case Upload</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </section>
  );
};
