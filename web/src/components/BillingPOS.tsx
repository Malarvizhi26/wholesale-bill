import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, Plus, Trash2, Printer, Share2, PauseCircle, 
  AlertTriangle, X, ShieldAlert, Split
} from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import type { Product, Party, POSLineItem, BillSummary, HeldBill, Language, ProductUnit } from '../types';
import { api } from '../api/client';
import { KbdBadge } from './ui/KbdBadge';
import { CurrencyCell } from './ui/CurrencyCell';

interface BillingPOSProps {
  products: Product[];
  parties: Party[];
  language: Language;
}

export const BillingPOS: React.FC<BillingPOSProps> = ({ products, parties, language }) => {
  // Active Bill State
  const [selectedParty, setSelectedParty] = useState<Party | null>(null);
  const [lines, setLines] = useState<POSLineItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Product[]>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [selectedSearchIdx, setSelectedSearchIdx] = useState(0);
  const [paymentMode, setPaymentMode] = useState<'CASH' | 'UPI' | 'CREDIT' | 'SPLIT'>('CASH');
  const [paidAmount, setPaidAmount] = useState<number | undefined>(undefined);
  const [invoiceNumber, setInvoiceNumber] = useState('C1/26-27/0001');

  // Split payment state
  const [cashPart, setCashPart] = useState('');
  const [upiPart, setUpiPart] = useState('');
  const [creditPart, setCreditPart] = useState('');

  // Modals
  const [showReceiptModal, setShowReceiptModal] = useState(false);
  const [showHoldModal, setShowHoldModal] = useState(false);
  const [showSplitModal, setShowSplitModal] = useState(false);
  const [showPinModal, setShowPinModal] = useState(false);
  const [ownerPin, setOwnerPin] = useState('');
  const [pinError, setPinError] = useState(false);
  const [isPinApproved, setIsPinApproved] = useState(false);
  const [heldBills, setHeldBills] = useState<HeldBill[]>([]);

  // Refs for keyboard shortcuts
  const searchInputRef = useRef<HTMLInputElement>(null);
  const partySelectRef = useRef<HTMLSelectElement>(null);

  // Bill Summary
  const summary: BillSummary = api.calculateClientBill(lines, '33', '33', paidAmount);

  // Credit limit breach check
  const isCreditOverLimit = Boolean(
    selectedParty && selectedParty.credit_limit > 0 && 
    (selectedParty.current_balance + summary.grandTotal) > selectedParty.credit_limit
  );

  // Keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // F2: New Bill
      if (e.key === 'F2') {
        e.preventDefault();
        startNewBill();
      }
      // F3: Focus Item Search
      else if (e.key === 'F3') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
      // F4: Focus Customer
      else if (e.key === 'F4') {
        e.preventDefault();
        partySelectRef.current?.focus();
      }
      // F6: Hold Bill
      else if (e.key === 'F6') {
        e.preventDefault();
        holdCurrentBill();
      }
      // F7: Recall Held Bill
      else if (e.key === 'F7') {
        e.preventDefault();
        setShowHoldModal(true);
      }
      // F8: Split Payment
      else if (e.key === 'F8') {
        e.preventDefault();
        if (lines.length > 0) {
          setCashPart((summary.grandTotal / 2).toFixed(2));
          setUpiPart((summary.grandTotal / 2).toFixed(2));
          setCreditPart('0.00');
          setShowSplitModal(true);
        }
      }
      // F9: Quick Cash Bill & Print
      else if (e.key === 'F9') {
        e.preventDefault();
        attemptCheckout('CASH');
      }
      // F10: Settle Bill Modal
      else if (e.key === 'F10') {
        e.preventDefault();
        attemptCheckout(paymentMode);
      }
      // Escape closes open modals
      else if (e.key === 'Escape') {
        setShowSearchResults(false);
        setShowReceiptModal(false);
        setShowHoldModal(false);
        setShowSplitModal(false);
        setShowPinModal(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [lines, selectedParty, summary, paymentMode, isCreditOverLimit, isPinApproved]);

  // Product search filter with keyboard arrow navigation
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }

    const q = searchQuery.toLowerCase();
    const filtered = products.filter(
      p => p.name.toLowerCase().includes(q) ||
           p.code.toLowerCase().includes(q) ||
           (p.tamil_name && p.tamil_name.toLowerCase().includes(q))
    );
    setSearchResults(filtered);
    setShowSearchResults(filtered.length > 0);
    setSelectedSearchIdx(0);
  }, [searchQuery, products]);

  // Omnibar keyboard navigation (Up/Down/Enter)
  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (!showSearchResults || searchResults.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedSearchIdx(prev => (prev + 1) % searchResults.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedSearchIdx(prev => (prev - 1 + searchResults.length) % searchResults.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const chosen = searchResults[selectedSearchIdx];
      if (chosen) addProductToBill(chosen);
    }
  };

  // Add Product to bill
  const addProductToBill = (prod: Product) => {
    const defaultUnit: ProductUnit = prod.units.find(u => u.is_default_sales_unit) || prod.units[0] || {
      unit_name: prod.base_unit,
      conversion_factor: 1,
      can_buy: true,
      can_sell: true
    };

    let unitPrice = 0;
    if (prod.code === 'SCR001') unitPrice = 185.00;
    else if (prod.code === 'TMT012') unitPrice = 650.00;
    else if (prod.code === 'PNT001') unitPrice = 275.00;
    else if (prod.code === 'PIP001') unitPrice = 85.00;
    else if (prod.code === 'GIW020') unitPrice = 1850.00;
    else unitPrice = prod.purchase_price_base * 1.25;

    const newLine: POSLineItem = {
      id: Math.random().toString(36).substring(7),
      productId: prod.id,
      productCode: prod.code,
      name: prod.name,
      tamilName: prod.tamil_name,
      hsnCode: prod.hsn_code,
      unitName: defaultUnit.unit_name,
      conversionFactor: defaultUnit.conversion_factor,
      quantity: 1,
      isVariableWeight: prod.is_variable_weight,
      actualWeightKg: prod.is_variable_weight ? 10.65 : undefined,
      baseQuantity: defaultUnit.conversion_factor,
      unitPrice,
      discountType: 'FLAT',
      discountValue: 0,
      discountAmount: 0,
      taxableAmount: unitPrice,
      gstRatePercent: 18,
      cgstAmount: 0,
      sgstAmount: 0,
      igstAmount: 0,
      lineTotal: unitPrice,
      availableUnits: prod.units.length > 0 ? prod.units : [defaultUnit],
    };

    setLines(prev => [...prev, newLine]);
    setSearchQuery('');
    setShowSearchResults(false);
  };

  // Update line unit
  const handleUnitChange = (lineId: string, unitName: string) => {
    setLines(prev => prev.map(line => {
      if (line.id !== lineId) return line;
      const foundUnit = line.availableUnits.find(u => u.unit_name === unitName);
      if (!foundUnit) return line;

      let adjustedPrice = line.unitPrice;
      if (foundUnit.conversion_factor === 1 && line.conversionFactor > 1) {
        adjustedPrice = Math.round((line.unitPrice / line.conversionFactor) * 100) / 100;
      } else if (foundUnit.conversion_factor > 1 && line.conversionFactor === 1) {
        adjustedPrice = Math.round((line.unitPrice * foundUnit.conversion_factor) * 100) / 100;
      }

      return {
        ...line,
        unitName: foundUnit.unit_name,
        conversionFactor: foundUnit.conversion_factor,
        unitPrice: adjustedPrice,
        baseQuantity: line.quantity * foundUnit.conversion_factor,
      };
    }));
  };

  // Update line quantity
  const handleQuantityChange = (lineId: string, qty: number) => {
    setLines(prev => prev.map(line => {
      if (line.id !== lineId) return line;
      const safeQty = Math.max(0.01, qty);
      return {
        ...line,
        quantity: safeQty,
        baseQuantity: safeQty * line.conversionFactor,
      };
    }));
  };

  // Update line scale weight
  const handleScaleWeightChange = (lineId: string, weightKg: number) => {
    setLines(prev => prev.map(line => {
      if (line.id !== lineId) return line;
      return {
        ...line,
        actualWeightKg: Math.max(0.01, weightKg),
        baseQuantity: Math.max(0.01, weightKg),
      };
    }));
  };

  // Update line price
  const handlePriceChange = (lineId: string, price: number) => {
    setLines(prev => prev.map(line => {
      if (line.id !== lineId) return line;
      return { ...line, unitPrice: Math.max(0, price) };
    }));
  };

  // Update line discount
  const handleDiscountChange = (lineId: string, disc: number) => {
    setLines(prev => prev.map(line => {
      if (line.id !== lineId) return line;
      return { ...line, discountValue: Math.max(0, disc) };
    }));
  };

  // Remove line
  const removeLine = (lineId: string) => {
    setLines(prev => prev.filter(l => l.id !== lineId));
  };

  // Start new bill
  const startNewBill = () => {
    setLines([]);
    setSelectedParty(null);
    setSearchQuery('');
    setPaymentMode('CASH');
    setPaidAmount(undefined);
    setIsPinApproved(false);
    const num = parseInt(invoiceNumber.split('/')[2]) + 1;
    setInvoiceNumber(`C1/26-27/${num.toString().padStart(4, '0')}`);
  };

  // Hold current bill
  const holdCurrentBill = () => {
    if (lines.length === 0) return;
    const newHeld: HeldBill = {
      id: Math.random().toString(36).substring(7),
      heldAt: new Date().toLocaleTimeString(),
      partyName: selectedParty ? selectedParty.name : 'Walk-in Customer',
      lines: [...lines],
      grandTotal: summary.grandTotal,
    };
    setHeldBills(prev => [...prev, newHeld]);
    startNewBill();
  };

  // Recall held bill
  const recallBill = (held: HeldBill) => {
    setLines(held.lines);
    setHeldBills(prev => prev.filter(h => h.id !== held.id));
    setShowHoldModal(false);
  };

  // Checkout with credit check protection
  const attemptCheckout = (mode: 'CASH' | 'UPI' | 'CREDIT' | 'SPLIT') => {
    if (lines.length === 0) return;
    setPaymentMode(mode);

    // If credit mode or customer exceeds limit without override PIN
    if (mode === 'CREDIT' && isCreditOverLimit && !isPinApproved) {
      setShowPinModal(true);
      return;
    }

    setShowReceiptModal(true);
  };

  // Verify supervisor PIN
  const handlePinSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (ownerPin === '1234' || ownerPin === '0000') {
      setIsPinApproved(true);
      setShowPinModal(false);
      setShowReceiptModal(true);
      setPinError(false);
      setOwnerPin('');
    } else {
      setPinError(true);
    }
  };

  // Dynamic UPI QR code URI
  const upiIntentUri = `upi://pay?pa=salemtraders@icici&pn=Salem%20Sri%20Murugan%20Hardware&am=${summary.grandTotal.toFixed(2)}&cu=INR&tn=Invoice_${invoiceNumber}`;

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
      {/* Top Customer Station & Credit Bar */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 hardware-card p-3 shadow-md">
        {/* Customer Selector */}
        <div className="md:col-span-5 flex items-center gap-2">
          <label className="text-xs font-bold text-slate-300 whitespace-nowrap flex items-center gap-1.5">
            <span>{language === 'ta' ? 'வாடிக்கையாளர்:' : 'Customer:'}</span>
            <KbdBadge>F4</KbdBadge>
          </label>
          <select
            ref={partySelectRef}
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:border-emerald-500 font-medium"
            value={selectedParty?.id || ''}
            onChange={(e) => {
              const party = parties.find(p => p.id === e.target.value) || null;
              setSelectedParty(party);
              setIsPinApproved(false);
            }}
          >
            <option value="">Walk-in Retail (சில்லறை விற்பனை)</option>
            {parties.filter(p => p.party_type === 'CUSTOMER').map(p => (
              <option key={p.id} value={p.id}>
                {p.name} {p.phone ? `(${p.phone})` : ''} - Bal: ₹{p.current_balance.toFixed(0)}
              </option>
            ))}
          </select>
        </div>

        {/* Customer Balance & Credit Alert Badge */}
        <div className="md:col-span-4 flex items-center gap-2 text-xs">
          {selectedParty ? (
            <div className="flex items-center justify-between bg-slate-900/90 px-3 py-1.5 rounded-lg border border-slate-700/80 w-full">
              <div className="flex items-center gap-2">
                <span className="text-slate-400">Balance:</span>
                <CurrencyCell amount={selectedParty.current_balance} highlight={selectedParty.current_balance > 0 ? 'amber' : 'default'} />
                <span className="text-slate-600">|</span>
                <span className="text-slate-400">Limit:</span>
                <span className="font-mono text-slate-300">₹{selectedParty.credit_limit.toLocaleString()}</span>
              </div>
              {isCreditOverLimit && (
                <span className="flex items-center gap-1 text-red-400 font-bold bg-red-950/70 px-2 py-0.5 rounded border border-red-800 text-[10px]">
                  <AlertTriangle className="w-3 h-3" /> Over Limit
                </span>
              )}
            </div>
          ) : (
            <span className="text-slate-400 text-xs italic bg-slate-900/50 px-3 py-1.5 rounded-lg border border-slate-800">
              Retail Price List • Cash Settle
            </span>
          )}
        </div>

        {/* Invoice Number & Held Tray */}
        <div className="md:col-span-3 flex items-center justify-end gap-2 text-xs">
          <span className="bg-slate-900 px-3 py-1 rounded-lg border border-slate-700 font-mono text-emerald-400 font-black tracking-wide">
            {invoiceNumber}
          </span>
          {heldBills.length > 0 && (
            <button
              onClick={() => setShowHoldModal(true)}
              className="flex items-center gap-1.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2.5 py-1 rounded-lg font-bold hover:bg-amber-500/30 transition"
            >
              <PauseCircle className="w-3.5 h-3.5" />
              <span>Held ({heldBills.length})</span>
              <KbdBadge variant="amber">F7</KbdBadge>
            </button>
          )}
        </div>
      </div>

      {/* Main Billing Grid & Totals Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left: Omnibar & Lines Table */}
        <div className="lg:col-span-8 space-y-3">
          {/* Omnibar (F3) */}
          <div className="relative">
            <div className="flex items-center gap-2.5 bg-slate-800 border-2 border-emerald-500/60 rounded-xl px-3.5 py-2.5 shadow-lg shadow-emerald-950/20">
              <Search className="w-5 h-5 text-emerald-400" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder={language === 'ta' ? 'பொருள் பெயர் / பார்கோடு ஸ்கேன் செய்க (F3)...' : 'Scan barcode or type product name (e.g. Screws, TMT, Paint) [F3]...'}
                className="w-full bg-transparent text-white placeholder-slate-400 text-sm focus:outline-none font-medium"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
              />
              <KbdBadge size="sm">F3</KbdBadge>
            </div>

            {/* Dropdown Suggestions with Arrow Selection */}
            {showSearchResults && (
              <div className="absolute top-full left-0 right-0 mt-1.5 bg-slate-800 border border-slate-600 rounded-xl shadow-2xl z-40 max-h-64 overflow-y-auto">
                {searchResults.map((prod, idx) => (
                  <div
                    key={prod.id}
                    onClick={() => addProductToBill(prod)}
                    className={`flex items-center justify-between p-3 cursor-pointer border-b border-slate-700/50 text-xs transition ${
                      idx === selectedSearchIdx ? 'bg-emerald-950/60 border-l-4 border-l-emerald-400' : 'hover:bg-slate-700/60'
                    }`}
                  >
                    <div>
                      <div className="font-bold text-white flex items-center gap-2">
                        <span>{prod.name}</span>
                        {prod.tamil_name && <span className="text-emerald-400 text-xs">({prod.tamil_name})</span>}
                      </div>
                      <div className="text-slate-400 text-[11px] font-mono mt-0.5">
                        Code: {prod.code} • Base: {prod.base_unit} • HSN: {prod.hsn_code}
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="px-2 py-0.5 rounded bg-emerald-900/60 text-emerald-300 font-mono text-[11px] font-bold border border-emerald-700/50">
                        + Add Line [Enter]
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active Bill Lines Table */}
          <div className="hardware-card overflow-hidden min-h-[360px] flex flex-col justify-between">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/90 text-slate-300 border-b border-slate-700 uppercase font-mono tracking-wider text-[11px]">
                  <tr>
                    <th className="p-2.5 w-10">#</th>
                    <th className="p-2.5">Item Name & Tamil Label</th>
                    <th className="p-2.5 w-24 text-center">Unit</th>
                    <th className="p-2.5 w-24 text-center">Qty</th>
                    <th className="p-2.5 w-24 text-right">Rate (₹)</th>
                    <th className="p-2.5 w-20 text-right">Disc</th>
                    <th className="p-2.5 w-28 text-right">Total (₹)</th>
                    <th className="p-2.5 w-10"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60 font-sans">
                  {lines.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="p-16 text-center text-slate-400 text-sm">
                        <div className="flex flex-col items-center justify-center gap-2">
                          <Search className="w-8 h-8 text-slate-600" />
                          <span>Bill is currently empty. Press <KbdBadge>F3</KbdBadge> to search or scan items.</span>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    lines.map((line, idx) => (
                      <tr key={line.id} className="hover:bg-slate-700/30 transition">
                        <td className="p-2.5 text-slate-400 font-mono">{idx + 1}</td>
                        <td className="p-2.5">
                          <div className="font-bold text-slate-100">{line.name}</div>
                          {line.tamilName && <div className="text-slate-400 text-[11px]">{line.tamilName}</div>}
                          {line.isVariableWeight && (
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className="text-[10px] text-amber-300 font-mono">Scale Wt:</span>
                              <input
                                type="number"
                                step="any"
                                className="w-20 bg-slate-900 border border-amber-600 text-amber-300 px-1 py-0.5 rounded text-[11px] font-mono font-bold"
                                value={line.actualWeightKg || ''}
                                onChange={(e) => handleScaleWeightChange(line.id, parseFloat(e.target.value) || 0)}
                              />
                              <span className="text-[10px] text-amber-400 font-mono">kg</span>
                            </div>
                          )}
                        </td>
                        {/* Unit Picker */}
                        <td className="p-2.5 text-center">
                          <select
                            className="bg-slate-900 border border-slate-700 text-white rounded-lg px-2 py-1 text-xs font-semibold focus:border-emerald-500"
                            value={line.unitName}
                            onChange={(e) => handleUnitChange(line.id, e.target.value)}
                          >
                            {line.availableUnits.map(u => (
                              <option key={u.unit_name} value={u.unit_name}>
                                {u.unit_name}
                              </option>
                            ))}
                          </select>
                        </td>
                        {/* Quantity Input */}
                        <td className="p-2.5 text-center">
                          <input
                            type="number"
                            min="0.01"
                            step="any"
                            className="w-18 bg-slate-900 border border-slate-700 text-white text-center rounded-lg px-2 py-1 text-xs font-mono font-bold focus:border-emerald-500"
                            value={line.quantity}
                            onChange={(e) => handleQuantityChange(line.id, parseFloat(e.target.value) || 0)}
                          />
                        </td>
                        {/* Rate Input */}
                        <td className="p-2.5 text-right">
                          <input
                            type="number"
                            step="any"
                            className="w-20 bg-slate-900 border border-slate-700 text-white text-right rounded-lg px-2 py-1 text-xs font-mono font-bold focus:border-emerald-500"
                            value={line.unitPrice}
                            onChange={(e) => handlePriceChange(line.id, parseFloat(e.target.value) || 0)}
                          />
                        </td>
                        {/* Discount Input */}
                        <td className="p-2.5 text-right">
                          <input
                            type="number"
                            step="any"
                            className="w-16 bg-slate-900 border border-slate-700 text-amber-300 text-right rounded-lg px-1.5 py-1 text-xs font-mono focus:border-emerald-500"
                            value={line.discountValue}
                            onChange={(e) => handleDiscountChange(line.id, parseFloat(e.target.value) || 0)}
                          />
                        </td>
                        {/* Line Total */}
                        <td className="p-2.5 text-right">
                          <CurrencyCell amount={line.lineTotal} highlight="emerald" size="base" />
                        </td>
                        {/* Remove */}
                        <td className="p-2.5 text-center">
                          <button
                            onClick={() => removeLine(line.id)}
                            className="text-slate-500 hover:text-red-400 p-1 rounded transition"
                            title="Remove Line Item"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Frequent / Last-Used Quick Items Bar */}
            <div className="bg-slate-900/80 p-2.5 border-t border-slate-700 flex items-center justify-between text-xs text-slate-400">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-slate-300">Quick Items:</span>
                {products.slice(0, 4).map(p => (
                  <button
                    key={p.id}
                    onClick={() => addProductToBill(p)}
                    className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[11px] font-medium transition"
                  >
                    + {p.name.split(' ')[0]}
                  </button>
                ))}
              </div>
              <span className="font-mono text-slate-300">{lines.length} Line Items</span>
            </div>
          </div>
        </div>

        {/* Right: Checkout & Settlement Panel */}
        <div className="lg:col-span-4 space-y-3">
          <div className="hardware-card p-4 shadow-lg space-y-4">
            <div className="flex items-center justify-between border-b border-slate-700 pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">Bill Settlement</span>
              <span className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono font-medium">
                TN GST (CGST+SGST 18%)
              </span>
            </div>

            {/* Calculations Breakdown */}
            <div className="space-y-2 text-xs">
              <div className="flex justify-between text-slate-300">
                <span>Taxable Subtotal:</span>
                <CurrencyCell amount={summary.subtotalTaxable} />
              </div>
              <div className="flex justify-between text-slate-400">
                <span>CGST (9%):</span>
                <CurrencyCell amount={summary.cgstTotal} />
              </div>
              <div className="flex justify-between text-slate-400">
                <span>SGST (9%):</span>
                <CurrencyCell amount={summary.sgstTotal} />
              </div>
              {summary.totalDiscount > 0 && (
                <div className="flex justify-between text-amber-400 font-semibold">
                  <span>Total Savings / Discount:</span>
                  <CurrencyCell amount={-summary.totalDiscount} highlight="amber" />
                </div>
              )}
              {summary.roundOff !== 0 && (
                <div className="flex justify-between text-slate-400">
                  <span>Rupee Round-off:</span>
                  <span className="font-mono">{summary.roundOff > 0 ? `+₹${summary.roundOff.toFixed(2)}` : `-₹${Math.abs(summary.roundOff).toFixed(2)}`}</span>
                </div>
              )}

              {/* Grand Total Box (Large Visual Hierarchy) */}
              <div className="bg-slate-900 p-4 rounded-xl border-2 border-emerald-500/60 mt-3 flex items-center justify-between shadow-inner">
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">Grand Total</div>
                  <CurrencyCell amount={summary.grandTotal} highlight="emerald" size="3xl" />
                </div>
                <div className="text-right">
                  <span className="text-[11px] text-emerald-400 block font-mono font-semibold">Round-off Included</span>
                </div>
              </div>
            </div>

            {/* Payment Mode Selector Tabs */}
            <div className="space-y-2 pt-2 border-t border-slate-700">
              <label className="text-xs font-bold text-slate-300 block">Payment Mode:</label>
              <div className="grid grid-cols-4 gap-1.5">
                {(['CASH', 'UPI', 'CREDIT', 'SPLIT'] as const).map(mode => (
                  <button
                    key={mode}
                    onClick={() => {
                      if (mode === 'SPLIT') {
                        setCashPart((summary.grandTotal / 2).toFixed(2));
                        setUpiPart((summary.grandTotal / 2).toFixed(2));
                        setCreditPart('0.00');
                        setShowSplitModal(true);
                      } else {
                        setPaymentMode(mode);
                      }
                    }}
                    className={`py-2 rounded-lg text-xs font-bold transition ${
                      paymentMode === mode
                        ? 'bg-emerald-600 text-white shadow-md'
                        : 'bg-slate-900 text-slate-300 hover:bg-slate-700 border border-slate-700'
                    }`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>

            {/* Primary Action Buttons */}
            <div className="space-y-2 pt-2">
              <button
                onClick={() => attemptCheckout('CASH')}
                disabled={lines.length === 0}
                className="w-full flex items-center justify-center gap-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white py-3.5 rounded-xl font-bold text-sm shadow-xl shadow-emerald-950/40 transition active:scale-[0.99]"
              >
                <Printer className="w-4 h-4" />
                <span>{language === 'ta' ? 'ரொக்கம் & ரசீது அச்சிடு' : 'Quick Cash & Print'}</span>
                <KbdBadge variant="slate">F9</KbdBadge>
              </button>

              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={holdCurrentBill}
                  disabled={lines.length === 0}
                  className="flex items-center justify-center gap-1.5 bg-slate-900 hover:bg-slate-700 disabled:opacity-50 text-slate-200 py-2.5 rounded-lg text-xs font-semibold border border-slate-700 transition"
                >
                  <PauseCircle className="w-3.5 h-3.5 text-amber-400" />
                  <span>Hold Bill</span>
                  <KbdBadge variant="amber">F6</KbdBadge>
                </button>
                <button
                  onClick={startNewBill}
                  className="flex items-center justify-center gap-1.5 bg-slate-900 hover:bg-slate-700 text-slate-200 py-2.5 rounded-lg text-xs font-semibold border border-slate-700 transition"
                >
                  <Plus className="w-3.5 h-3.5 text-emerald-400" />
                  <span>New Bill</span>
                  <KbdBadge>F2</KbdBadge>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Keyboard Shortcuts Bottom Dock */}
      <footer className="bg-slate-950 p-3 rounded-xl border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400 shadow-md">
        <div className="flex items-center gap-4 flex-wrap">
          <span className="font-bold text-slate-200">Shortcuts Dock:</span>
          <span><KbdBadge>F2</KbdBadge> New</span>
          <span><KbdBadge>F3</KbdBadge> Search</span>
          <span><KbdBadge>F4</KbdBadge> Cust</span>
          <span><KbdBadge variant="amber">F6</KbdBadge> Hold</span>
          <span><KbdBadge variant="amber">F7</KbdBadge> Recall</span>
          <span><KbdBadge>F8</KbdBadge> Split</span>
          <span><KbdBadge>F9</KbdBadge> Cash Print</span>
          <span><KbdBadge>F10</KbdBadge> Settle</span>
        </div>
        <div className="text-[11px] font-mono text-emerald-400 font-bold">
          Zero-Training 30s Counter Loop ⚡
        </div>
      </footer>

      {/* Thermal Receipt Preview Modal */}
      {showReceiptModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Printer className="w-5 h-5 text-emerald-400" />
                <h3 className="font-bold text-white text-base">3-Inch Thermal Receipt Preview</h3>
              </div>
              <button onClick={() => setShowReceiptModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Thermal Slip Simulation */}
            <div className="bg-white text-black p-4 rounded-lg font-mono text-xs shadow-inner space-y-2 select-text max-h-96 overflow-y-auto">
              <div className="text-center font-bold text-sm">SALEM SRI MURUGAN HARDWARE</div>
              <div className="text-center text-[10px]">ஸ்ரீ முருகன் ஹார்ட்வேர்</div>
              <div className="text-center text-[10px]">142 Junction Main Road, Salem - 636004</div>
              <div className="text-center text-[10px]">Ph: 9876543210 • GSTIN: 33AABCS1234F1Z5</div>
              <div className="border-b border-dashed border-black my-1"></div>

              <div className="flex justify-between text-[11px]">
                <span>Bill: {invoiceNumber}</span>
                <span>{new Date().toLocaleDateString('en-GB')} {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
              <div className="text-[11px]">Cust: {selectedParty ? selectedParty.name : 'Walk-in Cash Customer'}</div>
              <div className="border-b border-dashed border-black my-1"></div>

              {/* Items list */}
              <div className="space-y-1">
                {lines.map(l => (
                  <div key={l.id} className="flex justify-between text-[11px]">
                    <div className="truncate w-36">
                      <div>{l.name}</div>
                      <div className="text-[9px] text-gray-600">{l.quantity} {l.unitName} @ ₹{l.unitPrice}</div>
                    </div>
                    <div className="font-bold">₹{l.lineTotal.toFixed(2)}</div>
                  </div>
                ))}
              </div>

              <div className="border-b border-dashed border-black my-1"></div>
              <div className="flex justify-between">
                <span>Taxable Subtotal:</span>
                <span>₹{summary.subtotalTaxable.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span>CGST (9%):</span>
                <span>₹{summary.cgstTotal.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span>SGST (9%):</span>
                <span>₹{summary.sgstTotal.toFixed(2)}</span>
              </div>
              {summary.roundOff !== 0 && (
                <div className="flex justify-between">
                  <span>Round-off:</span>
                  <span>{summary.roundOff.toFixed(2)}</span>
                </div>
              )}
              <div className="border-b-2 border-black my-1"></div>
              <div className="flex justify-between font-bold text-sm">
                <span>NET TOTAL:</span>
                <span>₹{summary.grandTotal.toFixed(2)}</span>
              </div>
              <div className="border-b-2 border-black my-1"></div>

              {/* Dynamic UPI QR Code */}
              <div className="flex flex-col items-center justify-center py-2 space-y-1">
                <span className="text-[10px] font-bold">SCAN TO PAY VIA ANY UPI APP</span>
                <QRCodeSVG value={upiIntentUri} size={96} />
                <span className="text-[9px] text-gray-700">salemtraders@icici</span>
              </div>

              <div className="border-b border-dashed border-black my-1"></div>
              <div className="text-center font-bold text-[11px]">Thank You! Visit Again</div>
              <div className="text-center text-[10px]">நன்றி மீண்டும் வருக</div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  window.print();
                  startNewBill();
                  setShowReceiptModal(false);
                }}
                className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white py-2.5 rounded-xl font-bold text-xs shadow-md transition"
              >
                <Printer className="w-4 h-4" />
                <span>Print & Finish Bill</span>
              </button>

              {selectedParty?.phone && (
                <a
                  href={`https://wa.me/91${selectedParty.phone.replace(/\D/g, '')}?text=Vanakkam%20${encodeURIComponent(selectedParty.name)},%20Invoice%20${invoiceNumber}%20for%20Rs.${summary.grandTotal}%20from%20Salem%20Sri%20Murugan%20Hardware.%20Pay%20via%20UPI:%20${encodeURIComponent(upiIntentUri)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-center gap-1.5 bg-emerald-800 hover:bg-emerald-700 text-white px-4 py-2.5 rounded-xl font-bold text-xs transition"
                  title="Share on WhatsApp"
                >
                  <Share2 className="w-4 h-4" />
                  <span>WhatsApp</span>
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Supervisor Owner PIN Modal */}
      {showPinModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-red-500/50 rounded-2xl max-w-sm w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center gap-2.5 text-red-400">
              <ShieldAlert className="w-6 h-6" />
              <h3 className="font-bold text-white text-base">Credit Limit Exceeded</h3>
            </div>

            <p className="text-xs text-slate-300">
              Customer <strong className="text-white">{selectedParty?.name}</strong> has exceeded their credit limit of ₹{selectedParty?.credit_limit.toLocaleString()}. Enter Owner PIN to authorize credit sale:
            </p>

            <form onSubmit={handlePinSubmit} className="space-y-3">
              <div className="relative">
                <input
                  type="password"
                  maxLength={4}
                  autoFocus
                  placeholder="Enter 4-digit PIN..."
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-center text-lg font-mono tracking-widest text-white focus:border-red-500"
                  value={ownerPin}
                  onChange={(e) => setOwnerPin(e.target.value)}
                />
              </div>

              {pinError && (
                <div className="text-xs text-red-400 text-center font-bold">
                  Invalid PIN. Default demo PIN is 1234 or 0000.
                </div>
              )}

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowPinModal(false)}
                  className="px-3 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-bold transition shadow"
                >
                  Authorize Sale
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Split Payment Modal (F8) */}
      {showSplitModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Split className="w-5 h-5 text-emerald-400" />
                <h3 className="font-bold text-white text-base">Split Payment Breakdown</h3>
              </div>
              <button onClick={() => setShowSplitModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="text-xs text-slate-300">
              Total Bill: <CurrencyCell amount={summary.grandTotal} highlight="emerald" size="lg" />
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Cash Payment (₹):</label>
                <input
                  type="number"
                  step="any"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-sm"
                  value={cashPart}
                  onChange={(e) => setCashPart(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">UPI Digital Payment (₹):</label>
                <input
                  type="number"
                  step="any"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-sm"
                  value={upiPart}
                  onChange={(e) => setUpiPart(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Credit / Udhar (₹):</label>
                <input
                  type="number"
                  step="any"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-sm"
                  value={creditPart}
                  onChange={(e) => setCreditPart(e.target.value)}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowSplitModal(false)}
                className="px-3 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setPaymentMode('SPLIT');
                  setShowSplitModal(false);
                  setShowReceiptModal(true);
                }}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow"
              >
                Confirm Split & Proceed
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Held Bills Tray Modal (F7) */}
      {showHoldModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <PauseCircle className="w-5 h-5 text-amber-400" />
                <h3 className="font-bold text-white text-base">Held Bills Tray ({heldBills.length})</h3>
              </div>
              <button onClick={() => setShowHoldModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto">
              {heldBills.length === 0 ? (
                <div className="text-center p-8 text-slate-400 text-xs">No held bills found in memory.</div>
              ) : (
                heldBills.map(h => (
                  <div key={h.id} className="flex items-center justify-between p-3 rounded-xl bg-slate-800 border border-slate-700 hover:border-emerald-500 transition">
                    <div>
                      <div className="font-bold text-white text-xs">{h.partyName}</div>
                      <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                        Held at {h.heldAt} • {h.lines.length} items
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <CurrencyCell amount={h.grandTotal} highlight="emerald" size="base" />
                      <button
                        onClick={() => recallBill(h)}
                        className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition"
                      >
                        Recall
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
