import React from 'react';
import { FileText, Download, Printer } from 'lucide-react';
import type { Language } from '../types';

interface ReportsViewProps {
  language: Language;
}

export const ReportsView: React.FC<ReportsViewProps> = ({ language }) => {
  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-emerald-400" />
            <span>{language === 'ta' ? 'ஜிஎஸ்டி & வணிக அறிக்கைகள்' : 'Profit & GST Compliance Reports'}</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {language === 'ta'
              ? 'ஜிஎஸ்டிஆர்-1 தாக்கல் செய்ய துல்லியமான HSN மற்றும் வரி பிரிப்புகள்'
              : 'Exact HSN summary, GSTR-1 export, and product margin reports'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => window.print()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            <Printer className="w-3.5 h-3.5" />
            <span>Print Report</span>
          </button>
          <button
            onClick={() => alert("Downloading GSTR-1 Excel Summary...")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export GSTR-1 Excel</span>
          </button>
        </div>
      </div>

      {/* HSN Summary Table for GSTR-1 */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 shadow-md p-4 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-700 pb-2">
          <h3 className="font-bold text-white text-sm">GSTR-1 HSN-Wise Summary (Today)</h3>
          <span className="text-xs font-mono text-emerald-400">Total Taxable: ₹52,430.00</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/90 text-slate-300 uppercase font-mono tracking-wider border-b border-slate-700 text-[11px]">
              <tr>
                <th className="p-2.5">HSN Code</th>
                <th className="p-2.5">Description</th>
                <th className="p-2.5 text-center">GST Rate</th>
                <th className="p-2.5 text-right">Taxable Value</th>
                <th className="p-2.5 text-right">CGST</th>
                <th className="p-2.5 text-right">SGST</th>
                <th className="p-2.5 text-right">Total Invoice Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/60 font-sans font-mono">
              {[
                { hsn: '7214', desc: 'TMT Steel Bars', rate: '18%', taxable: 24500.00, cgst: 2205.00, sgst: 2205.00, total: 28910.00 },
                { hsn: '7318', desc: 'SS Screws & Fasteners', rate: '18%', taxable: 8450.00, cgst: 760.50, sgst: 760.50, total: 9971.00 },
                { hsn: '3208', desc: 'Paints & Primers', rate: '18%', taxable: 11200.00, cgst: 1008.00, sgst: 1008.00, total: 13216.00 },
                { hsn: '3917', desc: 'CPVC Pipes & Fittings', rate: '18%', taxable: 5100.00, cgst: 459.00, sgst: 459.00, total: 6018.00 },
                { hsn: '7217', desc: 'GI Binding Wire', rate: '18%', taxable: 3180.00, cgst: 286.20, sgst: 286.20, total: 3752.40 },
              ].map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-700/30 transition text-slate-200">
                  <td className="p-2.5 font-bold text-emerald-400">{row.hsn}</td>
                  <td className="p-2.5 font-sans">{row.desc}</td>
                  <td className="p-2.5 text-center text-slate-400">{row.rate}</td>
                  <td className="p-2.5 text-right font-semibold">₹{row.taxable.toFixed(2)}</td>
                  <td className="p-2.5 text-right text-slate-400">₹{row.cgst.toFixed(2)}</td>
                  <td className="p-2.5 text-right text-slate-400">₹{row.sgst.toFixed(2)}</td>
                  <td className="p-2.5 text-right font-bold text-white">₹{row.total.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
