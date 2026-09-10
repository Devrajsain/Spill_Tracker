import React, { useState } from 'react';
import { Header } from './components/Header';
import { HeroSection } from './components/HeroSection';
import { MissionBanner } from './components/MissionBanner';
import { CoreCapabilities } from './components/CoreCapabilities';
import { OperationalWorkflow } from './components/OperationalWorkflow';
import { OperationalStatistics } from './components/OperationalStatistics';
import { WhySlickTrace } from './components/WhySlickTrace';
import { Footer } from './components/Footer';
import { WorkflowUploadModal } from './components/WorkflowUploadModal';
import { Dashboard } from './components/Dashboard';

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<'home' | 'dashboard' | 'workflow'>('home');
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const [activeCaseId, setActiveCaseId] = useState<string>('');

  const handleNavigate = (view: 'home' | 'dashboard' | 'workflow') => {
    setCurrentView(view);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSelectCaseAndLaunch = (caseId: string) => {
    setActiveCaseId(caseId);
    setCurrentView('dashboard');
  };

  if (currentView === 'dashboard') {
    return (
      <>
        <Dashboard
          onNavigate={handleNavigate}
          onOpenUpload={() => setIsUploadModalOpen(true)}
          selectedCaseId={activeCaseId}
        />
        <WorkflowUploadModal
          isOpen={isUploadModalOpen}
          onClose={() => setIsUploadModalOpen(false)}
          onSelectCase={handleSelectCaseAndLaunch}
        />
      </>
    );
  }

  return (
    <div className="min-h-screen bg-white text-gov-text font-sans flex flex-col selection:bg-navy-800 selection:text-white">
      {/* Header Navigation */}
      <Header
        currentView={currentView}
        onNavigate={handleNavigate}
        onOpenUpload={() => setIsUploadModalOpen(true)}
      />

      {/* View Content */}
      <main className="flex-1">
        {currentView === 'home' && (
          <>
            <HeroSection
              onNavigate={handleNavigate}
              onOpenUpload={() => setIsUploadModalOpen(true)}
            />
            <MissionBanner />
            <CoreCapabilities onNavigate={handleNavigate} />
            <OperationalWorkflow
              onNavigate={handleNavigate}
              onOpenUpload={() => setIsUploadModalOpen(true)}
            />
            <OperationalStatistics />
            <WhySlickTrace />
          </>
        )}

        {currentView === 'workflow' && (
          <div className="py-8">
            <OperationalWorkflow
              onNavigate={handleNavigate}
              onOpenUpload={() => setIsUploadModalOpen(true)}
            />
            <div className="max-w-7xl mx-auto px-4 py-8">
              <div className="bg-gov-light border border-gov-border rounded-gov p-8 text-center space-y-4">
                <h2 className="text-xl font-bold text-navy-800">Ready to Process Evidence?</h2>
                <p className="text-xs text-gov-muted max-w-xl mx-auto">
                  Upload synthetic aperture radar (SAR) images and AIS telemetry files to run the full forensic analysis pipeline.
                </p>
                <button
                  onClick={() => setIsUploadModalOpen(true)}
                  className="px-6 py-3 bg-navy-800 hover:bg-navy-900 text-white text-xs font-semibold uppercase tracking-wider rounded-gov shadow-sm"
                >
                  Open Interactive Evidence Upload
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <Footer
        onNavigate={handleNavigate}
        onOpenUpload={() => setIsUploadModalOpen(true)}
      />

      {/* Interactive Workflow Modal */}
      <WorkflowUploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onSelectCase={handleSelectCaseAndLaunch}
      />
    </div>
  );
};

export default App;
