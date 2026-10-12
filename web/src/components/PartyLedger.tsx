import React, { useState, useEffect } from 'react';
import {
  Users,
  ShieldCheck,
  MessageCircle,
  Plus,
  X,
  UserPlus,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ArrowUpRight,
  ArrowDownLeft,
  FileText,
  PhoneCall,
  Send,
  Building2,
  RefreshCw,
  Search,
  Pencil,
} from 'lucide-react';
import type {
  Party,
  Language,
  PartyCreateInput,
  PartyUpdateInput,
  PartyAgeingSummary,
  InvoiceDueItem,
  SupplierBalancesSummary,
  CollectionReminderItem,
  ReceiptVoucherRecord,
  SupplierPaymentRecord,
} from '../types';
import { CurrencyCell } from './ui/CurrencyCell';
import { api } from '../api/client';

interface PartyLedgerProps {
  parties: Party[];
  language: Language;
  onAddParty?: (data: PartyCreateInput) => Promise<Party>;
  onUpdateParty?: (partyId: string, data: PartyUpdateInput) => Promise<Party>;
  initialTab?: string;
  initialPartyId?: string;
}

export const PartyLedger: React.FC<PartyLedgerProps> = ({ parties: initialParties, language, onAddParty, onUpdateParty, initialTab: _initialTab, initialPartyId: _initialPartyId }) => {
  const [partiesList, setPartiesList] = useState<Party[]>(initialParties);
  const [activeTab, setActiveTab] = useState<'CUSTOMERS' | 'SUPPLIERS' | 'CALL_LIST'>('CUSTOMERS');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals & Drawers state
  const [selectedPartyForPayment, setSelectedPartyForPayment] = useState<Party | null>(null);
  const [selectedPartyForDues, setSelectedPartyForDues] = useState<Party | null>(null);
  const [duesSummary, setDuesSummary] = useState<PartyAgeingSummary | null>(null);
  const [loadingDues, setLoadingDues] = useState(false);

  // Supplier tab state
  const [supplierSummary, setSupplierSummary] = useState<SupplierBalancesSummary | null>(null);
  const [loadingSuppliers, setLoadingSuppliers] = useState(false);
  const [selectedSupplierForPayment, setSelectedSupplierForPayment] = useState<Party | null>(null);

  // Call list state
  const [callList, setCallList] = useState<CollectionReminderItem[]>([]);
  const [loadingCallList, setLoadingCallList] = useState(false);
  const [dispatchedIds, setDispatchedIds] = useState<Record<string, boolean>>({});

  // Payment receipt form state
  const [receiptAmount, setReceiptAmount] = useState('');
  const [receiptMode, setReceiptMode] = useState<'CASH' | 'UPI' | 'NEFT_RTGS' | 'CHEQUE'>('UPI');
  const [receiptRef, setReceiptRef] = useState('');
  const [receiptNotes, setReceiptNotes] = useState('');
  const [allocationMethod, setAllocationMethod] = useState<'OLDEST_FIRST' | 'MANUAL'>('OLDEST_FIRST');
  const [manualAllocations, setManualAllocations] = useState<Record<string, string>>({});
  const [partyOpenInvoices, setPartyOpenInvoices] = useState<InvoiceDueItem[]>([]);
  const [submittingReceipt, setSubmittingReceipt] = useState(false);
  const [receiptSuccessData, setReceiptSuccessData] = useState<ReceiptVoucherRecord | null>(null);

  // Supplier payment form state
  const [supplierPayAmount, setSupplierPayAmount] = useState('');
  const [supplierPayMode, setSupplierPayMode] = useState<'CASH' | 'UPI' | 'NEFT_RTGS' | 'CHEQUE'>('NEFT_RTGS');
  const [supplierPayRef, setSupplierPayRef] = useState('');
  const [supplierPayNotes, setSupplierPayNotes] = useState('');
  const [submittingSupplierPay, setSubmittingSupplierPay] = useState(false);
  const [supplierPaySuccess, setSupplierPaySuccess] = useState<SupplierPaymentRecord | null>(null);

  // Add party modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [isSubmittingParty, setIsSubmittingParty] = useState(false);
  const [addSuccessMsg, setAddSuccessMsg] = useState<string | null>(null);
  const [formData, setFormData] = useState<{
    name: string;
    phone: string;
    gstin: string;
    partyType: 'CUSTOMER' | 'SUPPLIER' | 'BOTH';
    priceListCode: 'RETAIL' | 'CONTRACTOR' | 'WHOLESALE';
    creditLimit: string;
    creditDays: string;
    openingBalance: string;
    billingAddress: string;
  }>({
    name: '',
    phone: '',
    gstin: '',
    partyType: 'CUSTOMER',
    priceListCode: 'CONTRACTOR',
    creditLimit: '25000',
    creditDays: '30',
    openingBalance: '0',
    billingAddress: '',
  });

  // Edit party modal state
  const [editingParty, setEditingParty] = useState<Party | null>(null);
  const [isSubmittingEdit, setIsSubmittingEdit] = useState(false);
  const [editSuccessMsg, setEditSuccessMsg] = useState<string | null>(null);
  const [editFormData, setEditFormData] = useState<{
    name: string;
    phone: string;
    email: string;
    gstin: string;
    partyType: 'CUSTOMER' | 'SUPPLIER' | 'BOTH';
    priceListCode: 'RETAIL' | 'CONTRACTOR' | 'WHOLESALE';
    creditLimit: string;
    creditDays: string;
    billingAddress: string;
  }>({
    name: '',
    phone: '',
    email: '',
    gstin: '',
    partyType: 'CUSTOMER',
    priceListCode: 'CONTRACTOR',
    creditLimit: '25000',
    creditDays: '30',
    billingAddress: '',
  });

  const handleOpenEditParty = (party: Party) => {
    setEditingParty(party);
    setEditSuccessMsg(null);
    setEditFormData({
      name: party.name,
      phone: party.phone || '',
      email: party.email || '',
      gstin: party.gstin || '',
      partyType: party.party_type,
      priceListCode: (party.price_list_code as any) || 'CONTRACTOR',
      creditLimit: String(party.credit_limit ?? 0),
      creditDays: String(party.credit_days ?? 30),
      billingAddress: party.billing_address || '',
    });
  };

  const handleSaveEditParty = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingParty || !editFormData.name.trim()) return;

    setIsSubmittingEdit(true);
    try {
      const updatePayload: PartyUpdateInput = {
        name: editFormData.name.trim(),
        party_type: editFormData.partyType,
        phone: editFormData.phone.trim() || undefined,
        email: editFormData.email.trim() || undefined,
        gstin: editFormData.gstin.trim() || undefined,
        billing_address: editFormData.billingAddress.trim() || undefined,
        price_list_code: editFormData.priceListCode,
        credit_limit: parseFloat(editFormData.creditLimit) || 0,
        credit_days: parseInt(editFormData.creditDays, 10) || 0,
      };

      let updatedParty: Party;
      if (onUpdateParty) {
        updatedParty = await onUpdateParty(editingParty.id, updatePayload);
      } else {
        updatedParty = await api.updateParty(editingParty.id, updatePayload);
      }

      setPartiesList(prev => prev.map(p => (p.id === updatedParty.id ? updatedParty : p)));
      setEditSuccessMsg(language === 'ta' ? 'விவரங்கள் வெற்றிகரமாக மாற்றப்பட்டன!' : 'Party details updated successfully!');
      setTimeout(() => {
        setEditingParty(null);
        setEditSuccessMsg(null);
      }, 700);
    } catch (err: any) {
      alert(err.message || 'Failed to update party details');
    } finally {
      setIsSubmittingEdit(false);
    }
  };

  useEffect(() => {
    setPartiesList(initialParties);
  }, [initialParties]);

  // Keyboard-first: Escape closes any open ledger dialog (same as the POS screen)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      setSelectedPartyForDues(null);
      setSelectedPartyForPayment(null);
      setSelectedSupplierForPayment(null);
      setShowAddModal(false);
      setEditingParty(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Load supplier summary when switching to suppliers tab
  const fetchSupplierSummary = async () => {
    setLoadingSuppliers(true);
    try {
      const data = await api.getSupplierBalancesSummary();
      setSupplierSummary(data);
    } finally {
      setLoadingSuppliers(false);
    }
  };

  // Load call list when switching to call list tab
  const fetchCallList = async () => {
    setLoadingCallList(true);
    try {
      const data = await api.getCollectionCallList(0, 0);
      setCallList(data);
    } finally {
      setLoadingCallList(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'SUPPLIERS') {
      fetchSupplierSummary();
    } else if (activeTab === 'CALL_LIST') {
      fetchCallList();
    }
  }, [activeTab]);

  // Open Invoice Dues modal
  const handleOpenDues = async (party: Party) => {
    setSelectedPartyForDues(party);
    setLoadingDues(true);
    setDuesSummary(null);
    try {
      const summary = await api.getPartyAgeing(party.id);
      setDuesSummary(summary);
    } finally {
      setLoadingDues(false);
    }
  };

  // Open Payment receipt modal
  const handleOpenReceivePayment = async (party: Party) => {
    setSelectedPartyForPayment(party);
    setReceiptAmount(party.current_balance > 0 ? String(party.current_balance) : '');
    setReceiptMode('UPI');
    setReceiptRef('');
    setReceiptNotes('');
    setAllocationMethod('OLDEST_FIRST');
    setManualAllocations({});
    setReceiptSuccessData(null);

    // Fetch open invoices for manual allocation option
    try {
      const dues = await api.getPartyOpenDues(party.id);
      setPartyOpenInvoices(dues);
    } catch {
      setPartyOpenInvoices([]);
    }
  };

  // Submit Receipt Voucher
  const handlePostReceipt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPartyForPayment || !receiptAmount) return;

    const totalAmt = parseFloat(receiptAmount);
    if (isNaN(totalAmt) || totalAmt <= 0) return;

    setSubmittingReceipt(true);
    try {
      let manualPayload = undefined;
      if (allocationMethod === 'MANUAL') {
        manualPayload = Object.entries(manualAllocations)
          .filter(([_, val]) => parseFloat(val) > 0)
          .map(([invId, val]) => ({
            invoice_entry_id: invId,
            amount: parseFloat(val),
          }));
      }

      const res = await api.recordReceiptVoucher({
        party_id: selectedPartyForPayment.id,
        payment_mode: receiptMode,
        reference_number: receiptRef.trim() || undefined,
        total_amount: totalAmt,
        allocation_method: allocationMethod,
        manual_allocations: manualPayload,
        notes: receiptNotes.trim() || undefined,
      });

      setReceiptSuccessData(res);
      // Update local party list
      setPartiesList(prev =>
        prev.map(p => (p.id === res.party_id ? { ...p, current_balance: Number(res.party_current_balance ?? 0) } : p))
      );
    } catch (err: any) {
      alert(err.message || 'Failed to record receipt voucher');
    } finally {
      setSubmittingReceipt(false);
    }
  };

  // Submit Supplier Payment
  const handlePostSupplierPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSupplierForPayment || !supplierPayAmount) return;

    const amt = parseFloat(supplierPayAmount);
    if (isNaN(amt) || amt <= 0) return;

    setSubmittingSupplierPay(true);
    try {
      const res = await api.recordSupplierPayment({
        supplier_id: selectedSupplierForPayment.id,
        payment_mode: supplierPayMode,
        reference_number: supplierPayRef.trim() || undefined,
        amount: amt,
        notes: supplierPayNotes.trim() || undefined,
      });

      setSupplierPaySuccess(res);
      // Update local party list & supplier summary
      setPartiesList(prev =>
        prev.map(p => (p.id === res.supplier_id ? { ...p, current_balance: Number(res.supplier_current_balance ?? 0) } : p))
      );
      fetchSupplierSummary();
    } catch (err: any) {
      alert(err.message || 'Failed to record supplier payment');
    } finally {
      setSubmittingSupplierPay(false);
    }
  };

  // Dispatch WhatsApp Reminder
  const handleDispatchReminder = async (item: CollectionReminderItem) => {
    try {
      await api.dispatchWhatsAppReminder(item.party_id);
      setDispatchedIds(prev => ({ ...prev, [item.party_id]: true }));
    } catch (err: any) {
      alert(err.message || 'Failed to dispatch WhatsApp reminder');
    }
  };

  // Filter parties by search
  const filteredCustomers = partiesList.filter(
    p => (p.party_type === 'CUSTOMER' || p.party_type === 'BOTH') &&
         (p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (p.phone && p.phone.includes(searchQuery)))
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 hardware-card p-4 shadow-md">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Users className="w-5 h-5 text-emerald-400" />
            <span>{language === 'ta' ? 'வாடிக்கையாளர் & சப்ளையர் கணக்கு ஏடு' : 'Customer & Supplier Ledger'}</span>
          </h2>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1">
            <span className="flex items-center gap-1 text-emerald-400 font-bold bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/80">
              <ShieldCheck className="w-3.5 h-3.5" /> Paisa Integrity Guaranteed
            </span>
            <span>•</span>
            <span className="font-mono text-slate-300">
              ∑ Unpaid Invoices - Unallocated Advances == Current Balance (₹0.00 exact)
            </span>
          </div>
        </div>

        {/* Tab switch & Add Party Button */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex bg-slate-900 p-1 rounded-xl border border-slate-700 text-xs">
            <button
              onClick={() => setActiveTab('CUSTOMERS')}
              className={`px-3 py-1.5 rounded-lg font-bold transition flex items-center gap-1.5 ${
                activeTab === 'CUSTOMERS' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Users className="w-3.5 h-3.5" />
              <span>{language === 'ta' ? 'வாடிக்கையாளர்கள் (Receivables)' : 'Customers (Receivables)'}</span>
            </button>
            <button
              onClick={() => setActiveTab('SUPPLIERS')}
              className={`px-3 py-1.5 rounded-lg font-bold transition flex items-center gap-1.5 ${
                activeTab === 'SUPPLIERS' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Building2 className="w-3.5 h-3.5" />
              <span>{language === 'ta' ? 'சப்ளையர்கள் (Payables)' : 'Suppliers (Payables)'}</span>
            </button>
            <button
              onClick={() => setActiveTab('CALL_LIST')}
              className={`px-3 py-1.5 rounded-lg font-bold transition flex items-center gap-1.5 ${
                activeTab === 'CALL_LIST' ? 'bg-amber-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <PhoneCall className="w-3.5 h-3.5 text-amber-300" />
              <span>{language === 'ta' ? 'வசூல் நினைவூட்டல் (Reminders)' : 'Call List (Reminders)'}</span>
            </button>
          </div>

          <button
            onClick={() => {
              setFormData({
                name: '',
                phone: '',
                gstin: '',
                partyType: activeTab === 'SUPPLIERS' ? 'SUPPLIER' : 'CUSTOMER',
                priceListCode: 'CONTRACTOR',
                creditLimit: activeTab === 'SUPPLIERS' ? '100000' : '25000',
                creditDays: '30',
                openingBalance: '0',
                billingAddress: '',
              });
              setAddSuccessMsg(null);
              setShowAddModal(true);
            }}
            className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center gap-1.5 transition shadow-md"
          >
            <Plus className="w-4 h-4" />
            <span>
              {activeTab === 'SUPPLIERS'
                ? (language === 'ta' ? '+ சப்ளையர் சேர்' : '+ Add Supplier')
                : (language === 'ta' ? '+ வாடிக்கையாளர் சேர்' : '+ Add Customer')}
            </span>
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: CUSTOMERS (RECEIVABLES) */}
      {/* ========================================================================= */}
      {activeTab === 'CUSTOMERS' && (
        <div className="space-y-3">
          {/* Search bar */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs">
            <Search className="w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder={language === 'ta' ? 'வாடிக்கையாளர் பெயர் அல்லது தொலைபேசி மூலம் தேடவும்...' : 'Search customers by name or phone...'}
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="bg-transparent border-none outline-none text-white w-full placeholder-slate-500 font-sans"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="text-slate-400 hover:text-white">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="hardware-card overflow-hidden shadow-md">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/90 text-slate-300 uppercase font-mono tracking-wider border-b border-slate-700 text-[11px]">
                  <tr>
                    <th className="p-3">Customer / Phone</th>
                    <th className="p-3">GSTIN</th>
                    <th className="p-3 text-right">Credit Limit</th>
                    <th className="p-3 text-center">Credit Status</th>
                    <th className="p-3 text-right font-bold text-white">Current Balance (Dr)</th>
                    <th className="p-3 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60 font-sans">
                  {filteredCustomers.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-400">
                        <UserPlus className="w-8 h-8 mx-auto mb-2 text-slate-500" />
                        <div>{language === 'ta' ? 'வாடிக்கையாளர்கள் இல்லை' : 'No customers found matching search.'}</div>
                      </td>
                    </tr>
                  ) : (
                    filteredCustomers.map(p => {
                      const isBreached = p.credit_limit > 0 && p.current_balance > p.credit_limit;
                      return (
                        <tr key={p.id} className="hover:bg-slate-700/30 transition">
                          <td className="p-3">
                            <div className="font-bold text-white text-sm">{p.name}</div>
                            <div className="text-slate-400 text-xs font-mono flex items-center gap-2">
                              <span>{p.phone || 'No phone'}</span>
                              {p.price_list_code && (
                                <span className="bg-slate-800 text-slate-300 px-1.5 py-0.2 rounded text-[10px]">
                                  {p.price_list_code}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="p-3 font-mono text-slate-300">{p.gstin || 'Unregistered'}</td>
                          <td className="p-3 text-right">
                            <CurrencyCell amount={p.credit_limit} decimals={0} />
                            <div className="text-[10px] text-slate-400 font-mono">{p.credit_days} days term</div>
                          </td>
                          <td className="p-3 text-center">
                            {isBreached ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-red-950/80 border border-red-700 text-red-300 animate-pulse">
                                <AlertTriangle className="w-3 h-3 text-red-400" />
                                Limit Breached (+₹{(p.current_balance - p.credit_limit).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})
                              </span>
                            ) : p.credit_limit > 0 ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950/60 border border-emerald-800 text-emerald-400">
                                <CheckCircle2 className="w-3 h-3" /> Within Limit
                              </span>
                            ) : (
                              <span className="text-slate-500 text-[11px]">No Limit</span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <span className="flex items-center justify-end gap-1">
                              <CurrencyCell
                                amount={p.current_balance}
                                highlight={p.current_balance > 0 ? (isBreached ? 'red' : 'amber') : 'default'}
                                size="base"
                              />
                              <span className="text-xs text-slate-400 font-mono font-semibold">
                                {p.current_balance >= 0 ? 'Dr' : 'Cr'}
                              </span>
                            </span>
                          </td>
                          <td className="p-3 text-center">
                            <div className="flex items-center justify-center gap-2">
                              {/* Edit Customer Button */}
                              <button
                                onClick={() => handleOpenEditParty(p)}
                                className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition shadow-sm flex items-center gap-1"
                                title={language === 'ta' ? 'வாடிக்கையாளர் விவரங்களை மாற்று' : 'Edit Customer Details'}
                              >
                                <Pencil className="w-3.5 h-3.5" />
                                <span>{language === 'ta' ? 'மாற்று' : 'Edit'}</span>
                              </button>

                              {/* Receive Payment Button */}
                              <button
                                onClick={() => handleOpenReceivePayment(p)}
                                className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition shadow-sm flex items-center gap-1"
                                title="Record Payment Receipt & Settle FIFO"
                              >
                                <ArrowDownLeft className="w-3.5 h-3.5" />
                                <span>Receive ₹</span>
                              </button>

                              {/* View Dues & Ageing Button */}
                              <button
                                onClick={() => handleOpenDues(p)}
                                className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 font-semibold text-xs transition flex items-center gap-1"
                                title="View Invoice-Wise Dues & Ageing Buckets"
                              >
                                <FileText className="w-3.5 h-3.5 text-blue-400" />
                                <span>Dues</span>
                              </button>

                              {/* WhatsApp Reminder Button */}
                              {p.phone && p.current_balance > 0 && (
                                <a
                                  href={`https://wa.me/91${p.phone.replace(/\D/g, '')}?text=வணக்கம்%20${encodeURIComponent(p.name)},%20தங்களின்%20நிலுவைத்%20தொகை%20₹${p.current_balance}.%20Kindly%20pay%20via%20UPI:%20upi://pay?pa=store@icici%26pn=HardwareStore%26am=${p.current_balance}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="p-1.5 rounded-lg bg-emerald-950 text-emerald-400 hover:bg-emerald-900 border border-emerald-800 transition"
                                  title="Send WhatsApp Collection Reminder"
                                >
                                  <MessageCircle className="w-3.5 h-3.5" />
                                </a>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: SUPPLIERS (PAYABLES & BALANCES) */}
      {/* ========================================================================= */}
      {activeTab === 'SUPPLIERS' && (
        <div className="space-y-3">
          {/* Supplier Payables Overview Banner */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="hardware-card p-3 flex items-center justify-between border-l-4 border-l-blue-500">
              <div>
                <div className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">Active Suppliers</div>
                <div className="text-xl font-bold font-mono text-white mt-0.5">
                  {supplierSummary?.total_suppliers || 0}
                </div>
              </div>
              <Building2 className="w-7 h-7 text-blue-400/50" />
            </div>

            <div className="hardware-card p-3 flex items-center justify-between border-l-4 border-l-amber-500">
              <div>
                <div className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">Total Net Payables</div>
                <div className="text-xl font-bold font-mono text-amber-300 mt-0.5">
                  ₹{(supplierSummary?.total_payable_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <ArrowUpRight className="w-7 h-7 text-amber-400/50" />
            </div>

            <div className="hardware-card p-3 flex items-center justify-between border-l-4 border-l-emerald-500">
              <div>
                <div className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">Credit Ledger Engine</div>
                <div className="text-xs font-semibold text-emerald-400 mt-0.5">
                  Purchases (Cr) - Payments (Dr)
                </div>
              </div>
              <ShieldCheck className="w-7 h-7 text-emerald-400/50" />
            </div>
          </div>

          <div className="hardware-card overflow-hidden shadow-md">
            <div className="p-3 border-b border-slate-700 flex items-center justify-between">
              <span className="font-bold text-white text-xs">
                {language === 'ta' ? 'சப்ளையர் கணக்கு இருப்பு விவரங்கள்' : 'Supplier Accounts & Net Payables'}
              </span>
              <button
                onClick={fetchSupplierSummary}
                disabled={loadingSuppliers}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1 transition"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingSuppliers ? 'animate-spin' : ''}`} />
                <span>Refresh</span>
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/90 text-slate-300 uppercase font-mono tracking-wider border-b border-slate-700 text-[11px]">
                  <tr>
                    <th className="p-3">Supplier Name & Phone</th>
                    <th className="p-3">GSTIN</th>
                    <th className="p-3 text-right">Total Purchases (Cr)</th>
                    <th className="p-3 text-right">Total Paid (Dr)</th>
                    <th className="p-3 text-right font-bold text-white">Net Payable (Owed)</th>
                    <th className="p-3 text-center">Last Transaction</th>
                    <th className="p-3 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60 font-sans">
                  {loadingSuppliers ? (
                    <tr>
                      <td colSpan={7} className="p-8 text-center text-slate-400">Loading supplier balances...</td>
                    </tr>
                  ) : !supplierSummary || supplierSummary.suppliers.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-8 text-center text-slate-400">
                        No suppliers registered. Click "+ Add Supplier" to record inward vendors.
                      </td>
                    </tr>
                  ) : (
                    supplierSummary.suppliers.map(s => {
                      const partyObj = partiesList.find(p => p.id === s.supplier_id);
                      return (
                        <tr key={s.supplier_id} className="hover:bg-slate-700/30 transition">
                          <td className="p-3">
                            <div className="font-bold text-white text-sm">{s.name}</div>
                            <div className="text-slate-400 text-xs font-mono">{s.phone || 'No phone'}</div>
                          </td>
                          <td className="p-3 font-mono text-slate-300">{s.gstin || 'Unregistered'}</td>
                          <td className="p-3 text-right">
                            <CurrencyCell amount={s.total_purchases} decimals={2} />
                          </td>
                          <td className="p-3 text-right">
                            <CurrencyCell amount={s.total_paid} decimals={2} highlight="emerald" />
                          </td>
                          <td className="p-3 text-right">
                            <span className="flex items-center justify-end gap-1">
                              <CurrencyCell
                                amount={s.net_payable}
                                highlight={s.net_payable > 0 ? 'red' : 'default'}
                                size="base"
                              />
                              <span className="text-xs text-slate-400 font-mono font-semibold">
                                {s.current_balance < 0 ? 'Cr (Owe)' : 'Dr (Adv)'}
                              </span>
                            </span>
                          </td>
                          <td className="p-3 text-center font-mono text-slate-400">
                            {s.last_transaction_date || '—'}
                          </td>
                          <td className="p-3 text-center">
                            <div className="flex items-center justify-center gap-2">
                              {partyObj && (
                                <button
                                  onClick={() => handleOpenEditParty(partyObj)}
                                  className="px-2.5 py-1 rounded-lg bg-blue-600/90 hover:bg-blue-500 text-white font-semibold text-xs transition shadow-sm flex items-center gap-1"
                                  title={language === 'ta' ? 'சப்ளையர் விவரங்களை மாற்று' : 'Edit Supplier Details'}
                                >
                                  <Pencil className="w-3.5 h-3.5" />
                                  <span>{language === 'ta' ? 'மாற்று' : 'Edit'}</span>
                                </button>
                              )}
                              <button
                                onClick={() => {
                                  setSelectedSupplierForPayment(
                                    partyObj || {
                                      id: s.supplier_id,
                                      name: s.name,
                                      party_type: 'SUPPLIER',
                                      current_balance: s.current_balance,
                                      credit_limit: 0,
                                      credit_days: 0,
                                      state_code: '33',
                                    }
                                  );
                                  setSupplierPayAmount(s.net_payable > 0 ? String(s.net_payable) : '');
                                  setSupplierPayMode('NEFT_RTGS');
                                  setSupplierPayRef('');
                                  setSupplierPayNotes('');
                                  setSupplierPaySuccess(null);
                                }}
                                className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition shadow-sm flex items-center gap-1"
                              >
                                <ArrowUpRight className="w-3.5 h-3.5" />
                                <span>Pay Supplier ₹</span>
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: COLLECTION REMINDERS CALL LIST */}
      {/* ========================================================================= */}
      {activeTab === 'CALL_LIST' && (
        <div className="space-y-3">
          <div className="hardware-card p-4 flex flex-col sm:flex-row items-center justify-between gap-3 bg-gradient-to-r from-slate-900 to-amber-950/40 border-amber-800/40">
            <div>
              <h3 className="font-bold text-white text-base flex items-center gap-2">
                <PhoneCall className="w-5 h-5 text-amber-400" />
                <span>{language === 'ta' ? 'உரிமையாளரின் காலை வசூல் பட்டியல்' : "Owner's Morning Collection Call List"}</span>
              </h3>
              <p className="text-xs text-slate-300 mt-0.5">
                Prioritized by Urgency Score = <span className="font-mono text-amber-300 font-bold">Overdue Amount × √(Days Overdue)</span> with dynamic UPI payment links.
              </p>
            </div>
            <button
              onClick={fetchCallList}
              disabled={loadingCallList}
              className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs flex items-center gap-1 transition shadow"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingCallList ? 'animate-spin' : ''}`} />
              <span>Refresh Call List</span>
            </button>
          </div>

          {loadingCallList ? (
            <div className="hardware-card p-8 text-center text-slate-400">Analyzing overdue invoices...</div>
          ) : callList.length === 0 ? (
            <div className="hardware-card p-8 text-center text-slate-400">
              <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-400" />
              <div className="font-bold text-white text-sm">All customer accounts are clear or within terms!</div>
              <div className="text-xs text-slate-400 mt-1">No overdue debtors requiring collection calls right now.</div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {callList.map((item, idx) => {
                const isSent = dispatchedIds[item.party_id];
                return (
                  <div
                    key={item.party_id}
                    className="hardware-card p-4 space-y-3 border-l-4 border-l-amber-500 hover:border-slate-500 transition shadow-md"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40">
                            #{idx + 1} Priority
                          </span>
                          <span className="font-bold text-white text-sm">{item.customer_name}</span>
                        </div>
                        <div className="text-xs font-mono text-slate-400 mt-0.5">
                          {item.phone || 'No phone recorded'}
                        </div>
                      </div>

                      <div className="text-right">
                        <div className="text-[11px] text-slate-400">Urgency Score</div>
                        <div className="font-mono font-bold text-amber-400 text-sm">
                          {item.urgency_score.toLocaleString()}
                        </div>
                      </div>
                    </div>

                    {/* Due specifics */}
                    <div className="grid grid-cols-3 gap-2 bg-slate-950/70 p-2.5 rounded-lg border border-slate-800 text-xs font-mono">
                      <div>
                        <div className="text-[10px] text-slate-400 uppercase">Total Balance</div>
                        <div className="font-bold text-white">₹{item.current_balance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-400 uppercase">Oldest Bill</div>
                        <div className="font-bold text-slate-300">{item.oldest_bill_number || '—'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-400 uppercase">Days Overdue</div>
                        <div className="font-bold text-red-400 flex items-center gap-1">
                          <Clock className="w-3 h-3" /> {item.days_overdue} days
                        </div>
                      </div>
                    </div>

                    {/* WhatsApp Message preview */}
                    <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800 text-[11px] text-slate-300 font-sans space-y-1">
                      <div className="text-[10px] uppercase font-bold text-emerald-400 flex items-center gap-1">
                        <MessageCircle className="w-3 h-3" /> Tamil & English WhatsApp Template:
                      </div>
                      <p className="whitespace-pre-line text-slate-300 font-sans text-xs line-clamp-3">
                        {item.whatsapp_message}
                      </p>
                    </div>

                    {/* Dispatch actions */}
                    <div className="flex items-center justify-between pt-1">
                      {item.phone ? (
                        <a
                          href={`https://wa.me/91${item.phone.replace(/\D/g, '')}?text=${encodeURIComponent(item.whatsapp_message)}`}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center gap-1.5 transition shadow"
                        >
                          <Send className="w-3.5 h-3.5" />
                          <span>Open WhatsApp Web</span>
                        </a>
                      ) : (
                        <span className="text-xs text-slate-500">Phone required for WhatsApp</span>
                      )}

                      <button
                        onClick={() => handleDispatchReminder(item)}
                        disabled={isSent}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                          isSent
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-600'
                        }`}
                      >
                        {isSent ? (
                          <>
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                            <span>Dispatched & Logged</span>
                          </>
                        ) : (
                          <>
                            <MessageCircle className="w-3.5 h-3.5 text-slate-400" />
                            <span>Log Dispatch</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* DRAWER / MODAL: INVOICE-WISE DUES & AGEING SUMMARY */}
      {/* ========================================================================= */}
      {selectedPartyForDues && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-3xl w-full p-5 space-y-4 shadow-2xl my-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="font-bold text-white text-base flex items-center gap-2">
                  <FileText className="w-5 h-5 text-blue-400" />
                  <span>Invoice-Wise Dues & 4 Ageing Buckets</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Party: <span className="text-white font-bold">{selectedPartyForDues.name}</span> ({selectedPartyForDues.phone || 'No phone'})
                </p>
              </div>
              <button
                onClick={() => setSelectedPartyForDues(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {loadingDues ? (
              <div className="p-8 text-center text-slate-400">Loading invoice ledger entries...</div>
            ) : duesSummary ? (
              <div className="space-y-4">
                {/* Ageing 4 Buckets Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                  <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                    <div className="text-[10px] text-slate-400 uppercase font-mono">0–30 Days</div>
                    <div className="text-sm font-bold font-mono text-emerald-400 mt-1">
                      ₹{duesSummary.bucket_0_30.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                    <div className="text-[10px] text-slate-400 uppercase font-mono">31–60 Days</div>
                    <div className="text-sm font-bold font-mono text-amber-400 mt-1">
                      ₹{duesSummary.bucket_31_60.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                    <div className="text-[10px] text-slate-400 uppercase font-mono">61–90 Days</div>
                    <div className="text-sm font-bold font-mono text-orange-400 mt-1">
                      ₹{duesSummary.bucket_61_90.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                    <div className="text-[10px] text-slate-400 uppercase font-mono">90+ Days</div>
                    <div className="text-sm font-bold font-mono text-red-400 mt-1">
                      ₹{duesSummary.bucket_90_plus.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>

                {/* Paisa Integrity Formula Banner */}
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 flex items-center justify-between text-xs font-mono">
                  <div>
                    <span className="text-slate-400">Total Overdue:</span>{' '}
                    <span className="text-red-400 font-bold">₹{duesSummary.total_overdue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Unallocated Advances:</span>{' '}
                    <span className="text-emerald-400 font-bold">₹{duesSummary.unallocated_advance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Current Balance:</span>{' '}
                    <span className="text-white font-bold">₹{duesSummary.current_balance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                </div>

                {/* Open Invoices Table */}
                <div className="overflow-x-auto max-h-60 overflow-y-auto border border-slate-800 rounded-xl">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] sticky top-0 border-b border-slate-800">
                      <tr>
                        <th className="p-2.5">Invoice #</th>
                        <th className="p-2.5">Date</th>
                        <th className="p-2.5 text-right">Total (₹)</th>
                        <th className="p-2.5 text-right">Allocated (₹)</th>
                        <th className="p-2.5 text-right font-bold text-white">Due (₹)</th>
                        <th className="p-2.5 text-center">Age (Days)</th>
                        <th className="p-2.5 text-center">Bucket</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80 font-sans">
                      {duesSummary.open_invoices.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="p-4 text-center text-slate-400">
                            No open or partially paid invoices found for this party.
                          </td>
                        </tr>
                      ) : (
                        duesSummary.open_invoices.map(inv => (
                          <tr key={inv.entry_id} className="hover:bg-slate-800/30">
                            <td className="p-2.5 font-mono font-bold text-white">{inv.doc_number}</td>
                            <td className="p-2.5 font-mono text-slate-400">{inv.doc_date}</td>
                            <td className="p-2.5 text-right font-mono">₹{inv.total_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                            <td className="p-2.5 text-right font-mono text-emerald-400">₹{inv.allocated_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                            <td className="p-2.5 text-right font-mono font-bold text-amber-300">₹{inv.due_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                            <td className="p-2.5 text-center font-mono">
                              <span className={inv.is_overdue ? 'text-red-400 font-bold' : 'text-slate-300'}>
                                {inv.age_days}d
                              </span>
                            </td>
                            <td className="p-2.5 text-center">
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-300">
                                {inv.bucket}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={() => {
                      setSelectedPartyForDues(null);
                      handleOpenReceivePayment(selectedPartyForDues);
                    }}
                    className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center gap-1.5 transition shadow"
                  >
                    <ArrowDownLeft className="w-4 h-4" />
                    <span>Receive Payment for this Party</span>
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: RECEIVE CUSTOMER PAYMENT RECEIPT VOUCHER */}
      {/* ========================================================================= */}
      {selectedPartyForPayment && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-5 space-y-4 shadow-2xl my-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <ArrowDownLeft className="w-5 h-5 text-emerald-400" />
                <h3 className="font-bold text-white text-base">Record Payment Receipt</h3>
              </div>
              <button
                onClick={() => setSelectedPartyForPayment(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="hardware-card p-3 text-xs space-y-1.5 bg-slate-950/80">
              <div className="font-bold text-white text-sm">{selectedPartyForPayment.name}</div>
              <div className="text-slate-400 flex items-center justify-between">
                <span>Current Outstanding Dues:</span>
                <span className="font-mono font-bold text-amber-300 text-sm">
                  ₹{selectedPartyForPayment.current_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            {receiptSuccessData ? (
              <div className="space-y-3 p-4 rounded-xl bg-emerald-950/80 border border-emerald-800 text-xs">
                <div className="flex items-center gap-2 text-emerald-300 font-bold text-sm">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Voucher #{receiptSuccessData.voucher_number} Posted Successfully!</span>
                </div>
                <div className="space-y-1 text-slate-300 font-mono text-[11px]">
                  <div>Total Received: ₹{receiptSuccessData.total_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                  <div>Allocated to Invoices: ₹{receiptSuccessData.allocated_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                  <div>Unallocated Advance: ₹{receiptSuccessData.unallocated_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                  <div className="font-bold text-white border-t border-emerald-800 pt-1 mt-1">
                    New Current Balance: ₹{receiptSuccessData.party_current_balance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>

                {receiptSuccessData.allocations.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <div className="text-[10px] font-bold text-emerald-400 uppercase">Allocations:</div>
                    {receiptSuccessData.allocations.map(a => (
                      <div key={a.allocation_id} className="text-[11px] text-slate-300 font-mono flex justify-between">
                        <span>{a.invoice_number}</span>
                        <span>₹{a.allocated_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => setSelectedPartyForPayment(null)}
                  className="w-full mt-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg transition"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handlePostReceipt} className="space-y-3.5">
                {/* Amount & Mode */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-slate-300 font-semibold block mb-1">Receipt Amount (₹) *</label>
                    <input
                      type="number"
                      step="any"
                      required
                      placeholder="Enter amount..."
                      value={receiptAmount}
                      onChange={e => setReceiptAmount(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-300 font-semibold block mb-1">Payment Mode</label>
                    <select
                      value={receiptMode}
                      onChange={e => setReceiptMode(e.target.value as any)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-emerald-500 font-mono"
                    >
                      <option value="UPI">UPI (GPay / PhonePe / QR)</option>
                      <option value="CASH">CASH (Counter Cash)</option>
                      <option value="NEFT_RTGS">NEFT / RTGS (Bank Transfer)</option>
                      <option value="CHEQUE">CHEQUE</option>
                    </select>
                  </div>
                </div>

                {/* Reference Number */}
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">UTR / Ref Number</label>
                  <input
                    type="text"
                    placeholder="e.g. UPI Ref / Bank UTR / Cheque #"
                    value={receiptRef}
                    onChange={e => setReceiptRef(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-emerald-500"
                  />
                </div>

                {/* Allocation Method Selection */}
                <div className="space-y-1.5 border border-slate-800 p-2.5 rounded-xl bg-slate-950">
                  <label className="text-xs text-slate-300 font-semibold block">Allocation Strategy:</label>
                  <div className="flex items-center gap-4 text-xs">
                    <label className="flex items-center gap-1.5 cursor-pointer text-emerald-400 font-semibold">
                      <input
                        type="radio"
                        name="allocMethod"
                        checked={allocationMethod === 'OLDEST_FIRST'}
                        onChange={() => setAllocationMethod('OLDEST_FIRST')}
                      />
                      <span>OLDEST_FIRST (Auto FIFO)</span>
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                      <input
                        type="radio"
                        name="allocMethod"
                        checked={allocationMethod === 'MANUAL'}
                        onChange={() => setAllocationMethod('MANUAL')}
                      />
                      <span>MANUAL (Pick Bills)</span>
                    </label>
                  </div>

                  {allocationMethod === 'MANUAL' && (
                    <div className="mt-2 space-y-1.5 max-h-36 overflow-y-auto border-t border-slate-800 pt-2">
                      {partyOpenInvoices.length === 0 ? (
                        <div className="text-[11px] text-slate-500">No open bills available for manual allocation. Entire amount will be stored as Advance.</div>
                      ) : (
                        partyOpenInvoices.map(inv => (
                          <div key={inv.entry_id} className="flex items-center justify-between text-[11px] text-slate-300 font-mono">
                            <div>
                              <span>{inv.doc_number}</span>{' '}
                              <span className="text-slate-500">({inv.doc_date}, Due: ₹{inv.due_amount})</span>
                            </div>
                            <input
                              type="number"
                              step="any"
                              placeholder="0.00"
                              value={manualAllocations[inv.entry_id] || ''}
                              onChange={e => setManualAllocations(prev => ({ ...prev, [inv.entry_id]: e.target.value }))}
                              className="w-24 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-right text-white"
                            />
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {/* Notes */}
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Remarks / Notes</label>
                  <input
                    type="text"
                    placeholder="Optional voucher notes..."
                    value={receiptNotes}
                    onChange={e => setReceiptNotes(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-emerald-500"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setSelectedPartyForPayment(null)}
                    className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingReceipt}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold transition shadow-md flex items-center gap-1.5"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>{submittingReceipt ? 'Posting...' : 'Post Receipt Voucher'}</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: RECORD SUPPLIER PAYMENT VOUCHER */}
      {/* ========================================================================= */}
      {selectedSupplierForPayment && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl my-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <ArrowUpRight className="w-5 h-5 text-blue-400" />
                <h3 className="font-bold text-white text-base">Make Supplier Payment</h3>
              </div>
              <button
                onClick={() => setSelectedSupplierForPayment(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="hardware-card p-3 text-xs space-y-1.5 bg-slate-950/80">
              <div className="font-bold text-white text-sm">{selectedSupplierForPayment.name}</div>
              <div className="text-slate-400 flex items-center justify-between">
                <span>Net Payable Balance:</span>
                <span className="font-mono font-bold text-red-400 text-sm">
                  ₹{Math.max(0, -selectedSupplierForPayment.current_balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            {supplierPaySuccess ? (
              <div className="space-y-3 p-4 rounded-xl bg-blue-950/80 border border-blue-800 text-xs">
                <div className="flex items-center gap-2 text-blue-300 font-bold text-sm">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Voucher #{supplierPaySuccess.voucher_number} Posted!</span>
                </div>
                <div className="space-y-1 text-slate-300 font-mono text-[11px]">
                  <div>Amount Paid: ₹{supplierPaySuccess.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                  <div>Mode: {supplierPaySuccess.payment_mode}</div>
                  <div className="font-bold text-white border-t border-blue-800 pt-1 mt-1">
                    New Net Balance: ₹{supplierPaySuccess.supplier_current_balance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedSupplierForPayment(null)}
                  className="w-full mt-3 py-2 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-lg transition"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handlePostSupplierPayment} className="space-y-3.5">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Payment Amount (₹) *</label>
                  <input
                    type="number"
                    step="any"
                    required
                    placeholder="Enter payment amount..."
                    value={supplierPayAmount}
                    onChange={e => setSupplierPayAmount(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Payment Mode</label>
                  <select
                    value={supplierPayMode}
                    onChange={e => setSupplierPayMode(e.target.value as any)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-blue-500 font-mono"
                  >
                    <option value="NEFT_RTGS">NEFT / RTGS (Bank Transfer)</option>
                    <option value="UPI">UPI</option>
                    <option value="CASH">CASH</option>
                    <option value="CHEQUE">CHEQUE</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Bank Reference / UTR Number</label>
                  <input
                    type="text"
                    placeholder="e.g. UTR123456789"
                    value={supplierPayRef}
                    onChange={e => setSupplierPayRef(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Remarks</label>
                  <input
                    type="text"
                    placeholder="e.g. Bulk steel settlement"
                    value={supplierPayNotes}
                    onChange={e => setSupplierPayNotes(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-blue-500"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setSelectedSupplierForPayment(null)}
                    className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingSupplierPay}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-bold transition shadow-md flex items-center gap-1.5"
                  >
                    <ArrowUpRight className="w-3.5 h-3.5" />
                    <span>{submittingSupplierPay ? 'Recording...' : 'Record Supplier Payment'}</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: ADD NEW PARTY (CUSTOMER OR SUPPLIER) */}
      {/* ========================================================================= */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-5 space-y-4 shadow-2xl my-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-emerald-400" />
                <h3 className="font-bold text-white text-base">
                  {formData.partyType === 'CUSTOMER'
                    ? (language === 'ta' ? 'புதிய வாடிக்கையாளர் பதிவு' : 'Add New Customer')
                    : (language === 'ta' ? 'புதிய சப்ளையர் பதிவு' : 'Add New Supplier')}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form
              onSubmit={async e => {
                e.preventDefault();
                if (!formData.name.trim()) return;
                setIsSubmittingParty(true);
                try {
                  if (onAddParty) {
                    const created = await onAddParty({
                      name: formData.name.trim(),
                      phone: formData.phone.trim() || undefined,
                      gstin: formData.gstin.trim() || undefined,
                      party_type: formData.partyType,
                      credit_limit: parseFloat(formData.creditLimit) || 0,
                      credit_days: parseInt(formData.creditDays) || 0,
                      opening_balance: parseFloat(formData.openingBalance) || 0,
                      price_list_code: formData.priceListCode,
                      billing_address: formData.billingAddress.trim() || undefined,
                      state_code: '33',
                    });
                    setPartiesList(prev => [...prev, created]);
                    // Supplier table & call list are server summaries: refresh them too
                    if (activeTab === 'SUPPLIERS') fetchSupplierSummary();
                    else if (activeTab === 'CALL_LIST') fetchCallList();
                  }
                  setAddSuccessMsg(
                    language === 'ta'
                      ? `${formData.name} வெற்றிகரமாக சேர்க்கப்பட்டார்!`
                      : `${formData.name} added successfully!`
                  );
                  setTimeout(() => {
                    setShowAddModal(false);
                    setAddSuccessMsg(null);
                  }, 1000);
                } catch (err: any) {
                  alert(`Party not saved: ${err?.message || 'server error'}`);
                } finally {
                  setIsSubmittingParty(false);
                }
              }}
              className="space-y-3.5"
            >
              {/* Name & Phone */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'பெயர் / நிறுவனம் *' : 'Party Name *'}
                  </label>
                  <input
                    type="text"
                    required
                    placeholder={formData.partyType === 'CUSTOMER' ? 'e.g. Murugan Builders' : 'e.g. Salem Steel Ltd'}
                    value={formData.name}
                    onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'கைபேசி எண் (WhatsApp)' : 'Phone Number'}
                  </label>
                  <input
                    type="tel"
                    placeholder="94433 22110"
                    value={formData.phone}
                    onChange={e => setFormData(prev => ({ ...prev, phone: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Party Type & Price Tier */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'வகை (Party Type)' : 'Party Type'}
                  </label>
                  <select
                    value={formData.partyType}
                    onChange={e => setFormData(prev => ({ ...prev, partyType: e.target.value as any }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-emerald-500"
                  >
                    <option value="CUSTOMER">Customer (வாடிக்கையாளர்)</option>
                    <option value="SUPPLIER">Supplier (சப்ளையர்)</option>
                    <option value="BOTH">Both (இருவரும்)</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'விலைப் பட்டியல் (Price Tier)' : 'Price List Tier'}
                  </label>
                  <select
                    value={formData.priceListCode}
                    onChange={e => setFormData(prev => ({ ...prev, priceListCode: e.target.value as any }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-emerald-500"
                  >
                    <option value="CONTRACTOR">Contractor / Mason (ஒப்பந்ததாரர்)</option>
                    <option value="RETAIL">Retail (சில்லறை)</option>
                    <option value="WHOLESALE">Wholesale (மொத்த விற்பனை)</option>
                  </select>
                </div>
              </div>

              {/* GSTIN & State */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">GSTIN (B2B Tax Invoice)</label>
                  <input
                    type="text"
                    maxLength={15}
                    placeholder="33AABCM9876Q1Z2"
                    value={formData.gstin}
                    onChange={e => setFormData(prev => ({ ...prev, gstin: e.target.value.toUpperCase() }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono uppercase text-white text-xs focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">State Code</label>
                  <input
                    type="text"
                    value="33 (Tamil Nadu)"
                    disabled
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-lg p-2 text-slate-400 text-xs font-mono"
                  />
                </div>
              </div>

              {/* Credit Limit & Days */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'கடன் வரம்பு (₹)' : 'Credit Limit (₹)'}
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="500"
                    value={formData.creditLimit}
                    onChange={e => setFormData(prev => ({ ...prev, creditLimit: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'கடன் நாட்கள்' : 'Credit Days'}
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={formData.creditDays}
                    onChange={e => setFormData(prev => ({ ...prev, creditDays: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'தொடக்க இருப்பு (₹)' : 'Opening Balance (₹)'}
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={formData.openingBalance}
                    onChange={e => setFormData(prev => ({ ...prev, openingBalance: e.target.value }))}
                    placeholder="0.00"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Address */}
              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">
                  {language === 'ta' ? 'முகவரி (Address)' : 'Billing Address'}
                </label>
                <textarea
                  rows={2}
                  placeholder="Street, Area, Town..."
                  value={formData.billingAddress}
                  onChange={e => setFormData(prev => ({ ...prev, billingAddress: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-emerald-500"
                />
              </div>

              {addSuccessMsg && (
                <div className="p-2.5 rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs font-semibold">
                  {addSuccessMsg}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingParty}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold transition shadow-md flex items-center gap-1.5"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>{isSubmittingParty ? 'Saving...' : (language === 'ta' ? 'கணக்கைச் சேமிக்கவும்' : 'Save Party')}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 5: EDIT PARTY (CUSTOMER / SUPPLIER) */}
      {/* ========================================================================= */}
      {editingParty && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-xl w-full p-5 space-y-4 shadow-2xl animate-in fade-in duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Pencil className="w-5 h-5 text-blue-400" />
                <div>
                  <h3 className="font-bold text-white text-base">
                    {editingParty.party_type === 'SUPPLIER'
                      ? (language === 'ta' ? 'சப்ளையர் விவரங்களை மாற்று' : 'Edit Supplier Details')
                      : (language === 'ta' ? 'வாடிக்கையாளர் விவரங்களை மாற்று' : 'Edit Customer Details')}
                  </h3>
                  <div className="text-[11px] text-slate-400 font-mono">
                    ID: {editingParty.id.slice(0, 8)} • Balance: ₹{Number(editingParty.current_balance ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </div>
                </div>
              </div>
              <button
                onClick={() => setEditingParty(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveEditParty} className="space-y-3.5">
              {/* Name & Phone */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'பெயர் / நிறுவனம் *' : 'Party / Firm Name *'}
                  </label>
                  <input
                    type="text"
                    required
                    value={editFormData.name}
                    onChange={e => setEditFormData(prev => ({ ...prev, name: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'கைபேசி எண் (WhatsApp)' : 'Phone Number'}
                  </label>
                  <input
                    type="tel"
                    placeholder="94433 22110"
                    value={editFormData.phone}
                    onChange={e => setEditFormData(prev => ({ ...prev, phone: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Party Type & Price Tier */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'வகை (Party Type)' : 'Party Type'}
                  </label>
                  <select
                    value={editFormData.partyType}
                    onChange={e => setEditFormData(prev => ({ ...prev, partyType: e.target.value as any }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-blue-500"
                  >
                    <option value="CUSTOMER">Customer (வாடிக்கையாளர்)</option>
                    <option value="SUPPLIER">Supplier (சப்ளையர்)</option>
                    <option value="BOTH">Both (இருவரும்)</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'விலைப் பட்டியல் (Price Tier)' : 'Price List Tier'}
                  </label>
                  <select
                    value={editFormData.priceListCode}
                    onChange={e => setEditFormData(prev => ({ ...prev, priceListCode: e.target.value as any }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-blue-500"
                  >
                    <option value="CONTRACTOR">Contractor / Mason (ஒப்பந்ததாரர்)</option>
                    <option value="RETAIL">Retail (சில்லறை)</option>
                    <option value="WHOLESALE">Wholesale (மொத்த விற்பனை)</option>
                  </select>
                </div>
              </div>

              {/* GSTIN & Email */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">GSTIN (B2B Tax Invoice)</label>
                  <input
                    type="text"
                    maxLength={15}
                    placeholder="33AABCM9876Q1Z2"
                    value={editFormData.gstin}
                    onChange={e => setEditFormData(prev => ({ ...prev, gstin: e.target.value.toUpperCase() }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono uppercase text-white text-xs focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">Email</label>
                  <input
                    type="email"
                    placeholder="builder@example.com"
                    value={editFormData.email}
                    onChange={e => setEditFormData(prev => ({ ...prev, email: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Credit Limit & Days */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'கடன் வரம்பு (₹)' : 'Credit Limit (₹)'}
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="500"
                    value={editFormData.creditLimit}
                    onChange={e => setEditFormData(prev => ({ ...prev, creditLimit: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 font-semibold block mb-1">
                    {language === 'ta' ? 'கடன் நாட்கள்' : 'Credit Days'}
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={editFormData.creditDays}
                    onChange={e => setEditFormData(prev => ({ ...prev, creditDays: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-white text-xs focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Address */}
              <div>
                <label className="text-xs text-slate-300 font-semibold block mb-1">
                  {language === 'ta' ? 'முகவரி (Address)' : 'Billing Address'}
                </label>
                <textarea
                  rows={2}
                  placeholder="Street, Area, Town..."
                  value={editFormData.billingAddress}
                  onChange={e => setEditFormData(prev => ({ ...prev, billingAddress: e.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-white text-xs focus:border-blue-500"
                />
              </div>

              {editSuccessMsg && (
                <div className="p-2.5 rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs font-semibold">
                  {editSuccessMsg}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditingParty(null)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingEdit}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-bold transition shadow-md flex items-center gap-1.5"
                >
                  <Pencil className="w-3.5 h-3.5" />
                  <span>{isSubmittingEdit ? 'Saving...' : (language === 'ta' ? 'மாற்றங்களைச் சேமிக்கவும்' : 'Save Changes')}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
