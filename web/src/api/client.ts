import type { Product, Party, POSLineItem, BillSummary } from '../types';

const API_BASE_URL = 'http://localhost:8000/api/v1';
const DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001';

// Initial fallback hardware catalogue for immediate offline/pilot counter usage
const INITIAL_PRODUCTS: Product[] = [
  {
    id: 'p1',
    code: 'SCR001',
    name: 'SS Self-Tapping Screws 25mm',
    tamil_name: 'எஃகு திருகு 25மிமீ',
    hsn_code: '7318',
    base_unit: 'piece',
    is_variable_weight: false,
    min_stock_base: 500,
    purchase_price_base: 1.40,
    stock_base: 4700,
    display_stock: '47 Box (4700 piece)',
    units: [
      { unit_name: 'Box', conversion_factor: 100, can_buy: true, can_sell: true, is_default_sales_unit: true },
      { unit_name: 'piece', conversion_factor: 1, can_buy: true, can_sell: true, is_default_sales_unit: false }
    ]
  },
  {
    id: 'p2',
    code: 'TMT012',
    name: 'Tata Tiscon 12mm TMT Bar Fe500D',
    tamil_name: 'டாடா டிஸ்கான் 12மிமீ கம்பி',
    hsn_code: '7214',
    base_unit: 'kg',
    is_variable_weight: true,
    min_stock_base: 1000,
    purchase_price_base: 58.50,
    stock_base: 2025.8,
    display_stock: '190 Rod 2.3 kg (2025.8 kg)',
    units: [
      { unit_name: 'Rod', conversion_factor: 10.65, can_buy: true, can_sell: true, is_default_sales_unit: true },
      { unit_name: 'kg', conversion_factor: 1, can_buy: true, can_sell: true, is_default_sales_unit: false }
    ]
  },
  {
    id: 'p3',
    code: 'PNT001',
    name: 'Asian Paints Tractor Emulsion 1L',
    tamil_name: 'ஏசியன் பெயிண்ட் டிராக்டர் 1லி',
    hsn_code: '3208',
    base_unit: 'piece',
    is_variable_weight: false,
    min_stock_base: 24,
    purchase_price_base: 230.00,
    stock_base: 114,
    display_stock: '9 Case 6 piece (114 piece)',
    units: [
      { unit_name: 'Case', conversion_factor: 12, can_buy: true, can_sell: true, is_default_sales_unit: false },
      { unit_name: 'piece', conversion_factor: 1, can_buy: true, can_sell: true, is_default_sales_unit: true }
    ]
  },
  {
    id: 'p4',
    code: 'PIP001',
    name: 'Ashirvad CPVC Pipe 1" (3 metre)',
    tamil_name: 'ஆசிர்வாத் CPVC குழாய் 1"',
    hsn_code: '3917',
    base_unit: 'piece',
    is_variable_weight: false,
    min_stock_base: 50,
    purchase_price_base: 72.00,
    stock_base: 320,
    display_stock: '320 piece (320 piece)',
    units: [
      { unit_name: 'piece', conversion_factor: 1, can_buy: true, can_sell: true, is_default_sales_unit: true }
    ]
  },
  {
    id: 'p5',
    code: 'GIW020',
    name: 'GI Binding Wire 20 Gauge',
    tamil_name: 'ஜிஐ கட்டு கம்பி 20 கேஜ்',
    hsn_code: '7217',
    base_unit: 'kg',
    is_variable_weight: false,
    min_stock_base: 100,
    purchase_price_base: 65.00,
    stock_base: 450,
    display_stock: '18 Coil (450 kg)',
    units: [
      { unit_name: 'Coil', conversion_factor: 25, can_buy: true, can_sell: true, is_default_sales_unit: true },
      { unit_name: 'kg', conversion_factor: 1, can_buy: true, can_sell: true, is_default_sales_unit: false }
    ]
  }
];

const INITIAL_PARTIES: Party[] = [
  {
    id: 'party-1',
    name: 'Murugan Constructions (கட்டிடம்)',
    party_type: 'CUSTOMER',
    phone: '94433 22110',
    gstin: '33AABCM9876Q1Z2',
    state_code: '33',
    credit_limit: 50000.00,
    credit_days: 30,
    current_balance: 14250.00,
    price_list_code: 'CONTRACTOR',
  },
  {
    id: 'party-2',
    name: 'Raja Mason (மேஸ்திரி ராஜா)',
    party_type: 'CUSTOMER',
    phone: '98421 55678',
    state_code: '33',
    credit_limit: 15000.00,
    credit_days: 15,
    current_balance: 6200.00,
    price_list_code: 'CONTRACTOR',
  },
  {
    id: 'party-3',
    name: 'Salem Steel Suppliers',
    party_type: 'SUPPLIER',
    phone: '98765 12345',
    gstin: '33AABCS4455P1Z8',
    state_code: '33',
    credit_limit: 500000.00,
    credit_days: 45,
    current_balance: -85000.00,
  }
];

