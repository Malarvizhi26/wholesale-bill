import React from 'react';
import { ShoppingCart, LayoutDashboard, Package, Users, FileText, Wifi, WifiOff, Globe, Sparkles } from 'lucide-react';
import type { Language } from '../types';

interface NavbarProps {
  activeTab: 'pos' | 'dashboard' | 'inventory' | 'ledger' | 'reports' | 'assistant';
  setActiveTab: (tab: 'pos' | 'dashboard' | 'inventory' | 'ledger' | 'reports' | 'assistant') => void;
  language: Language;
  setLanguage: (lang: Language) => void;
  isBackendConnected: boolean;
  pendingSyncCount?: number;
  syncErrorCount?: number;
  isSyncing?: boolean;
  onSyncNow?: () => void;
  onOpenPinSettings?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  language,
  setLanguage,
  isBackendConnected,
  pendingSyncCount: _pendingSyncCount,
  syncErrorCount: _syncErrorCount,
  isSyncing: _isSyncing,
  onSyncNow: _onSyncNow,
  onOpenPinSettings: _onOpenPinSettings,
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand & Counter */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-600 flex items-center justify-center font-black text-xl text-white shadow-lg shadow-emerald-900/50">
              SM
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-100 text-base tracking-tight">
                  Salem Sri Murugan Hardware
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                  {language === 'ta' ? 'சேலம் ஸ்ரீ முருகன்' : 'Salem Junction'}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span className="font-mono text-slate-300">COUNTER-1</span>
                <span>•</span>
                <span>GST: 33AABCS1234F1Z5</span>
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-slate-800/80 p-1 rounded-xl border border-slate-700/60">
            <button
              onClick={() => setActiveTab('pos')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'pos'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <ShoppingCart className="w-4 h-4" />
              <span>{language === 'ta' ? 'பில்லிங் (F2)' : 'POS Billing (F2)'}</span>
            </button>

            <button
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'dashboard'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <LayoutDashboard className="w-4 h-4" />
              <span>{language === 'ta' ? 'டாஷ்போர்டு' : 'Dashboard'}</span>
            </button>

            <button
              onClick={() => setActiveTab('inventory')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'inventory'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Package className="w-4 h-4" />
              <span>{language === 'ta' ? 'சரக்கு இருப்பு' : 'Inventory'}</span>
            </button>

            <button
              onClick={() => setActiveTab('ledger')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'ledger'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Users className="w-4 h-4" />
              <span>{language === 'ta' ? 'கடன் கணக்கு' : 'Party Ledger'}</span>
            </button>

            <button
              onClick={() => setActiveTab('reports')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'reports'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>{language === 'ta' ? 'அறிக்கைகள்' : 'Reports'}</span>
            </button>

            <button
              onClick={() => setActiveTab('assistant')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'assistant'
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-500 text-white shadow-md ring-1 ring-emerald-400'
                  : 'text-emerald-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <span>{language === 'ta' ? 'AI உதவியாளர்' : 'AI Assistant'}</span>
            </button>
          </nav>

          {/* Status & Language Toggle */}
          <div className="flex items-center gap-3">
            {/* Backend Connectivity Badge */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                isBackendConnected
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
              }`}
              title={isBackendConnected ? 'Connected to FastAPI Monolith' : 'Offline Mode (Local Counter Queue)'}
            >
              {isBackendConnected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              <span>{isBackendConnected ? 'Online API' : 'Local SQLite'}</span>
            </div>

            {/* Language Toggle */}
            <button
              onClick={() => setLanguage(language === 'en' ? 'ta' : 'en')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs font-medium border border-slate-700 transition"
              title="Toggle Tamil / English"
            >
              <Globe className="w-3.5 h-3.5 text-emerald-400" />
              <span>{language === 'en' ? 'தமிழ்' : 'English'}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
