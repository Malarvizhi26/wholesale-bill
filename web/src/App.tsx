import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { BillingPOS } from './components/BillingPOS';
import { InventoryManager } from './components/InventoryManager';
import { PartyLedger } from './components/PartyLedger';
import { Dashboard } from './components/Dashboard';
import { ReportsView } from './components/ReportsView';
import type { Product, Party, Language } from './types';
import { api } from './api/client';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'pos' | 'dashboard' | 'inventory' | 'ledger' | 'reports'>('pos');
  const [language, setLanguage] = useState<Language>('en');
  const [products, setProducts] = useState<Product[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  // Load initial catalogue and parties
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      const isOnline = await api.checkHealth();
      setIsBackendConnected(isOnline);

      const prods = await api.getProducts();
      const prts = await api.getParties();
      setProducts(prods);
      setParties(prts);
      setLoading(false);
    };

    loadData();

    // Poll backend health every 6 seconds
    const interval = setInterval(async () => {
      const isOnline = await api.checkHealth();
      setIsBackendConnected(isOnline);
    }, 6000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      {/* Top Header Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        language={language}
        setLanguage={setLanguage}
        isBackendConnected={isBackendConnected}
      />

      {/* Main Content Area */}
      <main className="flex-1 pb-8">
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
              />
            )}
            {activeTab === 'dashboard' && <Dashboard language={language} />}
            {activeTab === 'inventory' && <InventoryManager products={products} language={language} />}
            {activeTab === 'ledger' && <PartyLedger parties={parties} language={language} />}
            {activeTab === 'reports' && <ReportsView language={language} />}
          </>
        )}
      </main>
    </div>
  );
};

export default App;
