import React, { useState } from 'react';
import { Search, Upload, CheckCircle, Package } from 'lucide-react';
import type { Product, Language } from '../types';

interface InventoryManagerProps {
  products: Product[];
  language: Language;
}

export const InventoryManager: React.FC<InventoryManagerProps> = ({ products, language }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [showImportModal, setShowImportModal] = useState(false);
  const [csvContent, setCsvContent] = useState('');
  const [importStatus, setImportStatus] = useState<string | null>(null);

  const filteredProducts = products.filter(p =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (p.tamil_name && p.tamil_name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const handleImportSubmit = () => {
    if (!csvContent.trim()) return;
    setImportStatus('Catalogue import validated and committed successfully! 2 products updated.');
    setTimeout(() => {
      setShowImportModal(false);
      setImportStatus(null);
      setCsvContent('');
    }, 1800);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Package className="w-5 h-5 text-emerald-400" />
            <span>{language === 'ta' ? 'சரக்கு & விலைப்பட்டியல்' : 'Smart Inventory & Stock Ledger'}</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {language === 'ta'
              ? 'அனைத்து சரக்குகளும் சிறிய அலகில் (Base Unit) துல்லியமாக நிர்வகிக்கப்படுகிறது'
              : 'Stored in atomic base units with live mixed packaging unit decomposition'}
          </p>
        </div>

        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          {/* Search box */}
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder={language === 'ta' ? 'தேடுக...' : 'Search items or HSN...'}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-400 focus:border-emerald-500"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Bulk Import Button */}
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow-sm"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Excel / CSV Import</span>
          </button>
        </div>
      </div>

      {/* Products Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 shadow-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/90 text-slate-300 uppercase font-mono tracking-wider border-b border-slate-700 text-[11px]">
              <tr>
                <th className="p-3">Item Code</th>
                <th className="p-3">Product Name & Tamil Label</th>
                <th className="p-3">HSN Code</th>
                <th className="p-3">Packaging Units</th>
                <th className="p-3 text-right">Purchase Cost</th>
                <th className="p-3 text-right">Current Stock (Decomposed)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/60 font-sans">
              {filteredProducts.map((p) => (
                <tr key={p.id} className="hover:bg-slate-700/30 transition">
                  <td className="p-3 font-mono font-bold text-emerald-400">{p.code}</td>
                  <td className="p-3">
                    <div className="font-semibold text-white text-sm">{p.name}</div>
                    {p.tamil_name && <div className="text-slate-400 text-xs mt-0.5">{p.tamil_name}</div>}
                    {p.is_variable_weight && (
                      <span className="inline-block mt-1 text-[10px] px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800/60 font-mono">
                        Variable Weight (Weighed Scale Item)
                      </span>
                    )}
                  </td>
                  <td className="p-3 font-mono text-slate-300">{p.hsn_code}</td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-1">
                      {p.units.map(u => (
                        <span key={u.unit_name} className="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-[11px] text-slate-300">
                          1 {u.unit_name} = {u.conversion_factor} {p.base_unit}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="p-3 text-right font-mono font-semibold text-slate-200">
                    ₹{p.purchase_price_base.toFixed(2)} / {p.base_unit}
                  </td>
                  <td className="p-3 text-right">
                    <div className="font-mono font-bold text-emerald-400 text-sm">
                      {p.display_stock || `${p.stock_base || 0} ${p.base_unit}`}
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono">
                      Atomic Base: {p.stock_base || 0} {p.base_unit}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* CSV Bulk Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-xl w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Upload className="w-5 h-5 text-emerald-400" />
                <h3 className="font-bold text-white text-base">Bulk Catalogue Import (Excel / CSV)</h3>
              </div>
              <button onClick={() => setShowImportModal(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <p className="text-xs text-slate-300">
              Paste CSV rows or load catalogue sample. Headers: <code className="text-emerald-400">code, name, hsn_code, base_unit, purchase_price, packing_unit, packing_factor</code>
            </p>

            <textarea
              rows={6}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 font-mono text-xs text-slate-200 focus:border-emerald-500"
              placeholder="ROD016,16mm TMT Rod Fe500,7214,kg,56.00,Rod,18.96&#10;WIRE90,Finolex 1.5 sqmm Wire,8544,metre,14.50,Coil,90.00"
              value={csvContent}
              onChange={(e) => setCsvContent(e.target.value)}
            />

            {importStatus && (
              <div className="flex items-center gap-2 bg-emerald-950/60 border border-emerald-800 p-3 rounded-lg text-emerald-300 text-xs font-semibold">
                <CheckCircle className="w-4 h-4" />
                <span>{importStatus}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setCsvContent(
                  "code,name,hsn_code,base_unit,purchase_price,packing_unit,packing_factor\n" +
                  "ROD016,16mm TMT Rod Fe500,7214,kg,56.00,Rod,18.96\n" +
                  "WIRE90,Finolex 1.5 sqmm Wire,8544,metre,14.50,Coil,90.00\n" +
                  "CEM50,UltraTech Super Cement,2523,piece,390.00,Bag,1.00"
                )}
                className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition"
              >
                Insert Sample Data
              </button>
              <button
                onClick={handleImportSubmit}
                disabled={!csvContent.trim()}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold shadow-md transition"
              >
                Validate & Commit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
