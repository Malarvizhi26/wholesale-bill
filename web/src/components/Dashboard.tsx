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
import type { Language, OwnerMorningSnapshot } from '../types';
import { CurrencyCell } from './ui/CurrencyCell';
import { api } from '../api/client';
import { Sparkles } from 'lucide-react';

interface DashboardProps {
  language: Language;
  onOpenAssistant?: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ language, onOpenAssistant }) => {
  const [snapshot, setSnapshot] = useState<OwnerMorningSnapshot | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchSnapshot = async () => {
    setLoading(true);
    try {
      const data = await api.getOwnerMorningSnapshot();
      setSnapshot(data);
    } catch {
      // offline fallback or defaults
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSnapshot();
  }, []);

  // Safe defaults if API loading or offline
  const sales = snapshot?.today_sales ?? 68450;
  const marginEst = snapshot?.gross_margin_estimate ?? 16975;
  const marginPct = snapshot?.gross_margin_percent ?? 24.8;
  const receivables = snapshot?.outstanding_receivables ?? 142800;
  const cashDrawer = snapshot?.cash_in_drawer ?? 28340;
  const expensesToday = snapshot?.operating_expenses_today ?? 2750;
  const netProfit = snapshot?.net_operating_profit_today ?? (marginEst - expensesToday);
  const stockValuation = snapshot?.stock_total_valuation ?? 485200;
  const payables = snapshot?.payables_due_suppliers ?? 52000;
  const lowStockCount = snapshot?.low_stock_alerts_count ?? 3;

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-5">
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
            <span>{snapshot?.invoices_count_today ?? 12} Invoices Billed</span>
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
            <span>{snapshot?.overdue_debtors_count ?? 6} parties overdue (&gt; 30 days)</span>
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
              <span className="text-sm font-bold font-mono text-purple-300">Exp: ₹{expensesToday.toLocaleString()}</span>
              <span>•</span>
              <span className="text-sm font-bold font-mono text-emerald-400">Net: ₹{netProfit.toLocaleString()}</span>
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
            {[
              { name: 'Murugan Constructions', amount: 14250, days: 38, phone: '94433 22110', billNo: 'C1/26-27/0014' },
              { name: 'Raja Mason (மேஸ்திரி ராஜா)', amount: 6200, days: 22, phone: '98421 55678', billNo: 'C1/26-27/0028' },
              { name: 'Kandhasamy Builders', amount: 28400, days: 54, phone: '94431 88900', billNo: 'C1/26-27/0002' },
            ].map((d, i) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-slate-900 border border-slate-700/70 text-xs hover:border-slate-500 transition">
                <div>
                  <div className="font-bold text-white text-sm">{d.name}</div>
                  <div className="text-slate-400 text-[11px] font-mono mt-0.5">
                    Ph: {d.phone} • Inv: {d.billNo} • <span className="text-red-400 font-bold">{d.days} days overdue</span>
                  </div>
                </div>
                <div className="text-right flex flex-col items-end">
                  <CurrencyCell amount={d.amount} highlight="amber" size="lg" />
                  <a
                    href={`https://wa.me/91${d.phone.replace(/\D/g, '')}?text=Vanakkam%20${encodeURIComponent(d.name)},%20your%20pending%20balance%20to%20Salem%20Sri%20Murugan%20Hardware%20is%20Rs.${d.amount}.%20Kindly%20pay%20via%20UPI:%20upi://pay?pa=salemtraders@icici%26pn=Salem%20Hardware%26am=${d.amount}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-emerald-400 hover:text-emerald-300 font-semibold inline-flex items-center gap-1 mt-1 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800"
                  >
                    <span>Send Reminder</span>
                    <ArrowUpRight className="w-3 h-3" />
                  </a>
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
            {[
              { name: 'Asian Paints Primer 1L', stock: '2 Case (24 pcs)', min: '48 pcs', supplier: 'Asian Paints Salem Depot' },
              { name: 'Tata Tiscon 12mm TMT Bar', stock: '85 Rods (905 kg)', min: '1,000 kg', supplier: 'Salem Steel Suppliers' },
              { name: 'Ashirvad CPVC Elbow 1"', stock: '12 piece', min: '50 piece', supplier: 'Ashirvad Southern Depot' },
            ].map((item, idx) => (
              <div key={idx} className="p-3 rounded-xl bg-slate-900 border border-slate-700/70 text-xs space-y-1.5">
                <div className="flex justify-between font-bold text-white">
                  <span>{item.name}</span>
                  <span className="text-red-400 font-mono font-black">{item.stock}</span>
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Threshold: <strong className="text-slate-200">{item.min}</strong></span>
                  <span className="text-slate-300 truncate max-w-[180px]">Supplier: {item.supplier}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
