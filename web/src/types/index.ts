export type Language = 'en' | 'ta';

export interface ProductUnit {
  id?: string;
  unit_name: string;
  conversion_factor: number;
  can_buy: boolean;
  can_sell: boolean;
  barcode?: string;
  is_default_sales_unit?: boolean;
  is_default_purchase_unit?: boolean;
}

export interface Product {
  id: string;
  code: string;
  name: string;
  tamil_name?: string;
  category_id?: string;
  brand_id?: string;
  hsn_code: string;
  base_unit: string;
  is_variable_weight: boolean;
  min_stock_base: number;
  reorder_quantity_base?: number;
  purchase_price_base: number;
  // GST slab from the product master (0 / 5 / 12 / 18 / 28)
  gst_rate_percent?: number;
  units: ProductUnit[];
  // Stock in base units summed across godowns (or the requested godown) + packaging breakdown
  current_stock_base?: number;
  stock_base?: number;
  display_stock?: string;
}

export interface ProductCreateInput {
  code: string;
  name: string;
  tamil_name?: string;
  category_id?: string;
  brand_id?: string;
  hsn_code: string;
  base_unit: string;
  is_variable_weight?: boolean;
  min_stock_base?: number;
  reorder_quantity_base?: number;
  purchase_price_base: number;
  gst_rate_percent?: number;
  prices?: Array<{ price_list_id: string; unit_name: string; price: number; min_allowed_price?: number }>;
  units?: Array<{
    unit_name: string;
    conversion_factor: number;
    can_buy?: boolean;
    can_sell?: boolean;
    barcode?: string;
    is_default_sales_unit?: boolean;
    is_default_purchase_unit?: boolean;
  }>;
}

export interface Party {
  id: string;
  party_type: 'CUSTOMER' | 'SUPPLIER' | 'BOTH';
  name: string;
  phone?: string;
  email?: string;
  gstin?: string;
  state_code: string;
  billing_address?: string;
  credit_limit: number;
  credit_days: number;
  current_balance: number;
  opening_balance?: number;
  // Price tier (Retail / Contractor / Wholesale ...) resolved by the server from price_list_id
  price_list_id?: string;
  price_list_code?: string;
  price_list_name?: string;
}

export interface PriceList {
  id: string;
  code: string;
  name: string;
  is_default: boolean;
}

export interface PartyCreateInput {
  party_type?: 'CUSTOMER' | 'SUPPLIER' | 'BOTH';
  name: string;
  phone?: string;
  email?: string;
  gstin?: string;
  state_code?: string;
  billing_address?: string;
  credit_limit?: number;
  credit_days?: number;
  opening_balance?: number;
  price_list_code?: string;
  price_list_id?: string;
}

export interface PartyUpdateInput {
  party_type?: 'CUSTOMER' | 'SUPPLIER' | 'BOTH';
  name?: string;
  phone?: string;
  email?: string;
  gstin?: string;
  state_code?: string;
  billing_address?: string;
  credit_limit?: number;
  credit_days?: number;
  price_list_code?: string;
  price_list_id?: string;
  is_active?: boolean;
}

export interface POSLineItem {
  id: string;
  productId: string;
  productCode: string;
  name: string;
  tamilName?: string;
  hsnCode: string;
  unitName: string;
  conversionFactor: number;
  quantity: number;
  isVariableWeight: boolean;
  actualWeightKg?: number;
  baseQuantity: number;
  unitPrice: number;
  grossAmount?: number;
  discountType: 'PERCENT' | 'FLAT';
  discountValue: number;
  discountAmount: number;
  taxableAmount: number;
  gstRatePercent: number;
  cgstAmount: number;
  sgstAmount: number;
  igstAmount: number;
  lineTotal: number;
  availableUnits: ProductUnit[];
  // Selling price per unit name from the customer's price list (via /billing/search)
  unitPrices?: Record<string, number>;
  returnCondition?: 'EXCESS' | 'DAMAGED';
}

export interface BillSummary {
  subtotalTaxable: number;
  totalDiscount: number;
  cgstTotal: number;
  sgstTotal: number;
  igstTotal: number;
  taxTotal: number;
  exactTotal: number;
  roundOff: number;
  grandTotal: number;
  paidAmount: number;
  dueAmount: number;
  isInterState: boolean;
}

export interface HeldBill {
  id: string;
  heldAt: string;
  partyName: string;
  partyId?: string;
  lines: POSLineItem[];
  grandTotal: number;
}

// -------------------------------------------------------------
// Smart Inventory Feature Types
// -------------------------------------------------------------