class ApiClient {
  private isOnline = false;

  async checkHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE_URL}/health`, { signal: AbortSignal.timeout(2000) });
      this.isOnline = res.ok;
      return res.ok;
    } catch {
      this.isOnline = false;
      return false;
    }
  }

  getOnlineStatus(): boolean {
    return this.isOnline;
  }

  async getProducts(search?: string): Promise<Product[]> {
    try {
      const url = new URL(`${API_BASE_URL}/inventory/products`);
      if (search) url.searchParams.set('search', search);

      const res = await fetch(url.toString(), {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          this.isOnline = true;
          return data;
        }
      }
    } catch {
      this.isOnline = false;
    }

    // Fallback search
    if (search) {
      const s = search.toLowerCase();
      return INITIAL_PRODUCTS.filter(
        p => p.name.toLowerCase().includes(s) ||
             p.code.toLowerCase().includes(s) ||
             (p.tamil_name && p.tamil_name.toLowerCase().includes(s))
      );
    }
    return INITIAL_PRODUCTS;
  }

  async getParties(): Promise<Party[]> {
    try {
      const res = await fetch(`${API_BASE_URL}/ledger/parties`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          this.isOnline = true;
          return data;
        }
      }
    } catch {
      this.isOnline = false;
    }
    return INITIAL_PARTIES;
  }

  calculateClientBill(
    lines: POSLineItem[],
    placeOfSupplyStateCode = '33',
    tenantStateCode = '33',
    paidAmount?: number
  ): BillSummary {
    const isInterState = placeOfSupplyStateCode !== tenantStateCode;
    let subtotalTaxable = 0;
    let totalDiscount = 0;
    let cgstTotal = 0;
    let sgstTotal = 0;
    let igstTotal = 0;

    for (const line of lines) {
      const gross = Math.round(line.quantity * line.unitPrice * 100) / 100;
      let disc = line.discountType === 'PERCENT'
        ? Math.round(gross * (line.discountValue / 100) * 100) / 100
        : line.discountValue;
      disc = Math.min(disc, gross);
      const taxable = Math.round((gross - disc) * 100) / 100;

      let cgst = 0;
      let sgst = 0;
      let igst = 0;

      if (isInterState) {
        igst = Math.round(taxable * (line.gstRatePercent / 100) * 100) / 100;
      } else {
        const halfRate = line.gstRatePercent / 2;
        cgst = Math.round(taxable * (halfRate / 100) * 100) / 100;
        sgst = Math.round(taxable * (halfRate / 100) * 100) / 100;
      }

      line.grossAmount = gross;
      line.discountAmount = disc;
      line.taxableAmount = taxable;
      line.cgstAmount = cgst;
      line.sgstAmount = sgst;
      line.igstAmount = igst;
      line.lineTotal = Math.round((taxable + cgst + sgst + igst) * 100) / 100;

      subtotalTaxable += taxable;
      totalDiscount += disc;
      cgstTotal += cgst;
      sgstTotal += sgst;
      igstTotal += igst;
    }

    subtotalTaxable = Math.round(subtotalTaxable * 100) / 100;
    totalDiscount = Math.round(totalDiscount * 100) / 100;
    cgstTotal = Math.round(cgstTotal * 100) / 100;
    sgstTotal = Math.round(sgstTotal * 100) / 100;
    igstTotal = Math.round(igstTotal * 100) / 100;

    const taxTotal = Math.round((cgstTotal + sgstTotal + igstTotal) * 100) / 100;
    const exactTotal = Math.round((subtotalTaxable + taxTotal) * 100) / 100;
    const grandTotal = Math.round(exactTotal);
    const roundOff = Math.round((grandTotal - exactTotal) * 100) / 100;
    const paid = paidAmount !== undefined ? paidAmount : grandTotal;
    const dueAmount = Math.max(0, grandTotal - paid);

    return {
      subtotalTaxable,
      totalDiscount,
      cgstTotal,
      sgstTotal,
      igstTotal,
      taxTotal,
      exactTotal,
      roundOff,
      grandTotal,
      paidAmount: paid,
      dueAmount,
      isInterState,
    };
  }
}

export const api = new ApiClient();
