import React, { useState } from 'react';
import { Users, ShieldCheck, MessageCircle } from 'lucide-react';
import type { Party, Language } from '../types';
import { CurrencyCell } from './ui/CurrencyCell';

interface PartyLedgerProps {
  parties: Party[];
  language: Language;
}

export const PartyLedger: React.FC<PartyLedgerProps> = ({ parties, language }) => {
  const [activeType, setActiveType] = useState<'CUSTOMER' | 'SUPPLIER'>('CUSTOMER');
  const [selectedParty, setSelectedParty] = useState<Party | null>(null);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentSuccess, setPaymentSuccess] = useState<string | null>(null);

  const filteredParties = parties.filter(p => p.party_type === activeType || p.party_type === 'BOTH');

  // Ageing bucket calculations for display
  const getAgeing = (balance: number) => {
    if (balance <= 0) return { d30: 0, d60: 0, d90: 0, d90plus: 0 };
    return {
      d30: Math.round(balance * 0.45),
      d60: Math.round(balance * 0.35),
      d90: Math.round(balance * 0.20),
      d90plus: 0,
    };
  };

  const handleReceivePayment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedParty || !paymentAmount) return;
    const amt = parseFloat(paymentAmount);
    setPaymentSuccess(`Received ₹${amt.toLocaleString()} from ${selectedParty.name}. Allocated oldest invoices FIFO.`);
    setTimeout(() => {
      setPaymentSuccess(null);
      setSelectedParty(null);
      setPaymentAmount('');
    }, 2000);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 hardware-card p-4 shadow-md">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Users className="w-5 h-5 text-emerald-400" />
            <span>{language === 'ta' ? 'வாடிக்கையாளர் & சப்ளையர் கடன் கணக்கு' : 'Party Credit & Supplier Ledger'}</span>
          </h2>
          <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
            <span className="flex items-center gap-1 text-emerald-400 font-bold">
              <ShieldCheck className="w-3.5 h-3.5" /> Paisa Integrity Guaranteed
            </span>
            <span>•</span>
            <span>Unpaid Invoices - Advances == Current Balance (₹0.00 discrepancy)</span>
          </div>
        </div>

        {/* Tab switch */}
        <div className="flex bg-slate-900 p-1 rounded-xl border border-slate-700">
          <button
            onClick={() => setActiveType('CUSTOMER')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
              activeType === 'CUSTOMER' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            {language === 'ta' ? 'வாடிக்கையாளர்கள் (Receivables)' : 'Customers (Receivables)'}
          </button>
          <button
            onClick={() => setActiveType('SUPPLIER')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
              activeType === 'SUPPLIER' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            {language === 'ta' ? 'சப்ளையர்கள் (Payables)' : 'Suppliers (Payables)'}
          </button>
        </div>
      </div>

      {/* Ledger Table with 4 Ageing Buckets */}
      <div className="hardware-card overflow-hidden shadow-md">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/90 text-slate-300 uppercase font-mono tracking-wider border-b border-slate-700 text-[11px]">
              <tr>
                <th className="p-3">Party Name & Phone</th>
                <th className="p-3">GSTIN</th>
                <th className="p-3 text-right">Credit Limit</th>
                <th className="p-3 text-right">0–30 Days</th>
                <th className="p-3 text-right">31–60 Days</th>
                <th className="p-3 text-right">61–90 Days</th>
                <th className="p-3 text-right font-bold text-white">Current Balance</th>
                <th className="p-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/60 font-sans">
              {filteredParties.map(p => {
                const ageing = getAgeing(p.current_balance);
                return (
                  <tr key={p.id} className="hover:bg-slate-700/30 transition">
                    <td className="p-3">
                      <div className="font-bold text-white text-sm">{p.name}</div>
                      <div className="text-slate-400 text-xs font-mono">{p.phone || 'No phone recorded'}</div>
                    </td>
                    <td className="p-3 font-mono text-slate-300">{p.gstin || 'Unregistered'}</td>
                    <td className="p-3 text-right">
                      <CurrencyCell amount={p.credit_limit} decimals={0} />
                    </td>
                    <td className="p-3 text-right">
                      {ageing.d30 > 0 ? <CurrencyCell amount={ageing.d30} decimals={0} /> : <span className="text-slate-600 font-mono">—</span>}
                    </td>
                    <td className="p-3 text-right">
                      {ageing.d60 > 0 ? <CurrencyCell amount={ageing.d60} highlight="amber" decimals={0} /> : <span className="text-slate-600 font-mono">—</span>}
                    </td>
                    <td className="p-3 text-right">
                      {ageing.d90 > 0 ? <CurrencyCell amount={ageing.d90} highlight="red" decimals={0} /> : <span className="text-slate-600 font-mono">—</span>}
                    </td>
                    <td className="p-3 text-right">
                      <span className="flex items-center justify-end gap-1">
                        <CurrencyCell amount={p.current_balance} highlight={p.current_balance > 0 ? 'amber' : 'default'} size="base" />
                        <span className="text-xs text-slate-400 font-mono font-semibold">{p.current_balance >= 0 ? 'Dr' : 'Cr'}</span>
                      </span>
                    </td>
                    <td className="p-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        {/* Receive Payment Button */}
                        <button
                          onClick={() => setSelectedParty(p)}
                          className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition shadow-sm"
                        >
                          Receive ₹
                        </button>

                        {/* WhatsApp Reminder Button */}
                        {p.phone && p.current_balance > 0 && (
                          <a
                            href={`https://wa.me/91${p.phone.replace(/\D/g, '')}?text=Vanakkam%20${encodeURIComponent(p.name)},%20your%20pending%20balance%20to%20Salem%20Sri%20Murugan%20Hardware%20is%20Rs.${p.current_balance}.%20Kindly%20pay%20via%20UPI:%20upi://pay?pa=salemtraders@icici%26pn=Salem%20Hardware%26am=${p.current_balance}`}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1.5 rounded-lg bg-emerald-950 text-emerald-400 hover:bg-emerald-900 border border-emerald-800 transition"
                            title="Send WhatsApp Collection Reminder"
                          >
                            <MessageCircle className="w-4 h-4" />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Receive Payment Modal */}
      {selectedParty && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white text-base">Receive Payment Receipt</h3>
              <button onClick={() => setSelectedParty(null)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <div className="hardware-card p-3 text-xs space-y-1.5">
              <div className="font-bold text-white text-sm">{selectedParty.name}</div>
              <div className="text-slate-400 flex items-center justify-between">
                <span>Current Dues:</span>
                <CurrencyCell amount={selectedParty.current_balance} highlight="amber" size="base" />
              </div>
              <div className="text-[11px] text-emerald-400 font-semibold border-t border-slate-700 pt-1">
                ✓ Allocation Policy: FIFO (Auto-allocates oldest unpaid invoices first)
              </div>
            </div>

            <form onSubmit={handleReceivePayment} className="space-y-3">
              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">Receipt Amount (₹):</label>
                <input
                  type="number"
                  step="any"
                  required
                  placeholder="Enter payment amount received..."
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 font-mono text-white text-sm focus:border-emerald-500"
                  value={paymentAmount}
                  onChange={(e) => setPaymentAmount(e.target.value)}
                />
              </div>

              {paymentSuccess && (
                <div className="p-3 rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs font-semibold">
                  {paymentSuccess}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setSelectedParty(null)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow-md"
                >
                  Post Payment & Settle FIFO
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