export interface Godown {
  id: string;
  code: string;
  name: string;
  is_primary: boolean;
  is_active: boolean;
  created_at?: string;
}

export interface GodownStockItem {
  product_id: string;
  product_code: string;
  product_name: string;
  tamil_name?: string;
  base_unit: string;
  current_quantity_base: number;
  weighted_avg_cost_base: number;
  display_stock: string;
  min_stock_base: number;
  is_low_stock: boolean;
}

export interface PurchaseBillLine {
  id?: string;
  line_number?: number;
  product_id: string;
  unit_name: string;
  conversion_factor: number;
  quantity: number;
  base_quantity?: number;
  unit_purchase_price: number;
  discount_amount: number;
  taxable_amount?: number;
  gst_rate_percent: number;
  tax_amount?: number;
  line_total?: number;
  apportioned_overhead?: number;
  landed_cost_base?: number;
}

export interface PurchaseBill {
  id: string;
  supplier_id?: string;
  supplier_name: string;
  supplier_invoice_number: string;
  bill_date: string;
  godown_id: string;
  subtotal_taxable: number;
  total_tax_amount: number;
  freight_charges: number;
  loading_charges: number;
  other_expenses: number;
  round_off_amount: number;
  total_invoice_amount: number;
  notes?: string;
  lines: PurchaseBillLine[];
}

export interface StockAdjustmentLine {
  id?: string;
  product_id: string;
  unit_name: string;
  conversion_factor: number;
  quantity: number;
  base_quantity?: number;
  unit_cost_base?: number;
  discrepancy_value?: number;
}

export interface StockAdjustment {
  id: string;
  adjustment_number: string;
  adjustment_date: string;
  godown_id: string;
  reason_type: 'BREAKAGE' | 'THEFT' | 'EXPIRY' | 'COUNT_CORRECTION';
  total_discrepancy_value: number;
  notes?: string;
  lines: StockAdjustmentLine[];
}

export interface LowStockAlert {
  product_id: string;
  product_code: string;
  product_name: string;
  tamil_name?: string;
  base_unit: string;
  current_stock_base: number;
  min_stock_base: number;
  reorder_quantity_base: number;
  deficit_base: number;
  suggested_reorder_base: number;
  alert_severity: 'CRITICAL_NEGATIVE' | 'OUT_OF_STOCK' | 'CRITICAL_LOW' | 'LOW_STOCK';
  display_stock: string;
  display_suggested_reorder: string;
}

export interface PriceHistoryItem {
  price_list_id: string;
  price_list_code: string;
  price_list_name: string;
  unit_name: string;
  price: number;
  min_allowed_price?: number;
  effective_from: string;
  effective_to?: string;
  is_current: boolean;
}

export interface PurchaseCostHistoryItem {
  purchase_date: string;
  supplier_name: string;
  supplier_invoice_number: string;
  unit_name: string;
  quantity: number;
  unit_purchase_price: number;
  landed_cost_base: number;
}

export interface ProductPriceHistory {
  product_id: string;
  product_code: string;
  product_name: string;
  current_purchase_price_base: number;
  selling_price_history: PriceHistoryItem[];
  purchase_cost_history: PurchaseCostHistoryItem[];
}

// -------------------------------------------------------------
// Fast Billing Feature Types: Invoices, Returns, Quotations, Challans
// -------------------------------------------------------------

export type BillingMode = 'INVOICE' | 'RETURN' | 'QUOTATION' | 'CHALLAN';

export interface ProductSearchItem {
  id: string;
  code: string;
  name: string;
  tamil_name?: string;
  hsn_code: string;
  base_unit: string;
  is_variable_weight: boolean;
  gst_rate_percent: number;
  current_stock_base: number;
  current_stock_display: string;
  cost_price_base: number;
  matched_unit?: string;
  selling_price: number;
  units: Array<{
    unit_name: string;
    conversion_factor: number;
    can_sell: boolean;
    barcode?: string;
    is_default_sales_unit?: boolean;
    selling_price: number;
  }>;
}

