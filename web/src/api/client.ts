import type {
  Product, ProductCreateInput, Party, PartyCreateInput, PartyUpdateInput, POSLineItem, BillSummary,
  PriceList, ReviewFlag, SyncInvoiceResult, ImportResult, LedgerSide,
} from '../types';

// Resolve API base URL: Normalize 'localhost' to '127.0.0.1' to prevent Windows IPv6 [::1] connection timeouts
const getResolvedHost = (): string => {
  if (typeof window === 'undefined' || !window.location.hostname) {
    return '127.0.0.1';
  }
  const host = window.location.hostname;
  return host === 'localhost' ? '127.0.0.1' : host;
};

const resolvedHost = getResolvedHost();
const API_BASE_URL = typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL
  : `http://${resolvedHost}:8000/api/v1`;
const FALLBACK_API_URL = `http://localhost:8000/api/v1`;
const DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001';

// -------------------------------------------------------------
// Decimal normalisation
// -------------------------------------------------------------
// FastAPI/Pydantic v2 serialises every `Decimal` field as a JSON *string*
// ("1234.50"). The UI types declare these as numbers and call
// `.toFixed()` / arithmetic on them, so convert known Decimal fields
// (taken from backend/app/schemas/*.py) into numbers at the API boundary.
// Identifier-like strings (codes, HSN, state codes, phones) are untouched.
const DECIMAL_FIELDS = new Set([
  'actual_cash_counted', 'actual_weight_kg', 'allocated_amount', 'amount', 'apportioned_overhead',
  'bank_upi_expenses', 'base_quantity', 'bucket_0_30', 'bucket_31_60', 'bucket_61_90', 'bucket_90_plus',
  'cash_expenses', 'cash_expenses_paid', 'cash_in_drawer', 'cash_ledger_receipts', 'cash_refunds_paid', 'cash_sales_amount',
  'cash_supplier_payouts', 'cgst_amount', 'cgst_percent', 'cgst_total', 'cogs', 'conversion_factor',
  'cost_price_base', 'cost_price_base_at_sale', 'credit_limit', 'current_balance', 'current_purchase_price_base',
  'current_quantity_base', 'current_stock_base', 'deficit_base', 'discount_amount', 'discount_value',
  'discrepancy_amount', 'discrepancy_value', 'due_amount', 'exact_total', 'expected_cash_drawer',
  'freight_charges', 'grand_total', 'gross_amount', 'gross_margin_estimate', 'gross_margin_percent',
  'gross_profit', 'gst_rate_percent', 'igst_amount', 'igst_percent', 'igst_total', 'landed_cost_base',
  'line_total', 'loading_charges', 'margin_percent', 'min_allowed_price', 'min_stock_base', 'net_operating_profit_today',
  'net_payable', 'opening_balance', 'opening_cash', 'operating_expenses_today', 'other_expenses',
  'outstanding_receivables', 'overall_margin_percent', 'overdue_amount', 'paid_amount', 'party_current_balance',
  'payables_due_suppliers', 'price', 'purchase_price_base', 'quantity', 'quantity_sold_base', 'reorder_quantity_base',
  'round_off', 'round_off_amount', 'selling_price', 'sgst_amount', 'sgst_percent', 'sgst_total',
  'stock_total_valuation', 'subtotal_amount', 'subtotal_taxable', 'suggested_reorder_base',
  'supplier_current_balance', 'tax_amount', 'tax_total', 'taxable_amount', 'taxable_sales', 'today_sales',
  'total_amount', 'total_cogs', 'total_discount', 'total_discrepancy_value', 'total_expenses',
  'total_gross_profit', 'total_invoice_amount', 'total_overdue', 'total_paid', 'total_payable_amount',
  'total_purchases', 'total_receivables', 'total_retail_value', 'total_sales', 'total_tax', 'total_tax_amount',
  'total_taxable_sales', 'total_valuation_cost', 'unallocated_advance', 'unallocated_amount', 'unit_cost_base',
  'unit_price', 'unit_purchase_price', 'urgency_score', 'valuation_cost', 'wac_base', 'weighted_avg_cost_base',
]);
// Dict[str, Decimal] maps whose values (not keys) are amounts
const DECIMAL_MAP_FIELDS = new Set(['sales_by_mode', 'by_category', 'godown_valuations']);

