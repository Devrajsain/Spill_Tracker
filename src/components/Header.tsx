import React from 'react';
import { Shield, MapPin, Database, FileText, ArrowRight, Activity, ExternalLink } from 'lucide-react';

interface HeaderProps {
  currentView: 'home' | 'dashboard' | 'workflow';
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const Header: React.FC<HeaderProps> = ({ currentView, onNavigate, onOpenUpload }) => {
  return (
    <header className="sticky top-0 z-50 bg-white border-b border-gov-border">
      {/* Official Government Top Bar */}
      <div className="bg-[#061629] text-white text-xs py-1 px-4 sm:px-8 flex justify-between items-center border-b border-navy-700">
        <div className="flex items-center space-x-3">
          <span className="font-semibold tracking-wider text-gray-200">GOVERNMENT OF INDIA</span>
          <span className="text-gray-500">|</span>
          <span className="text-gray-300">MINISTRY OF PORTS, SHIPPING AND WATERWAYS</span>
        </div>
        <div className="hidden md:flex items-center space-x-4 text-[11px] text-gray-300">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse"></span>
            NATIONAL MARITIME DEFENSE NETWORK ACTIVE
          </span>
          <span>|</span>
          <button onClick={() => onNavigate('dashboard')} className="hover:text-white transition-colors">
            SURVEILLANCE GRID v2.4
          </button>
        </div>
      </div>

      {/* Main Header Navigation */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-20">
          {/* Brand & Crest */}
          <div 
            className="flex items-center space-x-3 cursor-pointer group"
            onClick={() => onNavigate('home')}
          >
            {/* Emblem Placeholder */}
            <div className="w-12 h-12 rounded-full bg-navy-800 flex items-center justify-center border-2 border-navy-700 p-1 text-amber-400 shadow-sm">
              <svg viewBox="0 0 100 100" className="w-full h-full fill-current">
                {/* Simplified Ashoka Pillar Chakra Symbol */}
                <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="4"/>
                <circle cx="50" cy="50" r="12" fill="none" stroke="currentColor" strokeWidth="3"/>
                {Array.from({ length: 12 }).map((_, i) => (
                  <line 
                    key={i} 
                    x1="50" y1="50" 
                    x2={50 + 44 * Math.cos((i * Math.PI) / 6)} 
                    y2={50 + 44 * Math.sin((i * Math.PI) / 6)} 
                    stroke="currentColor" 
                    strokeWidth="2"
                  />
                ))}
              </svg>
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-2xl font-bold tracking-tight text-navy-800 font-sans">
                  SlickTrace
                </span>
                <span className="text-[10px] font-semibold uppercase tracking-wider bg-navy-800 text-white px-2 py-0.5 rounded-gov border border-navy-700">
                  GOV PORTAL
                </span>
              </div>
              <p className="text-xs text-gov-muted font-medium tracking-tight">
                Marine Oil Spill Detection &amp; Vessel Attribution System
              </p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="hidden lg:flex items-center space-x-8">
            <button
              onClick={() => onNavigate('home')}
              className={`text-sm font-semibold tracking-wide transition-colors py-2 border-b-2 ${
                currentView === 'home'
                  ? 'text-navy-800 border-navy-800'
                  : 'text-gov-text hover:text-navy-800 border-transparent hover:border-gov-border'
              }`}
            >
              Home
            </button>
            
            <a 
              href="#about" 
              onClick={(e) => {
                if (currentView !== 'home') onNavigate('home');
              }}
              className="text-sm font-medium text-gov-text hover:text-navy-800 py-2 border-b-2 border-transparent hover:border-gov-border transition-colors"
            >
              About
            </a>

            <button
              onClick={() => onNavigate('workflow')}
              className={`text-sm font-semibold tracking-wide transition-colors py-2 border-b-2 ${
                currentView === 'workflow'
                  ? 'text-navy-800 border-navy-800'
                  : 'text-gov-text hover:text-navy-800 border-transparent hover:border-gov-border'
              }`}
            >
              Forensic Workflow
            </button>

            <button
              onClick={() => onNavigate('dashboard')}
              className={`text-sm font-semibold tracking-wide transition-colors py-2 border-b-2 flex items-center gap-1.5 ${
                currentView === 'dashboard'
                  ? 'text-navy-800 border-navy-800'
                  : 'text-gov-text hover:text-navy-800 border-transparent hover:border-gov-border'
              }`}
            >
              <Activity className="w-4 h-4 text-gov-blue" />
              Surveillance Dashboard
            </button>

            <button
              onClick={onOpenUpload}
              className="text-sm font-medium text-gov-text hover:text-navy-800 py-2 border-b-2 border-transparent hover:border-gov-border transition-colors"
            >
              Upload Case
            </button>

            <a 
              href="#contact" 
              onClick={(e) => {
                if (currentView !== 'home') onNavigate('home');
              }}
              className="text-sm font-medium text-gov-text hover:text-navy-800 py-2 border-b-2 border-transparent hover:border-gov-border transition-colors"
            >
              Contact
            </a>
          </nav>

          {/* Action CTAs */}
          <div className="flex items-center space-x-3">
            <button
              onClick={onOpenUpload}
              className="hidden sm:inline-flex items-center justify-center px-3.5 py-2 text-xs font-semibold uppercase tracking-wider text-navy-800 bg-white border border-navy-800 rounded-gov hover:bg-gray-50 transition-all shadow-sm"
            >
              Upload New Case
            </button>
            <button
              onClick={() => onNavigate('dashboard')}
              className="inline-flex items-center justify-center px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white bg-navy-800 rounded-gov hover:bg-navy-900 transition-all shadow-sm gap-2"
            >
              <span>Launch Grid</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* 3px Indian Tricolor Accent Strip */}
      <div className="w-full flex h-[3px]">
        <div className="w-1/3 bg-[#FF9933]"></div>
        <div className="w-1/3 bg-white"></div>
        <div className="w-1/3 bg-[#138808]"></div>
      </div>
    </header>
  );
};
