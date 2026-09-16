import React, { useState } from 'react';
import { ArrowRight, Moon, Menu, X } from 'lucide-react';

interface HeaderProps {
  currentView: 'home' | 'dashboard' | 'workflow';
  onNavigate: (view: 'home' | 'dashboard' | 'workflow') => void;
  onOpenUpload: () => void;
}

export const Header: React.FC<HeaderProps> = ({ currentView, onNavigate, onOpenUpload }) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { label: 'Home', action: () => onNavigate('home'), isActive: currentView === 'home' },
    { label: 'Forensic Workflow', action: () => onNavigate('workflow'), isActive: currentView === 'workflow' },
    { label: 'Surveillance Dashboard', action: () => onNavigate('dashboard'), isActive: currentView === 'dashboard' },
    { label: 'About', action: () => onNavigate('home'), isActive: false },
  ];

  return (
    <header className="fixed top-0 left-0 w-full z-50 bg-[rgba(6,18,35,0.55)] backdrop-blur-[20px] shadow-md border-b border-[rgba(255,255,255,0.08)] transition-all duration-300">
      <div className="w-full px-8 h-[80px]">
          <div className="relative flex justify-between items-center h-full">
            {/* Brand */}
            <div
              className="flex items-center space-x-3 cursor-pointer group flex-shrink-0"
              onClick={() => onNavigate('home')}
            >
              <img
                src="/neeraksh_logo.jpg"
                alt="NEERAKSH"
                className="w-10 h-10 rounded-full object-cover border border-cyan-400/30 shadow-sm group-hover:border-cyan-400/60 transition-all"
              />
              <div className="hidden sm:block">
                <span className="text-lg font-bold tracking-tight text-white">
                  NEERAKSH
                </span>
              </div>
            </div>

            {/* Desktop Navigation */}
            <nav className="hidden lg:flex items-center space-x-8 absolute left-1/2 -translate-x-1/2">
              {navLinks.map((link) => (
                <button
                  key={link.label}
                  onClick={link.action}
                  className={`relative px-1 py-1 text-[13px] font-bold tracking-wide transition-all duration-250 ${
                    link.isActive
                      ? 'text-white'
                      : 'text-white/70 hover:text-white'
                  }`}
                >
                  {link.label}
                  {link.isActive && (
                    <span className="absolute -bottom-1.5 left-0 w-full h-[2px] bg-[#00C8FF] shadow-[0_0_8px_#00C8FF]" />
                  )}
                </button>
              ))}
            </nav>

            {/* Right Actions */}
            <div className="flex items-center space-x-3">
              <button
                className="w-9 h-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/60 hover:text-white hover:bg-white/10 transition-all"
                aria-label="Toggle theme"
              >
                <Moon className="w-4 h-4" />
              </button>

              <button
                onClick={() => onNavigate('dashboard')}
                className="hidden sm:inline-flex items-center gap-2 px-5 py-2 text-xs font-bold uppercase tracking-wider text-white rounded-lg transition-all launch-grid-btn"
              >
                <span>Launch Grid</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>

              {/* Mobile Menu Toggle */}
              <button
                className="lg:hidden w-9 h-9 rounded-md bg-white/5 border border-white/10 flex items-center justify-center text-white"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="lg:hidden bg-[#061629]/95 backdrop-blur-xl border-t border-white/5">
          <div className="px-4 py-3 space-y-1">
            {navLinks.map((link) => (
              <button
                key={link.label}
                onClick={() => { link.action(); setMobileMenuOpen(false); }}
                className={`block w-full text-left px-4 py-2.5 text-sm rounded-md transition-all ${
                  link.isActive
                    ? 'text-cyan-400 bg-white/5'
                    : 'text-white/70 hover:text-white hover:bg-white/5'
                }`}
              >
                {link.label}
              </button>
            ))}
            <div className="pt-2 border-t border-white/10">
              <button
                onClick={() => { onNavigate('dashboard'); setMobileMenuOpen(false); }}
                className="w-full px-4 py-2.5 text-sm font-bold uppercase tracking-wider text-white rounded-md launch-grid-btn text-center"
              >
                Launch Grid →
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