const toNum = (v: unknown): unknown => {
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
  return v;
};

export const normalizeDecimals = (data: any): any => {
  if (Array.isArray(data)) return data.map(normalizeDecimals);
  if (data === null || typeof data !== 'object') return data;
  const out: Record<string, any> = {};
  for (const [key, value] of Object.entries(data)) {
    if (DECIMAL_FIELDS.has(key)) {
      out[key] = toNum(value);
    } else if (DECIMAL_MAP_FIELDS.has(key) && value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toNum(v)]));
    } else {
      out[key] = normalizeDecimals(value);
    }
  }
  return out;
};

const readJson = async (res: Response): Promise<any> => normalizeDecimals(await res.json());

// HTTP error from the server (carries the status so the UI can react to 403 / 409 / 429 ...)
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(message: string, status: number, detail: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

// The request never got an HTTP response (server down / no network). Safe to queue & retry.
export class NetworkError extends Error {
  constructor(message = 'Server unreachable') {
    super(message);
    this.name = 'NetworkError';
  }
}

export const isNetworkError = (e: unknown): e is NetworkError => e instanceof NetworkError;
export const isApiError = (e: unknown, status?: number): e is ApiError =>
  e instanceof ApiError && (status === undefined || e.status === status);

// Extract FastAPI error detail (string or 422 validation list) into a readable message
const errorFromResponse = async (res: Response, fallback: string): Promise<ApiError> => {
  const err = await res.json().catch(() => null);
  let detail: string = fallback;
  if (err && typeof err.detail === 'string') {
    detail = err.detail;
  } else if (err && Array.isArray(err.detail)) {
    detail = err.detail
      .map((d: any) => `${Array.isArray(d.loc) ? d.loc.slice(1).join('.') : ''}: ${d.msg}`)
      .join('; ');
  }
  return new ApiError(`${detail} (HTTP ${res.status})`, res.status, detail);
};

// Every API call is tenant-scoped: the server answers 400 without a valid X-Tenant-ID header.
const withTenant = (headers?: HeadersInit): Headers => {
  const h = new Headers(headers);
  h.set('X-Tenant-ID', DEFAULT_TENANT_ID);
  return h;
};

// Local (shop = IST) calendar date as YYYY-MM-DD. Never use toISOString() for business dates:
// it is UTC, so before 05:30 IST it returns yesterday.
export const localDateStr = (d: Date = new Date()): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

// Money rounding that matches the backend's Decimal ROUND_HALF_UP.
// Plain Math.round(x * 100) / 100 is wrong for values such as 1.005 (float 1.00499..).
export const roundHalfUp = (value: number, places = 2): number => {
  if (!Number.isFinite(value)) return 0;
  const cleaned = Number(value.toFixed(8)); // strip binary float noise (3 * 1.15 = 3.4499999999999997)
  if (Math.abs(cleaned) < 1e-6) return 0;
  const sign = cleaned < 0 ? -1 : 1;
  const shifted = Math.round(Number(`${Math.abs(cleaned)}e${places}`));
  return sign * Number(`${shifted}e-${places}`);
};

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
    current_stock_base: 4700,
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
    current_stock_base: 2025.8,
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
    current_stock_base: 114,
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
    current_stock_base: 320,
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
    current_stock_base: 450,
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

// Last catalogue / parties seen from the server, so offline bills reference real product & party IDs
// (and therefore sync cleanly) instead of the pilot demo catalogue.
const CATALOGUE_CACHE_KEY = 'hbos.cache.products.v1';
const PARTIES_CACHE_KEY = 'hbos.cache.parties.v1';

const readCache = <T,>(key: string): T | null => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
};

const writeCache = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage full / disabled: cache is best-effort only
  }
};

type Json = Record<string, any> | any[];

class ApiClient {
  private isOnline = false;

  private currentBaseUrl = API_BASE_URL;

