import type { Product, ProductCreateInput, Party, PartyCreateInput, POSLineItem, BillSummary } from '../types';

const apiHost = typeof window !== 'undefined' && window.location.hostname ? window.location.hostname : 'localhost';
const API_BASE_URL = `http://${apiHost}:8001/api/v1`;
const FALLBACK_API_URL = `http://${apiHost}:8000/api/v1`;
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

  private currentBaseUrl = API_BASE_URL;

  async checkHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE_URL}/health`, { signal: AbortSignal.timeout(1500) });
      if (res.ok) {
        this.currentBaseUrl = API_BASE_URL;
        this.isOnline = true;
        return true;
      }
    } catch {
      // try fallback 8000
    }

    try {
      const res2 = await fetch(`${FALLBACK_API_URL}/health`, { signal: AbortSignal.timeout(1500) });
      if (res2.ok) {
        this.currentBaseUrl = FALLBACK_API_URL;
        this.isOnline = true;
        return true;
      }
    } catch {
      // both offline
    }

    this.isOnline = false;
    return false;
  }

  getOnlineStatus(): boolean {
    return this.isOnline;
  }

  async getProducts(search?: string): Promise<Product[]> {
    try {
      const url = new URL(`${this.currentBaseUrl}/inventory/products`);
      if (search) url.searchParams.set('search', search);

      const res = await fetch(url.toString(), {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          this.isOnline = true;
          return data.map((p: any) => ({
            ...p,
            min_stock_base: Number(p.min_stock_base ?? 0),
            reorder_quantity_base: Number(p.reorder_quantity_base ?? 0),
            purchase_price_base: Number(p.purchase_price_base ?? 0),
            stock_base: Number(p.stock_base ?? 0),
            units: (p.units || []).map((u: any) => ({
              ...u,
              conversion_factor: Number(u.conversion_factor ?? 1),
            })),
            prices: (p.prices || []).map((pr: any) => ({
              ...pr,
              price: Number(pr.price ?? 0),
              min_quantity: pr.min_quantity != null ? Number(pr.min_quantity) : null,
            })),
          }));
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

  async createProduct(product: ProductCreateInput): Promise<Product> {
    const payload = {
      code: product.code,
      name: product.name,
      tamil_name: product.tamil_name || null,
      category_id: product.category_id || null,
      brand_id: product.brand_id || null,
      hsn_code: product.hsn_code,
      base_unit: product.base_unit,
      is_variable_weight: product.is_variable_weight || false,
      min_stock_base: product.min_stock_base || 0,
      reorder_quantity_base: product.reorder_quantity_base || 0,
      purchase_price_base: product.purchase_price_base,
      units: product.units && product.units.length > 0 ? product.units : [
        {
          unit_name: product.base_unit,
          conversion_factor: 1,
          can_buy: true,
          can_sell: true,
          is_default_sales_unit: true,
          is_default_purchase_unit: true,
        }
      ],
      prices: [],
    };

    try {
      const res = await fetch(`${this.currentBaseUrl}/inventory/products`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-ID': DEFAULT_TENANT_ID,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to create product' }));
        throw new Error(err.detail || 'Failed to create product');
      }

      const created = await res.json();
      return created;
    } catch (e: any) {
      if (this.isOnline) throw e;
      // Offline fallback: save locally to INITIAL_PRODUCTS array
      const localProd: Product = {
        id: `p-${Date.now()}`,
        code: product.code,
        name: product.name,
        tamil_name: product.tamil_name,
        hsn_code: product.hsn_code,
        base_unit: product.base_unit,
        is_variable_weight: product.is_variable_weight || false,
        min_stock_base: product.min_stock_base || 0,
        reorder_quantity_base: product.reorder_quantity_base || 0,
        purchase_price_base: product.purchase_price_base,
        stock_base: 0,
        display_stock: `0 ${product.base_unit}`,
        units: product.units && product.units.length > 0
          ? product.units.map((u) => ({
              unit_name: u.unit_name,
              conversion_factor: u.conversion_factor,
              can_buy: u.can_buy ?? true,
              can_sell: u.can_sell ?? true,
              barcode: u.barcode,
              is_default_sales_unit: u.is_default_sales_unit ?? false,
              is_default_purchase_unit: u.is_default_purchase_unit ?? false,
            }))
          : [
              {
                unit_name: product.base_unit,
                conversion_factor: 1,
                can_buy: true,
                can_sell: true,
                is_default_sales_unit: true,
                is_default_purchase_unit: true,
              },
            ],
      };
      INITIAL_PRODUCTS.unshift(localProd);
      return localProd;
    }
  }

  async getParties(): Promise<Party[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/ledger/parties`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          this.isOnline = true;
          return data.map((p: any) => ({
            ...p,
            current_balance: Number(p.current_balance ?? 0),
            credit_limit: Number(p.credit_limit ?? 0),
            credit_days: Number(p.credit_days ?? 0),
            opening_balance: Number(p.opening_balance ?? 0),
          }));
        }
      }
    } catch {
      this.isOnline = false;
    }
    return INITIAL_PARTIES.map(p => ({
      ...p,
      current_balance: Number(p.current_balance ?? 0),
      credit_limit: Number(p.credit_limit ?? 0),
      credit_days: Number(p.credit_days ?? 0),
      opening_balance: p.opening_balance != null ? Number(p.opening_balance) : undefined,
    }));
  }

  async createParty(party: PartyCreateInput): Promise<Party> {
    const payload = {
      party_type: party.party_type || 'CUSTOMER',
      name: party.name,
      phone: party.phone || null,
      email: party.email || null,
      gstin: party.gstin || null,
      state_code: party.state_code || '33',
      billing_address: party.billing_address || null,
      price_list_code: party.price_list_code || 'RETAIL',
      credit_limit: party.credit_limit || 0,
      credit_days: party.credit_days || 0,
      opening_balance: party.opening_balance || 0,
    };

    try {
      const res = await fetch(`${this.currentBaseUrl}/ledger/parties`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-ID': DEFAULT_TENANT_ID,
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(3000),
      });

      if (res.ok) {
        const created = await res.json();
        this.isOnline = true;
        INITIAL_PARTIES.push(created);
        return created;
      }
    } catch {
      this.isOnline = false;
    }

    // Offline resilient fallback
    const offlineParty: Party = {
      id: `party-offline-${Date.now()}`,
      name: payload.name,
      party_type: payload.party_type as 'CUSTOMER' | 'SUPPLIER' | 'BOTH',
      phone: payload.phone || undefined,
      email: payload.email || undefined,
      gstin: payload.gstin || undefined,
      state_code: payload.state_code,
      billing_address: payload.billing_address || undefined,
      credit_limit: Number(payload.credit_limit),
      credit_days: Number(payload.credit_days),
      current_balance: Number(payload.opening_balance),
      price_list_code: payload.price_list_code as any,
    };
    INITIAL_PARTIES.push(offlineParty);
    return offlineParty;
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

  // -------------------------------------------------------------
  // Smart Inventory Module Methods
  // -------------------------------------------------------------

  async getGodowns(): Promise<import('../types').Godown[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/inventory/godowns`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return [
      { id: 'g-main', code: 'MAIN', name: 'Main Shop Godown', is_primary: true, is_active: true },
      { id: 'g-bypass', code: 'BYPASS', name: 'Salem Bypass Godown 2', is_primary: false, is_active: true }
    ];
  }

  async getGodownStock(godownId: string): Promise<import('../types').GodownStockItem[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/inventory/godowns/${godownId}/stock`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return [];
  }

  async transferGodownStock(payload: {
    source_godown_id: string;
    target_godown_id: string;
    product_id: string;
    unit_name: string;
    quantity: number;
    conversion_factor: number;
    notes?: string;
  }) {
    const res = await fetch(`${this.currentBaseUrl}/inventory/godowns/transfer`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Transfer failed' }));
      throw new Error(err.detail || 'Transfer failed');
    }
    return await res.json();
  }

  async getPurchases(): Promise<import('../types').PurchaseBill[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/inventory/purchases`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return [];
  }

  async createPurchase(payload: any): Promise<import('../types').PurchaseBill> {
    const res = await fetch(`${this.currentBaseUrl}/inventory/purchases`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to record purchase' }));
      throw new Error(err.detail || 'Failed to record purchase');
    }
    return await res.json();
  }

  async getAdjustments(): Promise<import('../types').StockAdjustment[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/inventory/adjustments`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return [];
  }

  async createAdjustment(payload: any): Promise<import('../types').StockAdjustment> {
    const res = await fetch(`${this.currentBaseUrl}/inventory/adjustments`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to record stock adjustment' }));
      throw new Error(err.detail || 'Failed to record stock adjustment');
    }
    return await res.json();
  }

  async getLowStockAlerts(godownId?: string): Promise<import('../types').LowStockAlert[]> {
    try {
      const url = new URL(`${this.currentBaseUrl}/inventory/alerts/low-stock`);
      if (godownId) url.searchParams.set('godown_id', godownId);
      const res = await fetch(url.toString(), {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return [];
  }

  async getProductPriceHistory(productId: string): Promise<import('../types').ProductPriceHistory> {
    const res = await fetch(`${this.currentBaseUrl}/inventory/products/${productId}/price-history`, {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) {
      throw new Error('Failed to fetch price history');
    }
    return await res.json();
  }

  async updateProductPrice(productId: string, payload: {
    price_list_id: string;
    unit_name: string;
    price: number;
    min_allowed_price?: number;
  }) {
    const res = await fetch(`${this.currentBaseUrl}/inventory/products/${productId}/prices`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update price' }));
      throw new Error(err.detail || 'Failed to update price');
    }
    return await res.json();
  }

  // -----------------------------------------------------------
  // Fast Billing APIs: Search, Invoices, Returns, Quotes, Challans
  // -----------------------------------------------------------

  async searchBillingProducts(query: string, godownId?: string, priceListId?: string): Promise<import('../types').ProductSearchItem[]> {
    try {
      const url = new URL(`${this.currentBaseUrl}/billing/search`);
      url.searchParams.set('q', query);
      if (godownId) url.searchParams.set('godown_id', godownId);
      if (priceListId) url.searchParams.set('price_list_id', priceListId);

      const res = await fetch(url.toString(), {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback handled by caller
    }
    return [];
  }

  async decomposeUnitQuantity(payload: {
    product_id: string;
    quantity: number;
    unit_name: string;
    actual_weight_kg?: number;
  }) {
    const res = await fetch(`${this.currentBaseUrl}/billing/unit-decompose`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to decompose unit quantity');
    return await res.json();
  }

  async createInvoice(payload: any): Promise<import('../types').SalesInvoiceRecord> {
    const res = await fetch(`${this.currentBaseUrl}/billing/invoices`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to post sales invoice' }));
      throw new Error(err.detail || 'Failed to post sales invoice');
    }
    return await res.json();
  }

  async listInvoices(limit = 50): Promise<import('../types').SalesInvoiceRecord[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/billing/invoices?limit=${limit}`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // ignore
    }
    return [];
  }

  async createSalesReturn(payload: any): Promise<import('../types').SalesReturnRecord> {
    const res = await fetch(`${this.currentBaseUrl}/billing/returns`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to record sales return' }));
      throw new Error(err.detail || 'Failed to record sales return');
    }
    return await res.json();
  }

  async listSalesReturns(limit = 50): Promise<import('../types').SalesReturnRecord[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/billing/returns?limit=${limit}`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // ignore
    }
    return [];
  }

  async createQuotation(payload: any): Promise<import('../types').QuotationRecord> {
    const res = await fetch(`${this.currentBaseUrl}/billing/quotations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to create quotation' }));
      throw new Error(err.detail || 'Failed to create quotation');
    }
    return await res.json();
  }

  async listQuotations(limit = 50): Promise<import('../types').QuotationRecord[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/billing/quotations?limit=${limit}`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // ignore
    }
    return [];
  }

  async convertQuotationToInvoice(quotationId: string, paymentMode = 'CASH', paidAmount?: number): Promise<import('../types').SalesInvoiceRecord> {
    const res = await fetch(`${this.currentBaseUrl}/billing/quotations/${quotationId}/convert-to-invoice`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify({ payment_mode: paymentMode, paid_amount: paidAmount }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to convert quotation' }));
      throw new Error(err.detail || 'Failed to convert quotation');
    }
    return await res.json();
  }

  async createDeliveryChallan(payload: any): Promise<import('../types').DeliveryChallanRecord> {
    const res = await fetch(`${this.currentBaseUrl}/billing/challans`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to create delivery challan' }));
      throw new Error(err.detail || 'Failed to create delivery challan');
    }
    return await res.json();
  }

  async listDeliveryChallans(limit = 50): Promise<import('../types').DeliveryChallanRecord[]> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/billing/challans?limit=${limit}`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // ignore
    }
    return [];
  }

  async convertChallanToInvoice(challanId: string, paymentMode = 'CREDIT', paidAmount?: number): Promise<import('../types').SalesInvoiceRecord> {
    const res = await fetch(`${this.currentBaseUrl}/billing/challans/${challanId}/convert-to-invoice`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify({ payment_mode: paymentMode, paid_amount: paidAmount }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to convert delivery challan' }));
      throw new Error(err.detail || 'Failed to convert delivery challan');
    }
    return await res.json();
  }

  // -----------------------------------------------------------
  // Customer & Supplier Ledger Methods
  // -----------------------------------------------------------

  async recordReceiptVoucher(payload: import('../types').ReceiptVoucherCreateInput): Promise<import('../types').ReceiptVoucherRecord> {
    const res = await fetch(`${this.currentBaseUrl}/ledger/receipts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to record receipt voucher' }));
      throw new Error(err.detail || 'Failed to record receipt voucher');
    }
    return await res.json();
  }

  async recordSupplierPayment(payload: import('../types').SupplierPaymentCreateInput): Promise<import('../types').SupplierPaymentRecord> {
    const res = await fetch(`${this.currentBaseUrl}/ledger/supplier-payments`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to record supplier payment' }));
      throw new Error(err.detail || 'Failed to record supplier payment');
    }
    return await res.json();
  }

  async getPartyOpenDues(partyId: string, asOf?: string): Promise<import('../types').InvoiceDueItem[]> {
    try {
      const url = new URL(`${this.currentBaseUrl}/ledger/parties/${partyId}/dues`);
      if (asOf) url.searchParams.set('as_of', asOf);
      const res = await fetch(url.toString(), {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return [];
  }

  async getPartyAgeing(partyId: string, asOf?: string): Promise<import('../types').PartyAgeingSummary | null> {
    try {
      const url = new URL(`${this.currentBaseUrl}/ledger/parties/${partyId}/ageing`);
      if (asOf) url.searchParams.set('as_of', asOf);
      const res = await fetch(url.toString(), {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return null;
  }

  async getSupplierBalancesSummary(): Promise<import('../types').SupplierBalancesSummary> {
    try {
      const res = await fetch(`${this.currentBaseUrl}/ledger/suppliers/summary`, {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return { total_suppliers: 0, total_payable_amount: 0, suppliers: [] };
  }

  async getCollectionCallList(minDays = 0, minAmount = 0): Promise<import('../types').CollectionReminderItem[]> {
    try {
      const url = new URL(`${this.currentBaseUrl}/ledger/reminders/call-list`);
      if (minDays > 0) url.searchParams.set('min_days_overdue', String(minDays));
      if (minAmount > 0) url.searchParams.set('min_amount', String(minAmount));
      const res = await fetch(url.toString(), {
        headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
      });
      if (res.ok) return await res.json();
    } catch {
      // offline fallback
    }
    return [];
  }

  async dispatchWhatsAppReminder(
    partyId: string,
    phoneOverride?: string,
    customNote?: string
  ): Promise<import('../types').DispatchReminderResponse> {
    const res = await fetch(`${this.currentBaseUrl}/ledger/reminders/dispatch-whatsapp`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify({
        party_id: partyId,
        phone_override: phoneOverride || null,
        custom_note: customNote || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to dispatch reminder' }));
      throw new Error(err.detail || 'Failed to dispatch reminder');
    }
    return await res.json();
  }

  // -----------------------------------------------------------
  // Profit & Business Reports Methods
  // -----------------------------------------------------------

  async getDailySalesSummary(startDate?: string, endDate?: string): Promise<import('../types').DailySalesSummary> {
    const url = new URL(`${this.currentBaseUrl}/reports/sales/daily`);
    if (startDate) url.searchParams.set('start_date', startDate);
    if (endDate) url.searchParams.set('end_date', endDate);
    const res = await fetch(url.toString(), {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
    });
    if (!res.ok) {
      throw new Error('Failed to fetch daily sales summary');
    }
    return await res.json();
  }

  async getGrossMarginReport(startDate?: string, endDate?: string): Promise<import('../types').GrossMarginReport> {
    const url = new URL(`${this.currentBaseUrl}/reports/margin/gross`);
    if (startDate) url.searchParams.set('start_date', startDate);
    if (endDate) url.searchParams.set('end_date', endDate);
    const res = await fetch(url.toString(), {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
    });
    if (!res.ok) {
      throw new Error('Failed to fetch gross margin report');
    }
    return await res.json();
  }

  async recordExpense(payload: import('../types').ExpenseCreateInput): Promise<import('../types').ExpenseRecord> {
    const res = await fetch(`${this.currentBaseUrl}/reports/expenses`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to record expense' }));
      throw new Error(err.detail || 'Failed to record expense');
    }
    return await res.json();
  }

  async getExpenseSummary(startDate?: string, endDate?: string): Promise<import('../types').ExpenseSummary> {
    const url = new URL(`${this.currentBaseUrl}/reports/expenses`);
    if (startDate) url.searchParams.set('start_date', startDate);
    if (endDate) url.searchParams.set('end_date', endDate);
    const res = await fetch(url.toString(), {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
    });
    if (!res.ok) {
      throw new Error('Failed to fetch expense summary');
    }
    return await res.json();
  }

  async getOutstandingCreditReport(): Promise<import('../types').OutstandingCreditReport> {
    const res = await fetch(`${this.currentBaseUrl}/reports/credit/outstanding`, {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
    });
    if (!res.ok) {
      throw new Error('Failed to fetch outstanding credit report');
    }
    return await res.json();
  }

  async getStockValuationReport(): Promise<import('../types').StockValuationReport> {
    const res = await fetch(`${this.currentBaseUrl}/reports/stock/valuation`, {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
    });
    if (!res.ok) {
      throw new Error('Failed to fetch stock valuation report');
    }
    return await res.json();
  }

  async reconcileCashDrawer(payload: import('../types').CashDrawerReconcileInput): Promise<import('../types').CashDrawerReconcileRecord> {
    const res = await fetch(`${this.currentBaseUrl}/reports/cash/reconcile`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to reconcile cash drawer' }));
      throw new Error(err.detail || 'Failed to reconcile cash drawer');
    }
    return await res.json();
  }

  async getOwnerMorningSnapshot(): Promise<import('../types').OwnerMorningSnapshot> {
    const res = await fetch(`${this.currentBaseUrl}/reports/owner/snapshot`, {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
    });
    if (!res.ok) {
      throw new Error('Failed to fetch owner snapshot');
    }
    return await res.json();
  }

  async askAIAssistant(query: string, language: string = 'both'): Promise<import('../types').AIQueryResponse> {
    const res = await fetch(`${this.currentBaseUrl}/ai/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': DEFAULT_TENANT_ID,
      },
      body: JSON.stringify({ query, language }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to query AI Assistant' }));
      throw new Error(err.detail || 'Failed to query AI Assistant');
    }
    return await res.json();
  }

  async getAISuggestions(): Promise<import('../types').SuggestedQuery[]> {
    const res = await fetch(`${this.currentBaseUrl}/ai/suggestions`, {
      headers: { 'X-Tenant-ID': DEFAULT_TENANT_ID },
    });
    if (!res.ok) {
      return [
        {
          label_en: 'Top Profitable Products',
          label_ta: 'அதிக லாபம் தந்த பொருட்கள்',
          query: 'Which products made the most profit this month?',
        },
        {
          label_en: 'Who Owes Me Money?',
          label_ta: 'யாருக்கு கடன் பாக்கி உள்ளது?',
          query: 'Who owes me money?',
        },
        {
          label_en: 'Items to Reorder',
          label_ta: 'மீண்டும் ஆர்டர் செய்ய வேண்டியவை',
          query: 'Which items should I reorder?',
        },
        {
          label_en: "Today's Sales Summary",
          label_ta: 'இன்றைய விற்பனை விவரம்',
          query: 'How much did I sell today?',
        },
        {
          label_en: 'Dead Stock Analysis',
          label_ta: 'விற்பனை ஆகாத தேக்க சரக்குகள்',
          query: 'Which items are dead stock?',
        },
        {
          label_en: 'Supplier Payables Due',
          label_ta: 'சப்ளையர் பாக்கிகள்',
          query: 'Whom do I owe money to?',
        },
      ];
    }
    return await res.json();
  }
}

export const api = new ApiClient();
