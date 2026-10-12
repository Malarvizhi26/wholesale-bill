import React, { useState, useEffect } from 'react';
import {
  FileText,
  TrendingUp,
  Percent,
  Clock,
  PackageCheck,
  CheckCircle2,
  Plus,
  X,
  RefreshCw,
  Printer,
  DollarSign,
  Coins,
} from 'lucide-react';
import type {
  Language,
  DailySalesSummary,
  GrossMarginReport,
  ExpenseSummary,
  ExpenseCreateInput,
  OutstandingCreditReport,
  StockValuationReport,
  CashDrawerReconcileRecord,
} from '../types';
import { api } from '../api/client';

export type ReportsTab = 'SALES' | 'MARGIN' | 'EXPENSES' | 'CREDIT' | 'STOCK' | 'CASH_RECON' | 'REVIEW';

export interface ReportsViewProps {
  language: Language;
  initialTab?: ReportsTab;
}

export const ReportsView: React.FC<ReportsViewProps> = ({ language, initialTab }) => {
  const [activeTab, setActiveTab] = useState<ReportsTab>(initialTab ?? 'SALES');
  // Local calendar date (toISOString() is UTC: before 05:30 IST it returns yesterday)
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

  // Date filters
  const [startDate, setStartDate] = useState(todayStr);
  const [endDate, setEndDate] = useState(todayStr);

  // Data states
  const [salesSummary, setSalesSummary] = useState<DailySalesSummary | null>(null);
  const [marginReport, setMarginReport] = useState<GrossMarginReport | null>(null);
  const [expenseSummary, setExpenseSummary] = useState<ExpenseSummary | null>(null);
  const [creditReport, setCreditReport] = useState<OutstandingCreditReport | null>(null);
  const [stockReport, setStockReport] = useState<StockValuationReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  // Record Expense modal state
  const [showExpenseModal, setShowExpenseModal] = useState(false);
  const [expenseForm, setExpenseForm] = useState<ExpenseCreateInput>({
    category: 'TEA_HAMALI',
    amount: 150,
    payment_mode: 'CASH',
    vendor_or_recipient: '',
    reference_number: '',
    notes: '',
  });
  const [submittingExpense, setSubmittingExpense] = useState(false);

  // Cash Reconciliation state
  const [openingCash, setOpeningCash] = useState('2000');
  const [denominations, setDenominations] = useState<Record<string, number>>({
    '500': 0,
    '200': 0,
    '100': 0,
    '50': 0,
    '20': 0,
    '10': 0,
    'coins': 0,
  });
  const [reconcileNotes, setReconcileNotes] = useState('');
  const [submittingReconcile, setSubmittingReconcile] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<CashDrawerReconcileRecord | null>(null);

  // Calculate actual cash counted from denominations
  const countedCash =
    (denominations['500'] || 0) * 500 +
    (denominations['200'] || 0) * 200 +
    (denominations['100'] || 0) * 100 +
    (denominations['50'] || 0) * 50 +
    (denominations['20'] || 0) * 20 +
    (denominations['10'] || 0) * 10 +
    (denominations['coins'] || 0);

  // Fetch report data on tab or date range change
  const loadReportData = async () => {
    setLoading(true);
    setReportError(null);
    try {
      if (activeTab === 'SALES') {
        const data = await api.getDailySalesSummary(startDate, endDate);
        setSalesSummary(data);
      } else if (activeTab === 'MARGIN') {
        const data = await api.getGrossMarginReport(startDate, endDate);
        setMarginReport(data);
      } else if (activeTab === 'EXPENSES') {
        const data = await api.getExpenseSummary(startDate, endDate);
        setExpenseSummary(data);
      } else if (activeTab === 'CREDIT') {
        const data = await api.getOutstandingCreditReport();
        setCreditReport(data);
      } else if (activeTab === 'STOCK') {
        const data = await api.getStockValuationReport();
        setStockReport(data);
      }
    } catch (err: any) {
      setReportError(err?.message || 'Failed to load report');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReportData();
  }, [activeTab, startDate, endDate]);

  // Handle Add Expense
  const handleRecordExpense = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!expenseForm.amount || !expenseForm.vendor_or_recipient.trim()) return;

    setSubmittingExpense(true);
    try {
      await api.recordExpense({
        ...expenseForm,
        amount: Number(expenseForm.amount),
        expense_date: startDate,
      });
      setShowExpenseModal(false);
      setExpenseForm({
        category: 'TEA_HAMALI',
        amount: 150,
        payment_mode: 'CASH',
        vendor_or_recipient: '',
        reference_number: '',
        notes: '',
      });
      loadReportData();
    } catch (err: any) {
      alert(err.message || 'Failed to record expense');
    } finally {
      setSubmittingExpense(false);
    }
  };

  // Handle Cash Drawer Reconciliation
  const handleReconcileCash = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittingReconcile(true);
    try {
      const res = await api.reconcileCashDrawer({
        counter_name: 'Counter 1',
        cashier_name: 'Murugan Cashier',
        session_date: startDate,
        opening_cash: parseFloat(openingCash) || 0,
        actual_cash_counted: countedCash,
        denominations,
        notes: reconcileNotes.trim() || undefined,
      });
      setReconcileResult(res);
    } catch (err: any) {
      alert(err.message || 'Failed to reconcile cash drawer');
    } finally {
      setSubmittingReconcile(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
      {reportError && (
        <div className="bg-red-950/70 border border-red-800 text-red-300 text-xs rounded-lg px-3 py-2">
          Report not loaded: {reportError}
        </div>
      )}
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 hardware-card p-4 shadow-md">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-emerald-400" />
            <span>{language === 'ta' ? 'வணிக & லாப அறிக்கைகள்' : 'Profit & Business Reports'}</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {language === 'ta'
              ? 'தினசரி விற்பனை, மொத்த லாபம், செலவுகள், கடன், சரக்கு மதிப்பு மற்றும் ரொக்க சரிபார்ப்பு'
              : 'Daily sales, gross margin (WAC), expenses, credit ageing, stock valuation, and cash drawer reconciliation'}
          </p>
        </div>

        {/* Global Print & Refresh */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => window.print()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            <Printer className="w-3.5 h-3.5" />
            <span>Print Report</span>
          </button>
          <button
            onClick={loadReportData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Tabs Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-900/90 p-1.5 rounded-2xl border border-slate-700 text-xs">
        <div className="flex flex-wrap items-center gap-1">
          <button
            onClick={() => setActiveTab('SALES')}
            className={`px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 ${
              activeTab === 'SALES' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Daily Sales</span>
          </button>
          <button
            onClick={() => setActiveTab('MARGIN')}
            className={`px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 ${
              activeTab === 'MARGIN' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Percent className="w-3.5 h-3.5" />
            <span>Gross Margin</span>
          </button>
          <button
            onClick={() => setActiveTab('EXPENSES')}
            className={`px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 ${
              activeTab === 'EXPENSES' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            <DollarSign className="w-3.5 h-3.5" />
            <span>Expenses</span>
          </button>
          <button
            onClick={() => setActiveTab('CREDIT')}
            className={`px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 ${
              activeTab === 'CREDIT' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Outstanding Credit</span>
          </button>
          <button
            onClick={() => setActiveTab('STOCK')}
            className={`px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 ${
              activeTab === 'STOCK' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            <PackageCheck className="w-3.5 h-3.5" />
            <span>Stock Valuation</span>
          </button>
          <button
            onClick={() => setActiveTab('CASH_RECON')}
            className={`px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 ${
              activeTab === 'CASH_RECON' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Coins className="w-3.5 h-3.5" />
            <span>Cash Reconciliation</span>
          </button>
        </div>

        {/* Date pickers for tabs that support range */}
        {(activeTab === 'SALES' || activeTab === 'MARGIN' || activeTab === 'EXPENSES' || activeTab === 'CASH_RECON') && (
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-slate-400">Date:</span>
            <input
              type="date"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
              className="bg-slate-950 border border-slate-700 text-slate-200 rounded-lg px-2 py-1 outline-none"
            />
            <span className="text-slate-500">to</span>
            <input
              type="date"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              className="bg-slate-950 border border-slate-700 text-slate-200 rounded-lg px-2 py-1 outline-none"
            />
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 1. DAILY SALES TAB */}
      {/* ========================================================================= */}
      {activeTab === 'SALES' && (
        <div className="space-y-4">
          {/* Key Sales Metrics Bento */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-emerald-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Total Invoices</div>
              <div className="text-2xl font-bold font-mono text-white">
                {salesSummary?.total_invoices ?? 0}
              </div>
              <div className="text-[11px] text-slate-400">Invoices billed in period</div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-blue-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Taxable Sales</div>
              <div className="text-2xl font-bold font-mono text-blue-300">
                ₹{(salesSummary?.taxable_amount ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[11px] text-slate-400">Revenue excluding GST</div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-purple-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Total Tax (GST)</div>
              <div className="text-2xl font-bold font-mono text-purple-300">
                ₹{(salesSummary?.total_tax ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[11px] text-slate-400">
                CGST: ₹{salesSummary?.cgst_amount?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? 0} • SGST: ₹{salesSummary?.sgst_amount?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? 0}
              </div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-amber-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Grand Total (Sales)</div>
              <div className="text-2xl font-bold font-mono text-amber-300">
                ₹{(salesSummary?.grand_total ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[11px] text-slate-400">
                Round-off: ₹{salesSummary?.round_off?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? 0}
              </div>
            </div>
          </div>

          {/* Sales Breakdown by Payment Mode */}
          <div className="hardware-card p-4 space-y-3 shadow-md">
            <h3 className="font-bold text-white text-sm border-b border-slate-700 pb-2">
              Payment Modes Distribution
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {['CASH', 'UPI', 'CREDIT', 'SPLIT'].map(mode => {
                const amt = salesSummary?.sales_by_mode?.[mode] ?? 0;
                return (
                  <div key={mode} className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                    <div className="text-[11px] text-slate-400 uppercase font-mono font-bold">{mode}</div>
                    <div className="text-lg font-bold font-mono text-white">
                      ₹{amt.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Hourly Sales Distribution */}
          {salesSummary?.hourly_breakdown && salesSummary.hourly_breakdown.length > 0 && (
            <div className="hardware-card p-4 space-y-3 shadow-md">
              <h3 className="font-bold text-white text-sm border-b border-slate-700 pb-2">
                Hourly Peak Sales Distribution
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-900 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-2">Time Slot</th>
                      <th className="p-2 text-center">Invoices</th>
                      <th className="p-2 text-right">Sales Amount (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {salesSummary.hourly_breakdown.map((h, i) => (
                      <tr key={i} className="hover:bg-slate-800/30 text-slate-200">
                        <td className="p-2 font-bold text-emerald-400">{h.hour}</td>
                        <td className="p-2 text-center">{h.invoice_count}</td>
                        <td className="p-2 text-right">₹{h.total_sales.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. GROSS MARGIN TAB */}
      {/* ========================================================================= */}
      {activeTab === 'MARGIN' && (
        <div className="space-y-4">
          {/* Margin Summary Bento */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-blue-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Taxable Revenue</div>
              <div className="text-2xl font-bold font-mono text-white">
                ₹{(marginReport?.total_taxable_sales ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-red-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Cost of Goods Sold (COGS)</div>
              <div className="text-2xl font-bold font-mono text-red-300">
                ₹{(marginReport?.total_cogs ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-slate-400">Exact WAC Cost at time of sale</div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-emerald-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Gross Profit (₹)</div>
              <div className="text-2xl font-bold font-mono text-emerald-400">
                ₹{(marginReport?.total_gross_profit ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-slate-400">Revenue - Landed WAC Cost</div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-amber-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Overall Margin %</div>
              <div className="text-2xl font-bold font-mono text-amber-300">
                {(marginReport?.overall_margin_percent ?? 0).toFixed(1)}%
              </div>
              <div className="text-[10px] text-slate-400">Shop-wide profit ratio</div>
            </div>
          </div>

          {/* Product-Wise Margin Ranking Table */}
          <div className="hardware-card overflow-hidden shadow-md">
            <div className="p-3 border-b border-slate-700 flex items-center justify-between">
              <h3 className="font-bold text-white text-sm">Product Profitability Breakdown</h3>
              <span className="text-xs text-slate-400 font-mono">Ranked by Gross Profit (₹)</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900 text-slate-300 uppercase font-mono text-[11px] border-b border-slate-700">
                  <tr>
                    <th className="p-3">Product Name & Code</th>
                    <th className="p-3 text-right">Sold Qty</th>
                    <th className="p-3 text-right">Taxable Sales (₹)</th>
                    <th className="p-3 text-right">COGS (₹)</th>
                    <th className="p-3 text-right font-bold text-emerald-400">Gross Profit (₹)</th>
                    <th className="p-3 text-center">Margin %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60 font-sans">
                  {!marginReport || marginReport.top_margin_products.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-400">
                        No sales recorded in selected period.
                      </td>
                    </tr>
                  ) : (
                    marginReport.top_margin_products.map(p => (
                      <tr key={p.product_id} className="hover:bg-slate-700/30 transition text-slate-200">
                        <td className="p-3">
                          <div className="font-bold text-white">{p.product_name}</div>
                          <div className="text-[11px] font-mono text-slate-400">{p.product_code}</div>
                        </td>
                        <td className="p-3 text-right font-mono">
                          {p.quantity_sold_base} {p.base_unit}
                        </td>
                        <td className="p-3 text-right font-mono">
                          ₹{p.taxable_sales.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td className="p-3 text-right font-mono text-slate-400">
                          ₹{p.cogs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td className="p-3 text-right font-mono font-bold text-emerald-400">
                          ₹{p.gross_profit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td className="p-3 text-center">
                          <span className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold ${
                            p.margin_percent >= 20 ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'
                          }`}>
                            {p.margin_percent.toFixed(1)}%
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. EXPENSES TAB */}
      {/* ========================================================================= */}
      {activeTab === 'EXPENSES' && (
        <div className="space-y-4">
          {/* Header & Add Button */}
          <div className="flex items-center justify-between">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 flex-1 mr-4">
              <div className="hardware-card p-3 border-l-4 border-l-purple-500">
                <div className="text-[11px] text-slate-400 uppercase font-bold">Total Expenses</div>
                <div className="text-xl font-bold font-mono text-purple-300">
                  ₹{(expenseSummary?.total_expenses ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="hardware-card p-3 border-l-4 border-l-blue-500">
                <div className="text-[11px] text-slate-400 uppercase font-bold">Cash Expenses</div>
                <div className="text-xl font-bold font-mono text-white">
                  ₹{(expenseSummary?.cash_expenses ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="hardware-card p-3 border-l-4 border-l-emerald-500">
                <div className="text-[11px] text-slate-400 uppercase font-bold">Bank / UPI Expenses</div>
                <div className="text-xl font-bold font-mono text-emerald-300">
                  ₹{(expenseSummary?.bank_upi_expenses ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            <button
              onClick={() => setShowExpenseModal(true)}
              className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs flex items-center gap-1.5 transition shadow"
            >
              <Plus className="w-4 h-4" />
              <span>+ Record Expense</span>
            </button>
          </div>

          {/* Expenses Table */}
          <div className="hardware-card overflow-hidden shadow-md">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900 text-slate-300 uppercase font-mono text-[11px] border-b border-slate-700">
                  <tr>
                    <th className="p-3">Voucher #</th>
                    <th className="p-3">Date</th>
                    <th className="p-3">Category</th>
                    <th className="p-3">Vendor / Recipient</th>
                    <th className="p-3 text-center">Mode</th>
                    <th className="p-3 text-right font-bold text-white">Amount (₹)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60 font-sans">
                  {!expenseSummary || expenseSummary.expenses.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-400">
                        No expenses recorded in selected period.
                      </td>
                    </tr>
                  ) : (
                    expenseSummary.expenses.map(e => (
                      <tr key={e.id} className="hover:bg-slate-700/30 text-slate-200">
                        <td className="p-3 font-mono font-bold text-purple-400">{e.voucher_number}</td>
                        <td className="p-3 font-mono text-slate-400">{e.expense_date}</td>
                        <td className="p-3 font-bold">{e.category}</td>
                        <td className="p-3">
                          <div>{e.vendor_or_recipient}</div>
                          {e.notes && <div className="text-[11px] text-slate-400">{e.notes}</div>}
                        </td>
                        <td className="p-3 text-center font-mono">
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">
                            {e.payment_mode}
                          </span>
                        </td>
                        <td className="p-3 text-right font-mono font-bold text-white">
                          ₹{e.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. OUTSTANDING CREDIT TAB */}
      {/* ========================================================================= */}
      {activeTab === 'CREDIT' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-amber-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Total Receivables</div>
              <div className="text-2xl font-bold font-mono text-amber-300">
                ₹{(creditReport?.total_receivables ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-red-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Total Overdue</div>
              <div className="text-2xl font-bold font-mono text-red-400">
                ₹{(creditReport?.total_overdue ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-slate-400">{creditReport?.breached_parties_count ?? 0} parties breached limit</div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-blue-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">0–30 Days (Current)</div>
              <div className="text-2xl font-bold font-mono text-white">
                ₹{(creditReport?.bucket_0_30 ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-orange-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">60+ Days Overdue</div>
              <div className="text-2xl font-bold font-mono text-orange-400">
                ₹{((creditReport?.bucket_61_90 ?? 0) + (creditReport?.bucket_90_plus ?? 0)).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
            </div>
          </div>

          {/* Top Debtors Table */}
          <div className="hardware-card overflow-hidden shadow-md">
            <div className="p-3 border-b border-slate-700 font-bold text-white text-sm">
              Top Customer Debtors & Overdue Ageing
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900 text-slate-300 uppercase font-mono text-[11px] border-b border-slate-700">
                  <tr>
                    <th className="p-3">Customer Name</th>
                    <th className="p-3">Phone</th>
                    <th className="p-3 text-right">Credit Limit</th>
                    <th className="p-3 text-center">Overdue Days</th>
                    <th className="p-3 text-right font-bold text-amber-300">Balance (₹)</th>
                    <th className="p-3 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60 font-sans">
                  {!creditReport || creditReport.top_debtors.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-400">
                        No outstanding customer credit balances.
                      </td>
                    </tr>
                  ) : (
                    creditReport.top_debtors.map(d => (
                      <tr key={d.party_id} className="hover:bg-slate-700/30 text-slate-200">
                        <td className="p-3 font-bold text-white">{d.party_name}</td>
                        <td className="p-3 font-mono text-slate-400">{d.phone || 'No phone'}</td>
                        <td className="p-3 text-right font-mono">₹{d.credit_limit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        <td className="p-3 text-center font-mono">
                          <span className={d.days_overdue > 0 ? 'text-red-400 font-bold' : 'text-slate-400'}>
                            {d.days_overdue}d
                          </span>
                        </td>
                        <td className="p-3 text-right font-mono font-bold text-amber-300">
                          ₹{d.current_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-3 text-center">
                          {d.phone && (
                            <a
                              href={`https://wa.me/91${d.phone.replace(/\D/g, '')}?text=வணக்கம்%20${encodeURIComponent(d.party_name)},%20தங்களின்%20நிலுவைத்%20தொகை%20₹${d.current_balance}.`}
                              target="_blank"
                              rel="noreferrer"
                              className="px-2 py-1 rounded bg-emerald-950 text-emerald-400 hover:bg-emerald-900 border border-emerald-800 text-[11px] font-bold inline-flex items-center gap-1"
                            >
                              <span>WhatsApp</span>
                            </a>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. STOCK VALUATION TAB */}
      {/* ========================================================================= */}
      {activeTab === 'STOCK' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-emerald-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Total Products</div>
              <div className="text-2xl font-bold font-mono text-white">
                {stockReport?.total_products ?? 0}
              </div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-blue-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Stock Valuation (WAC Cost)</div>
              <div className="text-2xl font-bold font-mono text-emerald-400">
                ₹{(stockReport?.total_valuation_cost ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-slate-400">Exact landed inventory worth</div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-purple-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Retail Value (Potential)</div>
              <div className="text-2xl font-bold font-mono text-purple-300">
                ₹{(stockReport?.total_retail_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </div>
            </div>

            <div className="hardware-card p-4 space-y-1 border-l-4 border-l-red-500">
              <div className="text-[11px] text-slate-400 uppercase font-bold">Low-Stock Warnings</div>
              <div className="text-2xl font-bold font-mono text-red-400">
                {stockReport?.low_stock_count ?? 0}
              </div>
              <div className="text-[10px] text-slate-400">Below reorder threshold</div>
            </div>
          </div>

          {/* Product Valuation Table */}
          <div className="hardware-card overflow-hidden shadow-md">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900 text-slate-300 uppercase font-mono text-[11px] border-b border-slate-700">
                  <tr>
                    <th className="p-3">Product Name & Code</th>
                    <th className="p-3 text-right">In-Stock Display</th>
                    <th className="p-3 text-right">WAC Unit Cost</th>
                    <th className="p-3 text-right font-bold text-emerald-400">Total Valuation (₹)</th>
                    <th className="p-3 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60 font-sans">
                  {!stockReport || stockReport.items.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-slate-400">
                        No product stock recorded.
                      </td>
                    </tr>
                  ) : (
                    stockReport.items.map(item => (
                      <tr key={item.product_id} className="hover:bg-slate-700/30 text-slate-200">
                        <td className="p-3">
                          <div className="font-bold text-white">{item.product_name}</div>
                          <div className="text-[11px] font-mono text-slate-400">{item.product_code}</div>
                        </td>
                        <td className="p-3 text-right font-mono font-bold text-slate-300">
                          {item.display_stock}
                        </td>
                        <td className="p-3 text-right font-mono text-slate-400">
                          ₹{item.wac_base.toFixed(2)} / {item.base_unit}
                        </td>
                        <td className="p-3 text-right font-mono font-bold text-emerald-400">
                          ₹{item.valuation_cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-3 text-center">
                          {item.is_low_stock ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-950 text-red-300 border border-red-800">
                              Low Stock
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">
                              Optimal
                            </span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 6. CASH RECONCILIATION TAB */}
      {/* ========================================================================= */}
      {activeTab === 'CASH_RECON' && (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
          {/* Left Form: Denominations Counter */}
          <div className="md:col-span-7 hardware-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-700 pb-2.5">
              <div className="flex items-center gap-2">
                <Coins className="w-5 h-5 text-amber-400" />
                <h3 className="font-bold text-white text-sm">Counter Shift Cash Drawer Count</h3>
              </div>
              <span className="text-xs font-mono text-slate-400">Counter 1</span>
            </div>

            <form onSubmit={handleReconcileCash} className="space-y-4">
              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">Opening Cash Balance (₹)</label>
                <input
                  type="number"
                  step="any"
                  value={openingCash}
                  onChange={e => setOpeningCash(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-emerald-500"
                />
              </div>

              {/* Denominations table */}
              <div className="border border-slate-800 rounded-xl overflow-hidden">
                <div className="bg-slate-900 p-2 text-xs font-bold text-slate-300 uppercase font-mono">
                  Denominations Counter
                </div>
                <div className="p-3 grid grid-cols-2 sm:grid-cols-3 gap-3 bg-slate-950/60 font-mono text-xs">
                  {['500', '200', '100', '50', '20', '10'].map(denom => (
                    <div key={denom} className="space-y-1">
                      <label className="text-[11px] text-slate-400 font-bold">₹{denom} × Count</label>
                      <input
                        type="number"
                        min="0"
                        value={denominations[denom] || ''}
                        onChange={e => setDenominations(prev => ({ ...prev, [denom]: parseInt(e.target.value) || 0 }))}
                        placeholder="0"
                        className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-right text-white"
                      />
                    </div>
                  ))}
                  <div className="space-y-1">
                    <label className="text-[11px] text-slate-400 font-bold">Coins (Total ₹)</label>
                    <input
                      type="number"
                      min="0"
                      value={denominations['coins'] || ''}
                      onChange={e => setDenominations(prev => ({ ...prev, coins: parseInt(e.target.value) || 0 }))}
                      placeholder="0"
                      className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-right text-white"
                    />
                  </div>
                </div>
              </div>

              {/* Counted Total */}
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 flex items-center justify-between font-mono">
                <span className="text-xs text-slate-400 uppercase font-bold">Total Actual Cash Counted:</span>
                <span className="text-xl font-bold text-emerald-400">₹{countedCash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>

              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">Shift Notes</label>
                <input
                  type="text"
                  placeholder="e.g. Evening shift closing"
                  value={reconcileNotes}
                  onChange={e => setReconcileNotes(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-emerald-500"
                />
              </div>

              <button
                type="submit"
                disabled={submittingReconcile}
                className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs transition shadow flex items-center justify-center gap-2"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>{submittingReconcile ? 'Reconciling...' : 'Reconcile & Close Cash Shift'}</span>
              </button>
            </form>
          </div>

          {/* Right Panel: Reconciliation Calculation Breakdown */}
          <div className="md:col-span-5 hardware-card p-4 space-y-4">
            <h3 className="font-bold text-white text-sm border-b border-slate-700 pb-2">
              Expected Cash Formula
            </h3>

            {reconcileResult ? (
              <div className="space-y-3 p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono">
                <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Session {reconcileResult.session_code} Reconciled</span>
                </div>
                <div className="space-y-1.5 text-slate-300 border-t border-slate-800 pt-2">
                  <div className="flex justify-between">
                    <span>Opening Cash:</span>
                    <span>₹{reconcileResult.opening_cash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between text-emerald-400">
                    <span>(+) Cash Sales:</span>
                    <span>₹{reconcileResult.cash_sales_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between text-emerald-400">
                    <span>(+) Cash Receipts:</span>
                    <span>₹{reconcileResult.cash_ledger_receipts.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between text-red-400">
                    <span>(-) Cash Expenses:</span>
                    <span>₹{reconcileResult.cash_expenses_paid.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between text-red-400">
                    <span>(-) Supplier Payouts:</span>
                    <span>₹{reconcileResult.cash_supplier_payouts.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between font-bold text-white border-t border-slate-700 pt-1">
                    <span>Expected Drawer Cash:</span>
                    <span>₹{reconcileResult.expected_cash_drawer.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between font-bold text-emerald-300">
                    <span>Actual Cash Counted:</span>
                    <span>₹{reconcileResult.actual_cash_counted.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className={`flex justify-between font-bold text-sm border-t border-slate-700 pt-1 ${
                    reconcileResult.discrepancy_amount === 0 ? 'text-emerald-400' : reconcileResult.discrepancy_amount < 0 ? 'text-red-400' : 'text-blue-400'
                  }`}>
                    <span>Discrepancy:</span>
                    <span>
                      {reconcileResult.discrepancy_amount === 0
                        ? '₹0.00 (Exact Match ✓)'
                        : `₹${reconcileResult.discrepancy_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${reconcileResult.discrepancy_amount < 0 ? 'Shortage' : 'Excess'})`}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2 text-xs text-slate-400 font-mono">
                <p>The system computes expected cash drawer mathematically:</p>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1 text-slate-300">
                  <div>(+) Opening Cash Balance</div>
                  <div>(+) Today Cash Sales</div>
                  <div>(+) Debtor Cash Receipts</div>
                  <div>(-) Cash Operating Expenses</div>
                  <div>(-) Supplier Cash Payments</div>
                  <div className="border-t border-slate-700 pt-1 font-bold text-emerald-400">
                    (=) Expected Counter Cash
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 pt-1">
                  Fill the counted denominations on the left and submit to record the closing shift voucher.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: RECORD EXPENSE */}
      {/* ========================================================================= */}
      {showExpenseModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white text-base">Record Operating Expense</h3>
              <button onClick={() => setShowExpenseModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleRecordExpense} className="space-y-3.5">
              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">Expense Category *</label>
                <select
                  value={expenseForm.category}
                  onChange={e => setExpenseForm(prev => ({ ...prev, category: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-purple-500 font-mono"
                >
                  <option value="TEA_HAMALI">Tea, Snacks & Hamali (தேநீர் & கூலி)</option>
                  <option value="ELECTRICITY">Electricity & Power (மின்சாரம்)</option>
                  <option value="SHOP_RENT">Shop Rent (கடை வாடகை)</option>
                  <option value="SALARY_WAGES">Staff Salary & Wages (சம்பளம்)</option>
                  <option value="FREIGHT_OUTWARD">Freight & Delivery (சரக்கு போக்குவரத்து)</option>
                  <option value="REPAIRS_MAINTENANCE">Repairs & Maintenance (பராமரிப்பு)</option>
                  <option value="OFFICE_STATIONERY">Stationery & Printing</option>
                  <option value="MISC">Miscellaneous (இதர செலவுகள்)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Amount (₹) *</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={expenseForm.amount}
                    onChange={e => setExpenseForm(prev => ({ ...prev, amount: parseFloat(e.target.value) || 0 }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Payment Mode</label>
                  <select
                    value={expenseForm.payment_mode}
                    onChange={e => setExpenseForm(prev => ({ ...prev, payment_mode: e.target.value as any }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-purple-500 font-mono"
                  >
                    <option value="CASH">CASH (Drawer)</option>
                    <option value="UPI">UPI (GPay / PhonePe)</option>
                    <option value="NEFT_RTGS">Bank Transfer</option>
                    <option value="CHEQUE">Cheque</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">Vendor / Payee Recipient *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Tea stall, TANGEDCO, Landlord"
                  value={expenseForm.vendor_or_recipient}
                  onChange={e => setExpenseForm(prev => ({ ...prev, vendor_or_recipient: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-purple-500"
                />
              </div>

              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">Notes / Remarks</label>
                <input
                  type="text"
                  placeholder="Optional details..."
                  value={expenseForm.notes || ''}
                  onChange={e => setExpenseForm(prev => ({ ...prev, notes: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-purple-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowExpenseModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingExpense}
                  className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold text-xs transition shadow flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{submittingExpense ? 'Recording...' : 'Post Expense'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
