"""Pydantic V2 schemas for Customer & Supplier Ledger, Vouchers, Allocations, and Reminders."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# 1. Party Master Schemas
# =============================================================================

class PartyCreateSchema(BaseModel):
    party_type: str = Field(default="CUSTOMER", description="CUSTOMER, SUPPLIER, or BOTH")
    name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=15)
    email: Optional[str] = Field(None, max_length=100)
    gstin: Optional[str] = Field(None, max_length=15)
    state_code: str = Field(default="33", min_length=2, max_length=2)
    billing_address: Optional[str] = None
    price_list_code: Optional[str] = Field(None, description="RETAIL, CONTRACTOR, or WHOLESALE")
    price_list_id: Optional[str] = None
    credit_limit: Decimal = Field(default=Decimal("0.00"), ge=0)
    credit_days: int = Field(default=0, ge=0)
    opening_balance: Decimal = Field(default=Decimal("0.00"))


class PartyResponseSchema(BaseModel):
    id: str
    party_type: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    state_code: str
    billing_address: Optional[str] = None
    price_list_id: Optional[str] = None
    credit_limit: Decimal
    credit_days: int
    opening_balance: Decimal
    current_balance: Decimal
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 2. Receipt Voucher / Customer Payment Schemas
# =============================================================================

class PaymentAllocationItemSchema(BaseModel):
    invoice_entry_id: str
    amount: Decimal = Field(gt=0)


class ReceiptVoucherCreateSchema(BaseModel):
    party_id: str
    voucher_date: Optional[date] = None
    payment_mode: str = Field(default="CASH", description="CASH, UPI, NEFT_RTGS, CHEQUE")
    reference_number: Optional[str] = None
    total_amount: Decimal = Field(..., gt=0)
    allocation_method: str = Field(default="OLDEST_FIRST", description="OLDEST_FIRST or MANUAL")
    manual_allocations: Optional[List[PaymentAllocationItemSchema]] = None
    notes: Optional[str] = None


class AllocationDetailSchema(BaseModel):
    allocation_id: str
    invoice_entry_id: str
    invoice_number: str
    allocated_amount: Decimal

    model_config = ConfigDict(from_attributes=True)


class ReceiptVoucherResponseSchema(BaseModel):
    id: str
    party_id: str
    party_name: str
    voucher_number: str
    voucher_date: date
    payment_mode: str
    reference_number: Optional[str] = None
    total_amount: Decimal
    allocated_amount: Decimal
    unallocated_amount: Decimal
    party_current_balance: Decimal
    allocations: List[AllocationDetailSchema] = []
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 3. Supplier Payment Schemas
# =============================================================================

class SupplierPaymentCreateSchema(BaseModel):
    supplier_id: str
    payment_date: Optional[date] = None
    payment_mode: str = Field(default="NEFT_RTGS", description="CASH, UPI, NEFT_RTGS, CHEQUE")
    reference_number: Optional[str] = None
    amount: Decimal = Field(..., gt=0)
    notes: Optional[str] = None


class SupplierPaymentResponseSchema(BaseModel):
    id: str
    supplier_id: str
    supplier_name: str
    voucher_number: str
    payment_date: date
    payment_mode: str
    reference_number: Optional[str] = None
    amount: Decimal
    supplier_current_balance: Decimal
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 4. Invoice-Wise Dues & Ageing Schemas
# =============================================================================

class InvoiceDueItemSchema(BaseModel):
    entry_id: str
    doc_type: str
    doc_number: str
    doc_date: date
    total_amount: Decimal
    allocated_amount: Decimal
    due_amount: Decimal
    age_days: int
    bucket: str  # '0-30', '31-60', '61-90', '90+'
    is_overdue: bool


class PartyAgeingSummarySchema(BaseModel):
    party_id: str
    party_name: str
    phone: Optional[str] = None
    credit_limit: Decimal
    credit_days: int
    current_balance: Decimal
    is_credit_exceeded: bool
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal
    total_overdue: Decimal
    unallocated_advance: Decimal
    open_invoices: List[InvoiceDueItemSchema] = []


# =============================================================================
# 5. Supplier Balances Summary Schemas
# =============================================================================

class SupplierBalanceItemSchema(BaseModel):
    supplier_id: str
    name: str
    phone: Optional[str] = None
    gstin: Optional[str] = None
    total_purchases: Decimal
    total_paid: Decimal
    current_balance: Decimal  # Negative = we owe, Positive = supplier advance
    net_payable: Decimal      # Absolute amount owed to supplier
    last_transaction_date: Optional[date] = None


class SupplierBalancesSummaryResponseSchema(BaseModel):
    total_suppliers: int
    total_payable_amount: Decimal
    suppliers: List[SupplierBalanceItemSchema]


# =============================================================================
# 6. Collection Reminders (WhatsApp & Call List) Schemas
# =============================================================================

class CollectionReminderItemSchema(BaseModel):
    party_id: str
    customer_name: str
    phone: Optional[str] = None
    current_balance: Decimal
    credit_limit: Decimal
    credit_days: int
    oldest_bill_number: Optional[str] = None
    oldest_bill_date: Optional[date] = None
    days_overdue: int
    overdue_amount: Decimal
    urgency_score: Decimal
    whatsapp_message: str
    upi_payment_link: str


class DispatchReminderRequestSchema(BaseModel):
    party_id: str
    phone_override: Optional[str] = None
    custom_note: Optional[str] = None


class DispatchReminderResponseSchema(BaseModel):
    log_id: str
    party_id: str
    recipient_phone: str
    message_text: str
    upi_link: Optional[str] = None
    status: str
    dispatched_at: datetime