export interface SalesInvoiceRecord {
  id: string;
  invoice_number: string;
  invoice_date: string;
  party_id?: string;
  customer_name: string;
  customer_phone?: string;
  customer_gstin?: string;
  place_of_supply_state_code: string;
  is_b2b: boolean;
  price_list_id: string;
  godown_id: string;
  status: string;
  subtotal_amount: number;
  discount_amount: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total_tax_amount: number;
  round_off_amount: number;
  grand_total: number;
  paid_amount: number;
  due_amount: number;
  payment_mode: string;
  payment_breakdown?: any;
  upi_qr_string?: string;
  is_offline_created: boolean;
  // Server-side soft warnings, e.g. NEGATIVE_STOCK_WARNING, CREDIT_LIMIT_EXCEEDED, BELOW_FLOOR_PRICE
  review_flags?: string[];
  lines: Array<{
    id: string;
    line_number: number;
    product_id: string;
    unit_name: string;
    conversion_factor: number;
    quantity: number;
    actual_weight_kg?: number;
    base_quantity: number;
    unit_price: number;
    discount_amount: number;
    taxable_amount: number;
    gst_rate_percent: number;
    cgst_amount: number;
    sgst_amount: number;
    igst_amount: number;
    line_total: number;
  }>;
}

export interface SalesReturnRecord {
  id: string;
  return_number: string;
  return_date: string;
  original_invoice_id?: string;
  original_invoice_number?: string;
  party_id?: string;
  customer_name: string;
  godown_id: string;
  refund_mode: string;
  subtotal_amount: number;
  total_tax_amount: number;
  grand_total: number;
  reason?: string;
  notes?: string;
  lines: Array<{
    id: string;
    line_number: number;
    product_id: string;
    unit_name: string;
    conversion_factor: number;
    quantity: number;
    base_quantity: number;
    unit_price: number;
    taxable_amount: number;
    gst_rate_percent: number;
    tax_amount: number;
    line_total: number;
    return_condition?: 'EXCESS' | 'DAMAGED';
  }>;
}

export interface QuotationRecord {
  id: string;
  quotation_number: string;
  quotation_date: string;
  valid_until?: string;
  party_id?: string;
  customer_name: string;
  customer_phone?: string;
  price_list_id: string;
  godown_id: string;
  place_of_supply_state_code: string;
  status: 'OPEN' | 'CONVERTED' | 'EXPIRED';
  converted_invoice_id?: string;
  subtotal_amount: number;
  discount_amount: number;
  total_tax_amount: number;
  round_off_amount: number;
  grand_total: number;
  notes?: string;
  lines: Array<{
    id: string;
    line_number: number;
    product_id: string;
    unit_name: string;
    conversion_factor: number;
    quantity: number;
    unit_price: number;
    discount_amount: number;
    taxable_amount: number;
    gst_rate_percent: number;
    tax_amount: number;
    line_total: number;
  }>;
}

export interface DeliveryChallanRecord {
  id: string;
  challan_number: string;
  challan_date: string;
  party_id?: string;
  customer_name: string;
  customer_phone?: string;
  delivery_site_address?: string;
  vehicle_number?: string;
  godown_id: string;
  status: 'DISPATCHED' | 'DELIVERED' | 'INVOICED';
  invoiced_invoice_id?: string;
  subtotal_amount: number;
  grand_total: number;
  notes?: string;
  lines: Array<{
    id: string;
    line_number: number;
    product_id: string;
    unit_name: string;
    conversion_factor: number;
    quantity: number;
    base_quantity: number;
    unit_price: number;
    line_total: number;
  }>;
}

// -------------------------------------------------------------
// Customer & Supplier Ledger Module Types
// -------------------------------------------------------------

export interface PaymentAllocationItem {
  invoice_entry_id: string;
  amount: number;
}

export interface AllocationDetail {
  allocation_id: string;
  invoice_entry_id: string;
  invoice_number: string;
  allocated_amount: number;
}

export interface ReceiptVoucherCreateInput {
  party_id: string;
  voucher_date?: string;
  payment_mode: 'CASH' | 'UPI' | 'NEFT_RTGS' | 'CHEQUE';
  reference_number?: string;
  total_amount: number;
  allocation_method: 'OLDEST_FIRST' | 'MANUAL';
  manual_allocations?: PaymentAllocationItem[];
  notes?: string;
}

export interface ReceiptVoucherRecord {
  id: string;
  party_id: string;
  party_name: string;
  voucher_number: string;
  voucher_date: string;
  payment_mode: string;
  reference_number?: string;
  total_amount: number;
  allocated_amount: number;
  unallocated_amount: number;
  party_current_balance: number;
  allocations: AllocationDetail[];
  notes?: string;
}

export interface SupplierPaymentCreateInput {
  supplier_id: string;
  payment_date?: string;
  payment_mode: 'CASH' | 'UPI' | 'NEFT_RTGS' | 'CHEQUE';
  reference_number?: string;
  amount: number;
  notes?: string;
}

export interface SupplierPaymentRecord {
  id: string;
  supplier_id: string;
  supplier_name: string;
  voucher_number: string;
  payment_date: string;
  payment_mode: string;
  reference_number?: string;
  amount: number;
  supplier_current_balance: number;
  notes?: string;
}

