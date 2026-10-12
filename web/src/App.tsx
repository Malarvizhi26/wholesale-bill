import React, { useState, useEffect, useCallback } from 'react';
import { Navbar } from './components/Navbar';
import { BillingPOS } from './components/BillingPOS';
import { InventoryManager } from './components/InventoryManager';
import { PartyLedger } from './components/PartyLedger';
import { Dashboard } from './components/Dashboard';
import { ReportsView } from './components/ReportsView';
import type { ReportsTab } from './components/ReportsView';
import { AIBusinessAssistant } from './components/AIBusinessAssistant';
import { OwnerPinDialog } from './components/OwnerPinDialog';
import type { Product, Party, Language, PartyCreateInput, PartyUpdateInput } from './types';
import { api } from './api/client';
import { getQueue, subscribeQueue, syncOfflineInvoices } from './api/offlineQueue';
import type { SyncOutcome } from './api/offlineQueue';

export type AppTab = 'pos' | 'dashboard' | 'inventory' | 'ledger' | 'reports' | 'assistant';

// Deep-link target inside a screen (from AI assistant action links / dashboard cards)
export interface NavTarget {
  subtab?: string;
  partyId?: string;
}

// AI assistant routes use lower-case aliases (/reports?tab=margin); map them to the screens' tab keys
const REPORT_TAB_ALIASES: Record<string, ReportsTab> = {
  daily: 'SALES', sales: 'SALES', margin: 'MARGIN', expenses: 'EXPENSES', credit: 'CREDIT',
  outstanding: 'CREDIT', valuation: 'STOCK', stock: 'STOCK', cash: 'CASH_RECON', review: 'REVIEW',
};

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<AppTab>('pos');
  const [navTarget, setNavTarget] = useState<NavTarget>({});
  const [language, setLanguage] = useState<Language>('en');
  const [products, setProducts] = useState<Product[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showPinSettings, setShowPinSettings] = useState(false);

  const [loadError, setLoadError] = useState<string | null>(null);

  // Offline invoice queue (bills saved while the server was unreachable)
  const [offlineQueue, setOfflineQueue] = useState(getQueue);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<SyncOutcome | null>(null);

  // Re-fetch catalogue (with stock) and parties (with balances) from the server.
  // Called after any posting so POS, Inventory and Ledger never show stale balances/stock.
  const refreshData = useCallback(async () => {
    try {
      const [prods, prts] = await Promise.all([api.getProducts(), api.getParties()]);
      setProducts(prods);
      setParties(prts);
      setLoadError(null);
    } catch (err: any) {
      setLoadError(err?.message || 'Failed to load data from server');
    }
  }, []);

  useEffect(() => subscribeQueue(setOfflineQueue), []);

  // Push queued offline bills; never drops a bill unless the server reports it SYNCED
  const runSync = useCallback(async (includeErrored = false) => {
    if (getQueue().length === 0) return;
    setSyncing(true);
    try {
      const outcome = await syncOfflineInvoices(includeErrored);
      if (outcome.synced.length > 0 || outcome.failed.length > 0) {
        setSyncNotice(outcome);
        if (outcome.synced.length > 0) refreshData();
      }
    } finally {
      setSyncing(false);
    }
  }, [refreshData]);

  // Load initial catalogue and parties
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      const isOnline = await api.checkHealth();
      setIsBackendConnected(isOnline);
      await refreshData();
      setLoading(false);
      if (isOnline) runSync();
    };

    loadData();

    // Poll backend health every 6 seconds; push pending offline bills as soon as it is reachable
    const interval = setInterval(async () => {
      const isOnline = await api.checkHealth();
      setIsBackendConnected(isOnline);
      if (isOnline && getQueue().some(q => q.status === 'PENDING')) runSync();
    }, 6000);

    const onOnline = () => {
      api.checkHealth().then(ok => {
        setIsBackendConnected(ok);
        if (ok) runSync();
      });
    };
    window.addEventListener('online', onOnline);

    return () => {
      clearInterval(interval);
      window.removeEventListener('online', onOnline);
    };
  }, [refreshData, runSync]);

  // Switching screens re-syncs balances & stock changed on another screen
  const handleTabChange = (tab: AppTab, target: NavTarget = {}) => {
    setActiveTab(tab);
    setNavTarget(target);
    if (tab !== activeTab) refreshData();
  };

  // F2 from any screen jumps to the POS counter (inside POS, F2 = New Bill)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'F2' && activeTab !== 'pos') {
        e.preventDefault();
        handleTabChange('pos');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const handleAddParty = async (data: PartyCreateInput): Promise<Party> => {
    const created = await api.createParty(data);
    setParties(prev => [...prev, created]);
    return created;
  };

  const handleUpdateParty = async (partyId: string, data: PartyUpdateInput): Promise<Party> => {
    const updated = await api.updateParty(partyId, data);
    setParties(prev => prev.map(p => (p.id === partyId ? { ...p, ...updated } : p)));
    return updated;
  };

  const reportsInitialTab = navTarget.subtab ? REPORT_TAB_ALIASES[navTarget.subtab.toLowerCase()] : undefined;
  const pendingCount = offlineQueue.length;
  const erroredCount = offlineQueue.filter(q => q.status === 'ERROR').length;

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      {/* Top Header Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={(tab) => handleTabChange(tab)}
        language={language}
        setLanguage={setLanguage}
        isBackendConnected={isBackendConnected}
        pendingSyncCount={pendingCount}
        syncErrorCount={erroredCount}
        isSyncing={syncing}
        onSyncNow={() => runSync(true)}
        onOpenPinSettings={() => setShowPinSettings(true)}
      />

      {/* Main Content Area */}
      <main className="flex-1 pb-8">
        {loadError && (
          <div className="max-w-7xl mx-auto px-4 pt-3">
            <div role="alert" className="bg-red-950/70 border border-red-800 text-red-300 text-xs rounded-lg px-3 py-2">
              Server error: {loadError}
            </div>
          </div>
        )}
        {syncNotice && (
          <div className="max-w-7xl mx-auto px-4 pt-3">
            <div role="status" className={`border text-xs rounded-lg px-3 py-2 flex items-start justify-between gap-3 ${
              syncNotice.failed.length > 0 ? 'bg-red-950/70 border-red-800 text-red-200' : 'bg-emerald-950/70 border-emerald-800 text-emerald-200'
            }`}>
              <div className="space-y-1">
                {syncNotice.synced.length > 0 && (
                  <div className="font-bold">
                    {syncNotice.synced.length} offline bill{syncNotice.synced.length > 1 ? 's' : ''} synced to the server.
                  </div>
                )}
                {syncNotice.synced.filter(s => s.review_flags.length > 0).map(s => (
                  <div key={s.invoice_number} className="text-amber-300">
                    {s.invoice_number}: flagged for owner review - {s.review_flags.join(', ')}
                  </div>
                ))}
                {syncNotice.failed.map(f => (
                  <div key={f.invoice_number}>
                    NOT synced {f.invoice_number}: {f.error} (kept in the queue - fix and press Sync)
                  </div>
                ))}
                {syncNotice.synced.some(s => s.review_flags.length > 0) && (
                  <button
                    onClick={() => handleTabChange('reports', { subtab: 'review' })}
                    className="underline font-semibold text-amber-200"
                  >
                    Open owner review flags
                  </button>
                )}
              </div>
              <button onClick={() => setSyncNotice(null)} className="font-bold opacity-80 hover:opacity-100" aria-label="Dismiss sync notice">x</button>
            </div>
          </div>
        )}
        {loading ? (
          <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-400 mr-3"></div>
            Loading Hardware OS...
          </div>
        ) : (
          <>
            {activeTab === 'pos' && (
              <BillingPOS
                products={products}
                parties={parties}
                language={language}
                onAddParty={handleAddParty}
                onUpdateParty={handleUpdateParty}
                onDocumentSaved={refreshData}
                pendingSyncCount={pendingCount}
              />
            )}
            {activeTab === 'dashboard' && (
              <Dashboard
                language={language}
                onOpenAssistant={() => handleTabChange('assistant')}
                onOpenReviewFlags={() => handleTabChange('reports', { subtab: 'review' })}
              />
            )}
            {activeTab === 'inventory' && (
              <InventoryManager
                products={products}
                parties={parties}
                language={language}
                initialTab={navTarget.subtab}
                onProductAdded={(newProd) => setProducts((prev) => [newProd, ...prev])}
                onStockChanged={refreshData}
              />
            )}
            {activeTab === 'ledger' && (
              <PartyLedger
                parties={parties}
                language={language}
                onAddParty={handleAddParty}
                onUpdateParty={handleUpdateParty}
                initialTab={navTarget.subtab}
                initialPartyId={navTarget.partyId}
              />
            )}
            {activeTab === 'reports' && <ReportsView language={language} initialTab={reportsInitialTab} />}
            {activeTab === 'assistant' && (
              <AIBusinessAssistant
                language={language}
                onNavigateTab={(tab, subtab) => handleTabChange(tab, { subtab })}
              />
            )}
          </>
        )}
      </main>

      {showPinSettings && <OwnerPinDialog language={language} onClose={() => setShowPinSettings(false)} />}
    </div>
  );
};

export default App;
