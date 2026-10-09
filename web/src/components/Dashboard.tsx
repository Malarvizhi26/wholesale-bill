import React from 'react';
import { TrendingUp, AlertTriangle, Wallet, Users, ArrowUpRight, Clock, ShieldAlert, CheckCircle2 } from 'lucide-react';
import type { Language } from '../types';
import { CurrencyCell } from './ui/CurrencyCell';

interface DashboardProps {
  language: Language;
}

export const Dashboard: React.FC<DashboardProps> = ({ language }) => {
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
            Salem Sri Murugan Hardware & Steels • Counter 1 Online • 09-Oct-2026
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-emerald-400 bg-slate-900/90 px-3.5 py-1.5 rounded-xl border border-slate-700/80 flex items-center gap-1.5 shadow-inner">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>Pre-calculated Ledger Snapshots</span>
          </span>
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
            <CurrencyCell amount={68450} size="3xl" highlight="default" />
          </div>
          <div className="text-[11px] text-emerald-400 flex items-center gap-1 font-bold">
            <span>+14.2%</span>
            <span className="text-slate-400 font-normal">vs yesterday (₹59,940)</span>
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
            <CurrencyCell amount={16975} size="3xl" highlight="emerald" />
          </div>
          <div className="text-[11px] text-slate-300 font-mono">
            Weighted Average Margin: <span className="text-emerald-400 font-black">24.8%</span>
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
            <CurrencyCell amount={142800} size="3xl" highlight="amber" />
          </div>
          <div className="text-[11px] text-red-400 flex items-center gap-1 font-bold">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>6 parties overdue (&gt; 30 days)</span>
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
            <CurrencyCell amount={28340} size="3xl" highlight="default" />
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Physical drawer cash counted at 12:00 PM
          </div>
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
              3 Items
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
