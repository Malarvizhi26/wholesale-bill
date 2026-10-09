import React from 'react';
import { IndianRupee, TrendingUp, AlertTriangle, Wallet, Users, ArrowUpRight, Clock, ShieldAlert } from 'lucide-react';
import type { Language } from '../types';

interface DashboardProps {
  language: Language;
}

export const Dashboard: React.FC<DashboardProps> = ({ language }) => {
  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-5">
      {/* Morning Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-gradient-to-r from-slate-800 to-slate-800/90 p-5 rounded-2xl border border-slate-700 shadow-lg">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-black text-white">
              {language === 'ta' ? 'வணக்கம், உரிமையாளர் காலை அறிக்கை' : 'Good Morning, Owner Snapshot'}
            </h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-mono">
              Live &lt; 1s
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Salem Sri Murugan Hardware & Steels • Counter 1 Active • 09-Oct-2026
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-slate-300 bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-700">
            Snapshot Refreshed: Just Now
          </span>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Today's Sales */}
        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>{language === 'ta' ? 'இன்றைய விற்பனை' : "Today's Sales"}</span>
            <span className="p-1.5 rounded-lg bg-emerald-950 text-emerald-400"><TrendingUp className="w-4 h-4" /></span>
          </div>
          <div className="text-2xl font-black font-mono text-white mt-2">₹68,450</div>
          <div className="text-[11px] text-emerald-400 flex items-center gap-1 mt-1 font-semibold">
            <span>+14.2%</span>
            <span className="text-slate-400 font-normal">vs yesterday</span>
          </div>
        </div>

        {/* Card 2: Gross Margin Estimate */}
        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>{language === 'ta' ? 'மொத்த லாபம் (WAC)' : 'Gross Margin Estimate'}</span>
            <span className="p-1.5 rounded-lg bg-emerald-950 text-emerald-400"><IndianRupee className="w-4 h-4" /></span>
          </div>
          <div className="text-2xl font-black font-mono text-emerald-400 mt-2">₹16,975</div>
          <div className="text-[11px] text-slate-400 mt-1 font-mono">
            Weighted Average Margin: <span className="text-emerald-300 font-bold">24.8%</span>
          </div>
        </div>

        {/* Card 3: Receivables & Overdue */}
        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>{language === 'ta' ? 'வர வேண்டிய கடன்' : 'Outstanding Credit'}</span>
            <span className="p-1.5 rounded-lg bg-amber-950 text-amber-400"><Clock className="w-4 h-4" /></span>
          </div>
          <div className="text-2xl font-black font-mono text-amber-400 mt-2">₹1,42,800</div>
          <div className="text-[11px] text-red-400 flex items-center gap-1 mt-1 font-semibold">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>6 parties overdue (&gt; 30 days)</span>
          </div>
        </div>

        {/* Card 4: Cash in Hand */}
        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>{language === 'ta' ? 'கையிருப்பு ரொக்கம்' : 'Cash in Hand'}</span>
            <span className="p-1.5 rounded-lg bg-blue-950 text-blue-400"><Wallet className="w-4 h-4" /></span>
          </div>
          <div className="text-2xl font-black font-mono text-blue-400 mt-2">₹28,340</div>
          <div className="text-[11px] text-slate-400 mt-1 font-mono">
            Drawer counted at 12:00 PM
          </div>
        </div>
      </div>

      {/* Middle Section: Top Debtors to Call Today & Low Stock Warnings */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Top Debtors Call List */}
        <div className="lg:col-span-7 bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md space-y-3">
          <div className="flex items-center justify-between border-b border-slate-700 pb-2">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-emerald-400" />
              <h3 className="font-bold text-white text-sm">
                {language === 'ta' ? 'இன்று வசூலிக்க வேண்டியவர்கள்' : "Today's Top Collections to Call"}
              </h3>
            </div>
            <span className="text-[11px] font-mono text-slate-400">Ranked by overdue age</span>
          </div>

          <div className="space-y-2">
            {[
              { name: 'Murugan Constructions', amount: 14250, days: 38, phone: '94433 22110' },
              { name: 'Raja Mason', amount: 6200, days: 22, phone: '98421 55678' },
              { name: 'Kandhasamy Builders', amount: 28400, days: 54, phone: '94431 88900' },
            ].map((d, i) => (
              <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900 border border-slate-700/60 text-xs hover:border-slate-600 transition">
                <div>
                  <div className="font-bold text-white">{d.name}</div>
                  <div className="text-slate-400 text-[11px] font-mono mt-0.5">
                    Ph: {d.phone} • Oldest bill: <span className="text-red-400 font-bold">{d.days} days overdue</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono font-bold text-amber-400 text-sm">₹{d.amount.toLocaleString()}</div>
                  <a
                    href={`https://wa.me/91${d.phone.replace(/\D/g, '')}?text=Vanakkam%20${encodeURIComponent(d.name)},%20gentle%20reminder%20for%20pending%20balance%20Rs.${d.amount}%20to%20Salem%20Hardware.`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[10px] text-emerald-400 hover:underline inline-flex items-center gap-0.5 mt-0.5"
                  >
                    Send WhatsApp Reminder <ArrowUpRight className="w-2.5 h-2.5" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Low Stock Alerts */}
        <div className="lg:col-span-5 bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md space-y-3">
          <div className="flex items-center justify-between border-b border-slate-700 pb-2">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400" />
              <h3 className="font-bold text-white text-sm">
                {language === 'ta' ? 'குறைந்த சரக்கு எச்சரிக்கை' : 'Low-Stock Reorder Warnings'}
              </h3>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-red-950 text-red-300 font-bold">
              3 Items
            </span>
          </div>

          <div className="space-y-2">
            {[
              { name: 'Asian Paints Primer 1L', stock: '2 Case (24 pcs)', min: '48 pcs', supplier: 'Asian Paints Salem' },
              { name: '12mm TMT Rod Fe500D', stock: '85 Rods (905 kg)', min: '1000 kg', supplier: 'Salem Steel' },
              { name: 'CPVC Elbow 1 inch', stock: '12 pcs', min: '50 pcs', supplier: 'Ashirvad Depot' },
            ].map((item, idx) => (
              <div key={idx} className="p-2.5 rounded-lg bg-slate-900 border border-slate-700/60 text-xs space-y-1">
                <div className="flex justify-between font-bold text-white">
                  <span>{item.name}</span>
                  <span className="text-red-400 font-mono">{item.stock}</span>
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Min threshold: {item.min}</span>
                  <span className="text-slate-300">Supplier: {item.supplier}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
