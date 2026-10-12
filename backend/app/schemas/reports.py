"""Pydantic V2 schemas for Profit & Business Reports."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# 1. Daily Sales Schemas
# =============================================================================

class DailySalesSummarySchema(BaseModel):
    period_start: date
    period_end: date
    total_invoices: int
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax: Decimal
    round_off: Decimal
    grand_total: Decimal
    sales_by_mode: Dict[str, Decimal] = {}
    hourly_breakdown: List[Dict[str, Any]] = []


# =============================================================================
# 2. Gross Margin & Profitability Schemas
# =============================================================================

class ProductMarginItemSchema(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    base_unit: str
    quantity_sold_base: Decimal
    taxable_sales: Decimal
    cogs: Decimal
    gross_profit: Decimal
    margin_percent: Decimal


class GrossMarginReportSchema(BaseModel):
    period_start: date
    period_end: date
    total_taxable_sales: Decimal
    total_cogs: Decimal
    total_gross_profit: Decimal
    overall_margin_percent: Decimal
    top_margin_products: List[ProductMarginItemSchema] = []
    low_margin_products: List[ProductMarginItemSchema] = []


# =============================================================================
# 3. Expense Schemas
# =============================================================================

class ExpenseCreateSchema(BaseModel):
    expense_date: Optional[date] = None
    category: str = Field(..., description="SHOP_RENT, ELECTRICITY, SALARY_WAGES, TEA_HAMALI, FREIGHT_OUTWARD, REPAIRS_MAINTENANCE, OFFICE_STATIONERY, MISC")
    amount: Decimal = Field(..., gt=0)
    payment_mode: str = Field(default="CASH", description="CASH, UPI, NEFT_RTGS, CHEQUE")
    vendor_or_recipient: str = Field(..., min_length=1, max_length=255)
    reference_number: Optional[str] = None
    is_direct_expense: bool = False
    notes: Optional[str] = None


class ExpenseResponseSchema(BaseModel):
    id: str
    voucher_number: str
    expense_date: date
    category: str
    amount: Decimal
    payment_mode: str
    vendor_or_recipient: str
    reference_number: Optional[str] = None
    is_direct_expense: bool
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseSummarySchema(BaseModel):
    period_start: date
    period_end: date
    total_expenses: Decimal
    cash_expenses: Decimal
    bank_upi_expenses: Decimal
    by_category: Dict[str, Decimal] = {}
    expenses: List[ExpenseResponseSchema] = []


# =============================================================================
# 4. Outstanding Credit & Receivables Schemas
# =============================================================================

class DebtorSummaryItemSchema(BaseModel):
    party_id: str
    party_name: str
    phone: Optional[str] = None
    credit_limit: Decimal
    credit_days: int
    current_balance: Decimal
    is_credit_exceeded: bool
    days_overdue: int
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal
    total_overdue: Decimal


class OutstandingCreditReportSchema(BaseModel):
    total_parties: int
    total_receivables: Decimal
    total_overdue: Decimal
    breached_parties_count: int
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal
    top_debtors: List[DebtorSummaryItemSchema] = []


# =============================================================================
# 5. Stock Valuation Schemas
# =============================================================================

class StockValuationItemSchema(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    base_unit: str
    current_stock_base: Decimal
    wac_base: Decimal
    valuation_cost: Decimal
    display_stock: str
    is_low_stock: bool


class StockValuationReportSchema(BaseModel):
    total_products: int
    total_valuation_cost: Decimal
    total_retail_value: Decimal
    low_stock_count: int
    godown_valuations: Dict[str, Decimal] = {}
    items: List[StockValuationItemSchema] = []


# =============================================================================
# 6. Cash Reconciliation & Counter Drawer Schemas
# =============================================================================

class CashDrawerReconcileCreateSchema(BaseModel):
    counter_name: str = Field(default="Counter 1")
    cashier_name: Optional[str] = None
    session_date: Optional[date] = None
    opening_cash: Decimal = Field(default=Decimal("0.00"), ge=0)
    actual_cash_counted: Decimal = Field(..., ge=0)
    denominations: Optional[Dict[str, int]] = None
    notes: Optional[str] = None


class CashDrawerReconcileResponseSchema(BaseModel):
    id: str
    session_code: str
    session_date: date
    counter_name: str
    cashier_name: Optional[str] = None
    status: str
    opening_cash: Decimal
    cash_sales_amount: Decimal
    cash_ledger_receipts: Decimal
    cash_refunds_paid: Decimal = Decimal("0.00")  # CASH refunds on sales returns that day
    cash_expenses_paid: Decimal
    cash_supplier_payouts: Decimal
    expected_cash_drawer: Decimal
    actual_cash_counted: Decimal
    discrepancy_amount: Decimal
    denominations: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 7. Owner Morning Snapshot Schema
# =============================================================================

class OwnerMorningSnapshotSchema(BaseModel):
    today_sales: Decimal
    invoices_count_today: int
    gross_margin_estimate: Decimal
    gross_margin_percent: Decimal
    operating_expenses_today: Decimal
    net_operating_profit_today: Decimal
    cash_in_drawer: Decimal
    outstanding_receivables: Decimal
    overdue_debtors_count: int
    payables_due_suppliers: Decimal
    stock_total_valuation: Decimal
    low_stock_alerts_count: int
    top_selling_product: Optional[str] = None