export interface InvoiceDueItem {
  entry_id: string;
  doc_type: string;
  doc_number: string;
  doc_date: string;
  total_amount: number;
  allocated_amount: number;
  due_amount: number;
  age_days: number;
  bucket: '0-30' | '31-60' | '61-90' | '90+';
  is_overdue: boolean;
}

export type LedgerSide = 'RECEIVABLE' | 'PAYABLE';

export interface PartyAgeingSummary {
  party_id: string;
  party_name: string;
  phone?: string;
  // RECEIVABLE = customer sales bills, PAYABLE = supplier purchase bills
  side: LedgerSide;
  credit_limit: number;
  credit_days: number;
  current_balance: number;
  is_credit_exceeded: boolean;
  bucket_0_30: number;
  bucket_31_60: number;
  bucket_61_90: number;
  bucket_90_plus: number;
  total_overdue: number;
  unallocated_advance: number;
  open_invoices: InvoiceDueItem[];
}

export interface SupplierBalanceItem {
  supplier_id: string;
  name: string;
  phone?: string;
  gstin?: string;
  total_purchases: number;
  total_paid: number;
  current_balance: number;
  net_payable: number;
  last_transaction_date?: string;
}

export interface SupplierBalancesSummary {
  total_suppliers: number;
  total_payable_amount: number;
  suppliers: SupplierBalanceItem[];
}

export interface CollectionReminderItem {
  party_id: string;
  customer_name: string;
  phone?: string;
  current_balance: number;
  credit_limit: number;
  credit_days: number;
  oldest_bill_number?: string;
  oldest_bill_date?: string;
  days_overdue: number;
  overdue_amount: number;
  urgency_score: number;
  whatsapp_message: string;
  upi_payment_link: string;
}

export interface DispatchReminderResponse {
  log_id: string;
  party_id: string;
  recipient_phone: string;
  message_text: string;
  upi_link?: string;
  status: string;
  dispatched_at: string;
}

// -------------------------------------------------------------
// Profit & Business Reports Module Types
// -------------------------------------------------------------

export interface DailySalesSummary {
  period_start: string;
  period_end: string;
  total_invoices: number;
  taxable_amount: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total_tax: number;
  round_off: number;
  grand_total: number;
  sales_by_mode: Record<string, number>;
  hourly_breakdown: Array<{
    hour: string;
    invoice_count: number;
    total_sales: number;
  }>;
}

export interface ProductMarginItem {
  product_id: string;
  product_code: string;
  product_name: string;
  base_unit: string;
  quantity_sold_base: number;
  taxable_sales: number;
  cogs: number;
  gross_profit: number;
  margin_percent: number;
}

export interface GrossMarginReport {
  period_start: string;
  period_end: string;
  total_taxable_sales: number;
  total_cogs: number;
  total_gross_profit: number;
  overall_margin_percent: number;
  top_margin_products: ProductMarginItem[];
  low_margin_products: ProductMarginItem[];
}

export interface ExpenseCreateInput {
  expense_date?: string;
  category: string;
  amount: number;
  payment_mode: 'CASH' | 'UPI' | 'NEFT_RTGS' | 'CHEQUE';
  vendor_or_recipient: string;
  reference_number?: string;
  is_direct_expense?: boolean;
  notes?: string;
}

export interface ExpenseRecord {
  id: string;
  voucher_number: string;
  expense_date: string;
  category: string;
  amount: number;
  payment_mode: string;
  vendor_or_recipient: string;
  reference_number?: string;
  is_direct_expense: boolean;
  notes?: string;
  created_at: string;
}

export interface ExpenseSummary {
  period_start: string;
  period_end: string;
  total_expenses: number;
  cash_expenses: number;
  bank_upi_expenses: number;
  by_category: Record<string, number>;
  expenses: ExpenseRecord[];
}

export interface DebtorSummaryItem {
  party_id: string;
  party_name: string;
  phone?: string;
  credit_limit: number;
  credit_days: number;
  current_balance: number;
  is_credit_exceeded: boolean;
  days_overdue: number;
  bucket_0_30: number;
  bucket_31_60: number;
  bucket_61_90: number;
  bucket_90_plus: number;
  total_overdue: number;
}

export interface OutstandingCreditReport {
  total_parties: number;
  total_receivables: number;
  total_overdue: number;
  breached_parties_count: number;
  bucket_0_30: number;
  bucket_31_60: number;
  bucket_61_90: number;
  bucket_90_plus: number;
  top_debtors: DebtorSummaryItem[];
}