  // Single entry point for every tenant API call: always sends X-Tenant-ID.
  // Throws NetworkError when no HTTP response was received (server down / offline).
  private async request(path: string, init: RequestInit = {}, timeoutMs?: number): Promise<Response> {
    try {
      const res = await fetch(`${this.currentBaseUrl}${path}`, {
        ...init,
        headers: withTenant(init.headers),
        signal: init.signal ?? (timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined),
      });
      this.isOnline = true;
      return res;
    } catch (e: any) {
      this.isOnline = false;
      throw new NetworkError(e?.name === 'TimeoutError' ? 'Server did not respond in time' : 'Server unreachable');
    }
  }

  // JSON request that throws ApiError on non-2xx and returns Decimal-normalised JSON
  private async json<T>(path: string, fallbackError: string, init: RequestInit = {}, timeoutMs?: number): Promise<T> {
    const res = await this.request(path, init, timeoutMs);
    if (!res.ok) throw await errorFromResponse(res, fallbackError);
    return await readJson(res);
  }

  private post<T>(path: string, body: Json, fallbackError: string, timeoutMs?: number): Promise<T> {
    return this.json<T>(path, fallbackError, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }, timeoutMs);
  }

  private put<T>(path: string, body: Json, fallbackError: string, timeoutMs?: number): Promise<T> {
    return this.json<T>(path, fallbackError, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }, timeoutMs);
  }

  // GET used by list screens: logs and returns `fallback` on any failure instead of throwing
  private async getOr<T>(path: string, fallback: T, timeoutMs?: number): Promise<T> {
    try {
      return await this.json<T>(path, 'API request failed', {}, timeoutMs);
    } catch (e) {
      if (!isNetworkError(e)) console.error(e);
      return fallback;
    }
  }

  private qs(params: Record<string, string | number | boolean | undefined | null>): string {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
    }
    const s = sp.toString();
    return s ? `?${s}` : '';
  }

  async checkHealth(): Promise<boolean> {
    // /health is not tenant-scoped (no X-Tenant-ID needed)
    try {
      const res = await fetch(`${API_BASE_URL}/health`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        this.currentBaseUrl = API_BASE_URL;
        this.isOnline = true;
        return true;
      }
    } catch {
      // primary host failed or timed out
    }

    if (API_BASE_URL !== FALLBACK_API_URL) {
      try {
        const res2 = await fetch(`${FALLBACK_API_URL}/health`, { signal: AbortSignal.timeout(3000) });
        if (res2.ok) {
          this.currentBaseUrl = FALLBACK_API_URL;
          this.isOnline = true;
          return true;
        }
      } catch {
        // fallback offline
      }
    }

    this.isOnline = false;
    return false;
  }

  getOnlineStatus(): boolean {
    return this.isOnline;
  }

  // -----------------------------------------------------------
  // Catalogue & parties
  // -----------------------------------------------------------

  // Products carry current_stock_base + display_stock (all godowns, or one godown via godownId)
  async getProducts(search?: string, godownId?: string): Promise<Product[]> {
    try {
      const products = await this.json<Product[]>(
        `/inventory/products${this.qs({ search, godown_id: godownId })}`,
        'Failed to load products', {}, 5000,
      );
      if (!search && !godownId) writeCache(CATALOGUE_CACHE_KEY, products);
      return products;
    } catch (e) {
      if (!isNetworkError(e)) throw e;
      // Network failure only: backend unreachable -> last catalogue seen online, else pilot catalogue
      const offline = readCache<Product[]>(CATALOGUE_CACHE_KEY) ?? INITIAL_PRODUCTS;
      if (!search) return offline;
      const s = search.toLowerCase();
      return offline.filter(
        p => p.name.toLowerCase().includes(s) ||
             p.code.toLowerCase().includes(s) ||
             (p.tamil_name && p.tamil_name.toLowerCase().includes(s))
      );
    }
  }

  async getPriceLists(): Promise<PriceList[]> {
    return this.getOr<PriceList[]>('/inventory/price-lists', [], 5000);
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
      gst_rate_percent: product.gst_rate_percent ?? 18,
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
      prices: product.prices ?? [],
    };
    // Master data is only created on the server (an offline-only product could never be billed/synced)
    return this.post<Product>('/inventory/products', payload, 'Failed to create product', 10000);
  }

  async importCatalogue(file: File, dryRun: boolean): Promise<ImportResult> {
    const form = new FormData();
    form.append('file', file, file.name);
    // No Content-Type header: the browser sets the multipart boundary. X-Tenant-ID is added by request().
    return this.json<ImportResult>(
      `/inventory/import${this.qs({ dry_run: dryRun ? 'true' : undefined })}`,
      'Import failed',
      { method: 'POST', body: form },
      60000,
    );
  }

  async getParties(): Promise<Party[]> {
    try {
      const parties = await this.json<Party[]>('/ledger/parties', 'Failed to load parties', {}, 5000);
      writeCache(PARTIES_CACHE_KEY, parties);
      return parties;
    } catch (e) {
      if (!isNetworkError(e)) throw e;
      // Network failure only: backend unreachable -> last parties seen online, else pilot parties
      return (readCache<Party[]>(PARTIES_CACHE_KEY) ?? INITIAL_PARTIES).map(p => ({ ...p }));
    }
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
      price_list_id: party.price_list_id || null,
      price_list_code: party.price_list_id ? null : (party.price_list_code || 'RETAIL'),
      credit_limit: party.credit_limit || 0,
      credit_days: party.credit_days || 0,
      opening_balance: party.opening_balance || 0,
    };
    // Parties are master data with ledger entries: create them on the server only
    return this.post<Party>('/ledger/parties', payload, 'Failed to create party', 10000);
  }

  async updateParty(partyId: string, party: PartyUpdateInput): Promise<Party> {
    const payload: Record<string, any> = {};
    if (party.name !== undefined) payload.name = party.name;
    if (party.party_type !== undefined) payload.party_type = party.party_type;
    if (party.phone !== undefined) payload.phone = party.phone || null;
    if (party.email !== undefined) payload.email = party.email || null;
    if (party.gstin !== undefined) payload.gstin = party.gstin || null;
    if (party.state_code !== undefined) payload.state_code = party.state_code;
    if (party.billing_address !== undefined) payload.billing_address = party.billing_address || null;
    if (party.price_list_id !== undefined) payload.price_list_id = party.price_list_id;
    if (party.price_list_code !== undefined) payload.price_list_code = party.price_list_code;
    if (party.credit_limit !== undefined) payload.credit_limit = party.credit_limit;
    if (party.credit_days !== undefined) payload.credit_days = party.credit_days;
    if (party.is_active !== undefined) payload.is_active = party.is_active;

    const updated = await this.put<Party>(`/ledger/parties/${partyId}`, payload, 'Failed to update party', 10000);
    const cached = readCache<Party[]>(PARTIES_CACHE_KEY);
    if (cached) {
      const idx = cached.findIndex(p => p.id === partyId);
      if (idx !== -1) {
        cached[idx] = { ...cached[idx], ...updated };
        writeCache(PARTIES_CACHE_KEY, cached);
      }
    }
    return updated;
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
      // Mirrors backend InvoiceCalculator (Decimal, ROUND_HALF_UP) so the counter total == posted total
      const gross = roundHalfUp(line.quantity * line.unitPrice);
      let disc = line.discountType === 'PERCENT'
        ? roundHalfUp(gross * (line.discountValue / 100))
        : roundHalfUp(line.discountValue);
      disc = Math.min(disc, gross);
      const taxable = roundHalfUp(gross - disc);

      let cgst = 0;
      let sgst = 0;
      let igst = 0;

      if (isInterState) {
        igst = roundHalfUp(taxable * (line.gstRatePercent / 100));
      } else {
        const halfRate = line.gstRatePercent / 2;
        cgst = roundHalfUp(taxable * (halfRate / 100));
        sgst = roundHalfUp(taxable * (halfRate / 100));
      }

      line.grossAmount = gross;
      line.discountAmount = disc;
      line.taxableAmount = taxable;
      line.cgstAmount = cgst;
      line.sgstAmount = sgst;
      line.igstAmount = igst;
      line.lineTotal = roundHalfUp(taxable + cgst + sgst + igst);

      subtotalTaxable += taxable;
      totalDiscount += disc;
      cgstTotal += cgst;
      sgstTotal += sgst;
      igstTotal += igst;
    }

    subtotalTaxable = roundHalfUp(subtotalTaxable);
    totalDiscount = roundHalfUp(totalDiscount);
    cgstTotal = roundHalfUp(cgstTotal);
    sgstTotal = roundHalfUp(sgstTotal);
    igstTotal = roundHalfUp(igstTotal);

    const taxTotal = roundHalfUp(cgstTotal + sgstTotal + igstTotal);
    const exactTotal = roundHalfUp(subtotalTaxable + taxTotal);
    const grandTotal = roundHalfUp(exactTotal, 0);
    const roundOff = roundHalfUp(grandTotal - exactTotal);
    const paid = paidAmount !== undefined ? Math.min(roundHalfUp(paidAmount), grandTotal) : grandTotal;
    const dueAmount = roundHalfUp(Math.max(0, grandTotal - paid));

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
  // Owner PIN
  // -------------------------------------------------------------

  // true/false for a well-formed answer; throws ApiError(429) while locked out, NetworkError offline
  async verifyOwnerPin(pin: string): Promise<boolean> {
    const res = await this.post<{ valid: boolean }>('/auth/verify-pin', { pin }, 'PIN check failed', 8000);
    return Boolean(res.valid);
  }

  // 403 wrong current PIN, 422 bad new PIN (4-8 digits), 429 locked out
  async changeOwnerPin(currentPin: string, newPin: string): Promise<void> {
    await this.post<{ status: string }>('/auth/change-pin', { current_pin: currentPin, new_pin: newPin }, 'PIN change failed', 8000);
  }

  // -------------------------------------------------------------
  // Smart Inventory Module Methods
  // -------------------------------------------------------------

  async getGodowns(): Promise<import('../types').Godown[]> {
    try {
      return await this.json<import('../types').Godown[]>('/inventory/godowns', 'Failed to load godowns', {}, 3000);
    } catch (e) {
      if (!isNetworkError(e)) {
        console.error(e);
        return [];
      }
    }
    // offline fallback (backend unreachable)
    return [
      { id: 'g-main', code: 'MAIN', name: 'Main Shop Godown', is_primary: true, is_active: true },
      { id: 'g-bypass', code: 'BYPASS', name: 'Salem Bypass Godown 2', is_primary: false, is_active: true }
    ];
  }

  async getGodownStock(godownId: string): Promise<import('../types').GodownStockItem[]> {
    return this.getOr(`/inventory/godowns/${godownId}/stock`, [], 3000);
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
    return this.post<any>('/inventory/godowns/transfer', payload, 'Transfer failed');
  }

  async getPurchases(): Promise<import('../types').PurchaseBill[]> {
    return this.getOr('/inventory/purchases', [], 3000);
  }

  async createPurchase(payload: any): Promise<import('../types').PurchaseBill> {
    return this.post('/inventory/purchases', payload, 'Failed to record purchase');
  }

  async getAdjustments(): Promise<import('../types').StockAdjustment[]> {
    return this.getOr('/inventory/adjustments', [], 3000);
  }

  async createAdjustment(payload: any): Promise<import('../types').StockAdjustment> {
    return this.post('/inventory/adjustments', payload, 'Failed to record stock adjustment');
  }

  async getLowStockAlerts(godownId?: string): Promise<import('../types').LowStockAlert[]> {
    return this.getOr(`/inventory/alerts/low-stock${this.qs({ godown_id: godownId })}`, [], 3000);
  }

  async getProductPriceHistory(productId: string): Promise<import('../types').ProductPriceHistory> {
    return this.json(`/inventory/products/${productId}/price-history`, 'Failed to fetch price history', {}, 3000);
  }

  async updateProductPrice(productId: string, payload: {
    price_list_id: string;
    unit_name: string;
    price: number;
    min_allowed_price?: number;
  }) {
    return this.post<any>(`/inventory/products/${productId}/prices`, payload, 'Failed to update price');
  }

  // -----------------------------------------------------------
  // Fast Billing APIs: Search, Invoices, Returns, Quotes, Challans
  // -----------------------------------------------------------

  async searchBillingProducts(query: string, godownId?: string, priceListId?: string): Promise<import('../types').ProductSearchItem[]> {
    // offline / error: [] (caller falls back to the local catalogue)
    return this.getOr(`/billing/search${this.qs({ q: query, godown_id: godownId, price_list_id: priceListId })}`, [], 3000);
  }

  async decomposeUnitQuantity(payload: {
    product_id: string;
    quantity: number;
    unit_name: string;
    actual_weight_kg?: number;
  }) {
    return this.post<any>('/billing/unit-decompose', payload, 'Failed to decompose unit quantity');
  }

  // Throws NetworkError when the server was not reached (caller may queue the bill offline),
  // ApiError(403) for a wrong/missing owner PIN with owner_override, ApiError(429) when locked out.
  // No client timeout: a timed-out request may still be posted server-side, so it must not be re-queued.
  async createInvoice(payload: any): Promise<import('../types').SalesInvoiceRecord> {
    return this.post('/billing/invoices', payload, 'Failed to post sales invoice');
  }

  // Push queued offline invoices; conflicts come back as review_flags, never as rejections
  async syncInvoices(payloads: any[]): Promise<SyncInvoiceResult[]> {
    return this.post<SyncInvoiceResult[]>('/billing/sync-invoices', payloads, 'Offline invoice sync failed');
  }

  async listInvoices(limit = 50): Promise<import('../types').SalesInvoiceRecord[]> {
    return this.getOr(`/billing/invoices${this.qs({ limit })}`, []);
  }

  async createSalesReturn(payload: any): Promise<import('../types').SalesReturnRecord> {
    return this.post('/billing/returns', payload, 'Failed to record sales return');
  }

  async listSalesReturns(limit = 50): Promise<import('../types').SalesReturnRecord[]> {
    return this.getOr(`/billing/returns${this.qs({ limit })}`, []);
  }

  async createQuotation(payload: any): Promise<import('../types').QuotationRecord> {
    return this.post('/billing/quotations', payload, 'Failed to create quotation');
  }

  async listQuotations(limit = 50): Promise<import('../types').QuotationRecord[]> {
    return this.getOr(`/billing/quotations${this.qs({ limit })}`, []);
  }

  async convertQuotationToInvoice(quotationId: string, paymentMode = 'CASH', paidAmount?: number): Promise<import('../types').SalesInvoiceRecord> {
    return this.post(`/billing/quotations/${quotationId}/convert-to-invoice`,
      { payment_mode: paymentMode, paid_amount: paidAmount }, 'Failed to convert quotation');
  }

  async createDeliveryChallan(payload: any): Promise<import('../types').DeliveryChallanRecord> {
    return this.post('/billing/challans', payload, 'Failed to create delivery challan');
  }

  async listDeliveryChallans(limit = 50): Promise<import('../types').DeliveryChallanRecord[]> {
    return this.getOr(`/billing/challans${this.qs({ limit })}`, []);
  }

  async convertChallanToInvoice(challanId: string, paymentMode = 'CREDIT', paidAmount?: number): Promise<import('../types').SalesInvoiceRecord> {
    return this.post(`/billing/challans/${challanId}/convert-to-invoice`,
      { payment_mode: paymentMode, paid_amount: paidAmount }, 'Failed to convert delivery challan');
  }

  // -----------------------------------------------------------
  // Owner review flags (negative stock / credit limit / floor price conflicts)
  // -----------------------------------------------------------

  async getReviewFlags(status: 'OPEN' | 'RESOLVED' | 'ALL' = 'OPEN', limit = 100): Promise<ReviewFlag[]> {
    return this.json(`/billing/review-flags${this.qs({ status, limit })}`, 'Failed to load review flags', {}, 5000);
  }

  // 403 wrong PIN, 404 unknown flag, 409 already resolved, 429 locked out
  async resolveReviewFlag(flagId: string, ownerPin: string, notes?: string): Promise<ReviewFlag> {
    return this.post(`/billing/review-flags/${flagId}/resolve`, { owner_pin: ownerPin, notes: notes || null }, 'Failed to resolve review flag');
  }

  // -----------------------------------------------------------
  // Customer & Supplier Ledger Methods
  // -----------------------------------------------------------

  async recordReceiptVoucher(payload: import('../types').ReceiptVoucherCreateInput): Promise<import('../types').ReceiptVoucherRecord> {
    return this.post('/ledger/receipts', payload, 'Failed to record receipt voucher');
  }

  async recordSupplierPayment(payload: import('../types').SupplierPaymentCreateInput): Promise<import('../types').SupplierPaymentRecord> {
    return this.post('/ledger/supplier-payments', payload, 'Failed to record supplier payment');
  }

  // side: RECEIVABLE (sales bills) or PAYABLE (purchase bills). Server default: PAYABLE for SUPPLIER parties.
  async getPartyOpenDues(partyId: string, asOf?: string, side?: LedgerSide): Promise<import('../types').InvoiceDueItem[]> {
    return this.getOr(`/ledger/parties/${partyId}/dues${this.qs({ as_of: asOf, side })}`, []);
  }

  async getPartyAgeing(partyId: string, asOf?: string, side?: LedgerSide): Promise<import('../types').PartyAgeingSummary | null> {
    return this.getOr(`/ledger/parties/${partyId}/ageing${this.qs({ as_of: asOf, side })}`, null);
  }

  async getSupplierBalancesSummary(): Promise<import('../types').SupplierBalancesSummary> {
    return this.getOr('/ledger/suppliers/summary', { total_suppliers: 0, total_payable_amount: 0, suppliers: [] });
  }

  // Only parties with overdue bills; overdue_amount is the overdue part of the balance
  async getCollectionCallList(minDays = 0, minAmount = 0): Promise<import('../types').CollectionReminderItem[]> {
    return this.getOr(`/ledger/reminders/call-list${this.qs({
      min_days_overdue: minDays > 0 ? minDays : undefined,
      min_amount: minAmount > 0 ? minAmount : undefined,
    })}`, []);
  }

  async dispatchWhatsAppReminder(
    partyId: string,
    phoneOverride?: string,
    customNote?: string
  ): Promise<import('../types').DispatchReminderResponse> {
    return this.post('/ledger/reminders/dispatch-whatsapp', {
      party_id: partyId,
      phone_override: phoneOverride || null,
      custom_note: customNote || null,
    }, 'Failed to dispatch reminder');
  }

  // -----------------------------------------------------------
  // Profit & Business Reports Methods (dates are local IST calendar days: YYYY-MM-DD)
  // -----------------------------------------------------------

  async getDailySalesSummary(startDate?: string, endDate?: string): Promise<import('../types').DailySalesSummary> {
    return this.json(`/reports/sales/daily${this.qs({ start_date: startDate, end_date: endDate })}`, 'Failed to fetch daily sales summary');
  }

  async getGrossMarginReport(startDate?: string, endDate?: string): Promise<import('../types').GrossMarginReport> {
    return this.json(`/reports/margin/gross${this.qs({ start_date: startDate, end_date: endDate })}`, 'Failed to fetch gross margin report');
  }

  async recordExpense(payload: import('../types').ExpenseCreateInput): Promise<import('../types').ExpenseRecord> {
    return this.post('/reports/expenses', payload, 'Failed to record expense');
  }

  async getExpenseSummary(startDate?: string, endDate?: string): Promise<import('../types').ExpenseSummary> {
    return this.json(`/reports/expenses${this.qs({ start_date: startDate, end_date: endDate })}`, 'Failed to fetch expense summary');
  }

  async getOutstandingCreditReport(): Promise<import('../types').OutstandingCreditReport> {
    return this.json('/reports/credit/outstanding', 'Failed to fetch outstanding credit report');
  }

  async getStockValuationReport(): Promise<import('../types').StockValuationReport> {
    return this.json('/reports/stock/valuation', 'Failed to fetch stock valuation report');
  }

  async reconcileCashDrawer(payload: import('../types').CashDrawerReconcileInput): Promise<import('../types').CashDrawerReconcileRecord> {
    return this.post('/reports/cash/reconcile', payload, 'Failed to reconcile cash drawer');
  }

  async getOwnerMorningSnapshot(): Promise<import('../types').OwnerMorningSnapshot> {
    return this.json('/reports/owner/snapshot', 'Failed to fetch owner snapshot');
  }

  async askAIAssistant(query: string, language: string = 'both'): Promise<import('../types').AIQueryResponse> {
    return this.post('/ai/query', { query, language }, 'Failed to query AI Assistant');
  }

  async getAISuggestions(): Promise<import('../types').SuggestedQuery[]> {
    try {
      return await this.json<import('../types').SuggestedQuery[]>('/ai/suggestions', 'Failed to load suggestions');
    } catch {
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
  }
}

export const api = new ApiClient();
