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
  purchase_price_base: number;
  units: ProductUnit[];
  // helper for POS
  stock_base?: number;
  display_stock?: string;
}

export interface Party {
  id: string;
  party_type: 'CUSTOMER' | 'SUPPLIER' | 'BOTH';
  name: string;
  phone?: string;
  gstin?: string;
  state_code: string;
  credit_limit: number;
  credit_days: number;
  current_balance: number;
  price_list_code?: 'RETAIL' | 'CONTRACTOR' | 'WHOLESALE';
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
  lines: POSLineItem[];
  grandTotal: number;
}