export interface StockValuationItem {
  product_id: string;
  product_code: string;
  product_name: string;
  base_unit: string;
  current_stock_base: number;
  wac_base: number;
  valuation_cost: number;
  display_stock: string;
  is_low_stock: boolean;
}

export interface StockValuationReport {
  total_products: number;
  total_valuation_cost: number;
  total_retail_value: number;
  low_stock_count: number;
  godown_valuations: Record<string, number>;
  items: StockValuationItem[];
}

export interface CashDrawerReconcileInput {
  counter_name?: string;
  cashier_name?: string;
  session_date?: string;
  opening_cash: number;
  actual_cash_counted: number;
  denominations?: Record<string, number>;
  notes?: string;
}

export interface CashDrawerReconcileRecord {
  id: string;
  session_code: string;
  session_date: string;
  counter_name: string;
  cashier_name?: string;
  status: string;
  opening_cash: number;
  cash_sales_amount: number;
  cash_ledger_receipts: number;
  // CASH refunds paid on sales returns that day (already subtracted from expected_cash_drawer)
  cash_refunds_paid: number;
  cash_expenses_paid: number;
  cash_supplier_payouts: number;
  expected_cash_drawer: number;
  actual_cash_counted: number;
  discrepancy_amount: number;
  denominations?: Record<string, number>;
  notes?: string;
  opened_at: string;
  closed_at?: string;
}

export interface OwnerMorningSnapshot {
  today_sales: number;
  invoices_count_today: number;
  gross_margin_estimate: number;
  gross_margin_percent: number;
  operating_expenses_today: number;
  net_operating_profit_today: number;
  cash_in_drawer: number;
  outstanding_receivables: number;
  overdue_debtors_count: number;
  payables_due_suppliers: number;
  stock_total_valuation: number;
  low_stock_alerts_count: number;
  top_selling_product?: string;
}

// =============================================================================
// AI Business Assistant Types
// =============================================================================

export interface AITableColumn {
  key: string;
  label_en: string;
  label_ta: string;
  type: 'text' | 'currency' | 'number' | 'badge';
}

export interface AIDataCard {
  title_en: string;
  title_ta: string;
  columns: AITableColumn[];
  rows: Record<string, any>[];
  summary_chips: {
    label_en: string;
    label_ta: string;
    value: string;
  }[];
}

export interface AIActionLink {
  label_en: string;
  label_ta: string;
  route: string;
  action_type: string;
  metadata?: Record<string, any>;
}

export interface SuggestedQuery {
  label_en: string;
  label_ta: string;
  query: string;
}

export interface AIQueryResponse {
  query: string;
  detected_intent: string;
  tool_called: string;
  tool_parameters: Record<string, any>;
  answer_en: string;
  answer_ta: string;
  data_card?: AIDataCard | null;
  action_link?: AIActionLink | null;
  raw_data?: Record<string, any> | null;
  suggested_queries: SuggestedQuery[];
}





// =============================================================================
// Owner review flags, offline sync & catalogue import
// =============================================================================

export type ReviewFlagType = 'NEGATIVE_STOCK_WARNING' | 'CREDIT_LIMIT_EXCEEDED' | 'BELOW_FLOOR_PRICE' | string;

export interface ReviewFlag {
  id: string;
  alert_type: ReviewFlagType;
  status: 'OPEN' | 'RESOLVED';
  reference_doc_type: string;
  reference_doc_id: string;
  reference_doc_number: string;
  product_id?: string | null;
  party_id?: string | null;
  godown_id?: string | null;
  message: string;
  is_offline_created: boolean;
  owner_override: boolean;
  created_at: string;
  resolved_at?: string | null;
  resolution_notes?: string | null;
}

export interface SyncInvoiceResult {
  invoice_number?: string | null;
  status: 'SYNCED' | 'ERROR';
  invoice_id?: string | null;
  review_flags: string[];
  error?: string | null;
}

export interface ImportErrorItem {
  row_number: number;
  field: string;
  message: string;
}

export interface ImportRowResult {
  row_number: number;
  code?: string | null;
  status: 'CREATED' | 'UPDATED' | 'VALID' | 'ERROR';
  errors: ImportErrorItem[];
}

export interface ImportResult {
  file_name: string;
  dry_run: boolean;
  committed: boolean;
  total_rows: number;
  valid_rows_count: number;
  invalid_rows_count: number;
  products_created: number;
  products_updated: number;
  units_created: number;
  prices_created: number;
  rows: ImportRowResult[];
}
