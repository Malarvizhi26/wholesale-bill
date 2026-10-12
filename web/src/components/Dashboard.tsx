import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  AlertTriangle,
  Wallet,
  Users,
  ArrowUpRight,
  Clock,
  ShieldAlert,
  RefreshCw,
  PackageCheck,
  Building2,
} from 'lucide-react';
import type { Language, OwnerMorningSnapshot, CollectionReminderItem, LowStockAlert } from '../types';
import { CurrencyCell } from './ui/CurrencyCell';
import { api } from '../api/client';
import { Sparkles } from 'lucide-react';

interface DashboardProps {
  language: Language;
  onOpenAssistant?: () => void;
  onOpenReviewFlags?: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ language, onOpenAssistant, onOpenReviewFlags: _onOpenReviewFlags }) => {
  const [snapshot, setSnapshot] = useState<OwnerMorningSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topDebtors, setTopDebtors] = useState<CollectionReminderItem[]>([]);
  const [lowStockItems, setLowStockItems] = useState<LowStockAlert[]>([]);

  const fetchSnapshot = async () => {
    setLoading(true);
    try {
      const [data, debtors, alerts] = await Promise.all([
        api.getOwnerMorningSnapshot(),
        api.getCollectionCallList(0, 0),
        api.getLowStockAlerts(),
      ]);
      setSnapshot(data);
      setTopDebtors(debtors.slice(0, 5));
      setLowStockItems(alerts.slice(0, 5));
      setError(null);
    } catch (err: any) {
      // Never show invented figures: report the failure and show zeros
      setError(err?.message || 'Failed to load owner snapshot');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSnapshot();
  }, []);

  // Real figures only (zeros until loaded / when the server is unreachable)
  const sales = snapshot?.today_sales ?? 0;
  const marginEst = snapshot?.gross_margin_estimate ?? 0;
  const marginPct = snapshot?.gross_margin_percent ?? 0;
  const receivables = snapshot?.outstanding_receivables ?? 0;
  const cashDrawer = snapshot?.cash_in_drawer ?? 0;
  const expensesToday = snapshot?.operating_expenses_today ?? 0;
  const netProfit = snapshot?.net_operating_profit_today ?? 0;
  const stockValuation = snapshot?.stock_total_valuation ?? 0;
  const payables = snapshot?.payables_due_suppliers ?? 0;
  const lowStockCount = snapshot?.low_stock_alerts_count ?? 0;

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-5">
      {error && (
        <div className="bg-red-950/70 border border-red-800 text-red-300 text-xs rounded-lg px-3 py-2">
          Dashboard not loaded: {error}
        </div>
      )}
      {/* Morning Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-gradient-to-r from-slate-800 to-slate-800/95 p-5 rounded-2xl border border-slate-700 shadow-xl">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-black text-white">
              {language === 'ta' ? 'வணக்கம், உரிமையாளர் காலை அறிக்கை' : 'Good Morning, Owner Snapshot'}
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-mono font-bold border border-emerald-500/30">
              Live &lt; 1s ⚡
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Salem Sri Murugan Hardware & Steels • Counter 1 Online • {new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {onOpenAssistant && (
            <button
              onClick={onOpenAssistant}
              className="text-xs font-semibold text-white bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 px-3.5 py-1.5 rounded-xl border border-emerald-400/40 flex items-center gap-1.5 shadow-md shadow-emerald-950/40 transition active:scale-95"
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-200" />
              <span>{language === 'ta' ? 'AI உதவியாளர்' : 'Ask AI Assistant'}</span>
            </button>
          )}

          <button
            onClick={fetchSnapshot}
            disabled={loading}
            className="text-xs font-mono text-emerald-400 bg-slate-900/90 hover:bg-slate-900 px-3 py-1.5 rounded-xl border border-slate-700/80 flex items-center gap-1.5 shadow-inner transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Refreshing...' : 'Pre-calculated Snapshots'}</span>
          </button>
        </div>
      </div>

      {/* KPI Cards Bento Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Today's Sales */}
        <div className="hardware-card p-4 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>{language === 'ta' ? 'இன்றைய விற்பனை' : "Today's Sales"}</span>
            <span className="p-1.5 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-800/50">
              <TrendingUp className="w-4 h-4" />
            </span>
          </div>
          <div className="pt-1">
            <CurrencyCell amount={sales} size="3xl" highlight="default" />
          </div>
          <div className="text-[11px] text-emerald-400 flex items-center gap-1 font-bold">
            <span>{snapshot?.invoices_count_today ?? 0} Invoices Billed</span>
            <span className="text-slate-400 font-normal">today</span>
          </div>
        </div>

        {/* Card 2: Gross Margin Estimate */}
        <div className="hardware-card p-4 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>{language === 'ta' ? 'மொத்த லாபம் (WAC)' : 'Gross Margin Estimate'}</span>
            <span className="p-1.5 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-800/50">
              <span className="font-mono font-bold text-xs">%</span>
            </span>
          </div>
          <div className="pt-1">
            <CurrencyCell amount={marginEst} size="3xl" highlight="emerald" />
          </div>
          <div className="text-[11px] text-slate-300 font-mono">
            Weighted Average Margin: <span className="text-emerald-400 font-black">{marginPct}%</span>
          </div>
        </div>

        {/* Card 3: Receivables & Overdue */}
        <div className="hardware-card p-4 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>{language === 'ta' ? 'வர வேண்டிய கடன்' : 'Outstanding Credit'}</span>
            <span className="p-1.5 rounded-lg bg-amber-950 text-amber-400 border border-amber-800/50">
              <Clock className="w-4 h-4" />
            </span>
          </div>
          <div className="pt-1">
            <CurrencyCell amount={receivables} size="3xl" highlight="amber" />
          </div>
          <div className="text-[11px] text-red-400 flex items-center gap-1 font-bold">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>{snapshot?.overdue_debtors_count ?? 0} parties overdue (&gt; 30 days)</span>
          </div>
        </div>

        {/* Card 4: Cash in Hand */}
        <div className="hardware-card p-4 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
            <span>{language === 'ta' ? 'கையிருப்பு ரொக்கம்' : 'Cash in Drawer'}</span>
            <span className="p-1.5 rounded-lg bg-blue-950 text-blue-400 border border-blue-800/50">
              <Wallet className="w-4 h-4" />
            </span>
          </div>
          <div className="pt-1">
            <CurrencyCell amount={cashDrawer} size="3xl" highlight="default" />
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Physical drawer cash counted live
          </div>
        </div>
      </div>

      {/* Secondary KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Operating Expenses & Net Profit */}
        <div className="hardware-card p-3.5 flex items-center justify-between border-l-4 border-l-purple-500">
          <div>
            <div className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">
              {language === 'ta' ? 'இன்றைய செலவு & நிகர லாபம்' : 'Expenses & Net Profit'}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-sm font-bold font-mono text-purple-300">Exp: ₹{expensesToday.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              <span>•</span>
              <span className="text-sm font-bold font-mono text-emerald-400">Net: ₹{netProfit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
          </div>
          <Wallet className="w-6 h-6 text-purple-400/50" />
        </div>

        {/* Stock Valuation */}
        <div className="hardware-card p-3.5 flex items-center justify-between border-l-4 border-l-emerald-500">
          <div>
            <div className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">
              {language === 'ta' ? 'சரக்கு மதிப்பு (WAC)' : 'Stock Valuation (WAC)'}
            </div>
            <div className="text-base font-bold font-mono text-emerald-300 mt-0.5">
              ₹{stockValuation.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>
          <PackageCheck className="w-6 h-6 text-emerald-400/50" />
        </div>

        {/* Payables Due */}
        <div className="hardware-card p-3.5 flex items-center justify-between border-l-4 border-l-red-500">
          <div>
            <div className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">
              {language === 'ta' ? 'சப்ளையர் பாக்கி' : 'Payables Due (Suppliers)'}
            </div>
            <div className="text-base font-bold font-mono text-red-300 mt-0.5">
              ₹{payables.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>
          <Building2 className="w-6 h-6 text-red-400/50" />
        </div>
      </div>

      {/* Middle Section: Top Debtors Call List & Low Stock Warnings */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Top Debtors Call List */}
        <div className="lg:col-span-7 hardware-card p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-700 pb-2.5">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-emerald-400" />
              <h3 className="font-bold text-white text-sm">
                {language === 'ta' ? 'இன்று வசூலிக்க வேண்டியவர்கள்' : "Top Debtors to Call Today (WhatsApp)"}
              </h3>
            </div>
            <span className="text-[11px] font-mono text-slate-400">Ranked by oldest unpaid bill</span>
          </div>

          <div className="space-y-2.5">
            {topDebtors.length === 0 && (
              <div className="text-center p-6 text-slate-500 text-xs">No outstanding customer dues.</div>
            )}
            {topDebtors.map((d) => (
              <div key={d.party_id} className="flex items-center justify-between p-3 rounded-xl bg-slate-900 border border-slate-700/70 text-xs hover:border-slate-500 transition">
                <div>
                  <div className="font-bold text-white text-sm">{d.customer_name}</div>
                  <div className="text-slate-400 text-[11px] font-mono mt-0.5">
                    Ph: {d.phone || '-'} • Inv: {d.oldest_bill_number || '-'} • <span className="text-red-400 font-bold">{d.days_overdue} days overdue</span>
                  </div>
                </div>
                <div className="text-right flex flex-col items-end">
                  <CurrencyCell amount={d.current_balance} highlight="amber" size="lg" />
                  {d.phone && (
                    <a
                      href={`https://wa.me/91${d.phone.replace(/\D/g, '')}?text=${encodeURIComponent(d.whatsapp_message)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-emerald-400 hover:text-emerald-300 font-semibold inline-flex items-center gap-1 mt-1 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800"
                    >
                      <span>Send Reminder</span>
                      <ArrowUpRight className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Low Stock Reorder Alerts */}
        <div className="lg:col-span-5 hardware-card p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-700 pb-2.5">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400" />
              <h3 className="font-bold text-white text-sm">
                {language === 'ta' ? 'குறைந்த சரக்கு எச்சரிக்கை' : 'Low-Stock Reorder Triggers'}
              </h3>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-red-950 text-red-300 font-bold border border-red-800">
              {lowStockCount} Items
            </span>
          </div>

          <div className="space-y-2.5">
            {lowStockItems.length === 0 && (
              <div className="text-center p-6 text-slate-500 text-xs">No items below minimum stock.</div>
            )}
            {lowStockItems.map((item) => (
              <div key={item.product_id} className="p-3 rounded-xl bg-slate-900 border border-slate-700/70 text-xs space-y-1.5">
                <div className="flex justify-between font-bold text-white">
                  <span>{item.product_name}</span>
                  <span className="text-red-400 font-mono font-black">{item.display_stock}</span>
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Threshold: <strong className="text-slate-200">{item.min_stock_base} {item.base_unit}</strong></span>
                  <span className="text-slate-300 truncate max-w-[180px]">Reorder: {item.display_suggested_reorder}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
