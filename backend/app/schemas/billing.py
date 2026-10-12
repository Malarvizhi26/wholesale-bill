"""Pydantic V2 schemas for Billing: Invoices, Returns, Quotations, Delivery Challans, and Barcode Search."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# 1. Product & Barcode Search Schemas
# =============================================================================

class ProductUnitInfo(BaseModel):
    unit_name: str
    conversion_factor: Decimal
    can_sell: bool = True
    barcode: Optional[str] = None
    is_default_sales_unit: bool = False
    selling_price: Decimal = Decimal("0.00")


class ProductSearchItemSchema(BaseModel):
    id: str
    code: str
    name: str
    tamil_name: Optional[str] = None
    hsn_code: str
    base_unit: str
    is_variable_weight: bool = False
    gst_rate_percent: Decimal = Decimal("18.00")
    current_stock_base: Decimal = Decimal("0.0000")
    current_stock_display: str = ""
    cost_price_base: Decimal = Decimal("0.0000")
    matched_unit: Optional[str] = None
    selling_price: Decimal = Decimal("0.00")
    units: List[ProductUnitInfo] = []


class UnitDecomposeRequestSchema(BaseModel):
    product_id: str
    quantity: Decimal
    unit_name: str
    actual_weight_kg: Optional[Decimal] = None


class UnitDecomposeResponseSchema(BaseModel):
    product_id: str
    base_quantity: Decimal
    base_unit: str
    display_units: str


# =============================================================================
# 2. Sales Invoice Schemas
# =============================================================================

class SalesInvoiceLineInputSchema(BaseModel):
    product_id: str
    unit_name: str
    conversion_factor: Decimal = Field(default=Decimal("1.0"), gt=0)
    quantity: Decimal = Field(gt=0)
    is_variable_weight: bool = False
    actual_weight_kg: Optional[Decimal] = None
    unit_price: Decimal = Field(ge=0)
    discount_type: str = "FLAT"  # 'PERCENT' or 'FLAT'
    discount_value: Decimal = Field(default=Decimal("0.00"), ge=0)
    hsn_code: Optional[str] = None
    gst_rate_percent: Optional[Decimal] = None


class SalesInvoiceCreateSchema(BaseModel):
    device_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    party_id: Optional[str] = None
    customer_name: str = "Walk-in Retail"
    customer_phone: Optional[str] = None
    customer_gstin: Optional[str] = None
    place_of_supply_state_code: str = "33"
    is_b2b: bool = False
    price_list_id: Optional[str] = None
    godown_id: Optional[str] = None
    payment_mode: str = "CASH"  # 'CASH', 'UPI', 'CARD', 'CREDIT', 'SPLIT'
    payment_breakdown: Optional[Dict[str, Any]] = None
    paid_amount: Optional[Decimal] = None
    lines: List[SalesInvoiceLineInputSchema]
    is_offline_created: bool = False
    offline_created_at: Optional[datetime] = None
    delivery_challan_id: Optional[str] = None  # If converted from Delivery Challan
    owner_override: bool = False  # Owner approval for credit-limit / floor-price breaches...
    owner_pin: Optional[str] = Field(default=None, max_length=32)  # ...must carry the owner PIN (verified server-side)


class SalesInvoiceLineResponseSchema(BaseModel):
    id: str
    line_number: int
    product_id: str
    unit_name: str
    conversion_factor: Decimal
    quantity: Decimal
    actual_weight_kg: Optional[Decimal] = None
    base_quantity: Decimal
    unit_price: Decimal
    cost_price_base_at_sale: Decimal
    discount_type: str
    discount_value: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    hsn_code: str
    gst_rate_percent: Decimal
    cgst_percent: Decimal
    cgst_amount: Decimal
    sgst_percent: Decimal
    sgst_amount: Decimal
    igst_percent: Decimal
    igst_amount: Decimal
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class SalesInvoiceResponseSchema(BaseModel):
    id: str
    invoice_number: str
    invoice_date: datetime
    party_id: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    customer_gstin: Optional[str] = None
    place_of_supply_state_code: str
    is_b2b: bool
    price_list_id: str
    godown_id: str
    status: str
    subtotal_amount: Decimal
    discount_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax_amount: Decimal
    round_off_amount: Decimal
    grand_total: Decimal
    paid_amount: Decimal
    due_amount: Decimal
    payment_mode: str
    payment_breakdown: Optional[Dict[str, Any]] = None
    upi_qr_string: Optional[str] = None
    is_offline_created: bool
    lines: List[SalesInvoiceLineResponseSchema] = []
    # Conflicts accepted for owner review: NEGATIVE_STOCK_WARNING, CREDIT_LIMIT_EXCEEDED, BELOW_FLOOR_PRICE
    review_flags: List[str] = []

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 3. Sales Returns / Credit Notes Schemas
# =============================================================================

class SalesReturnLineInputSchema(BaseModel):
    product_id: str
    unit_name: str
    conversion_factor: Decimal = Field(default=Decimal("1.0"), gt=0)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    gst_rate_percent: Optional[Decimal] = Field(default=None, ge=0)  # None -> product's GST rate
    return_condition: str = Field(default="EXCESS", description="'EXCESS' (restock) or 'DAMAGED' (do not restock)")


class SalesReturnCreateSchema(BaseModel):
    return_number: Optional[str] = None
    return_date: Optional[datetime] = None
    original_invoice_id: Optional[str] = None
    original_invoice_number: Optional[str] = None
    party_id: Optional[str] = None
    customer_name: str = "Walk-in Customer"
    godown_id: Optional[str] = None
    refund_mode: str = "CREDIT_NOTE"  # 'CREDIT_NOTE', 'CASH', 'UPI'
    reason: Optional[str] = None
    notes: Optional[str] = None
    lines: List[SalesReturnLineInputSchema]


class SalesReturnLineResponseSchema(BaseModel):
    id: str
    line_number: int
    product_id: str
    unit_name: str
    conversion_factor: Decimal
    quantity: Decimal
    base_quantity: Decimal
    unit_price: Decimal
    taxable_amount: Decimal
    gst_rate_percent: Decimal
    tax_amount: Decimal
    line_total: Decimal
    return_condition: str = "EXCESS"

    model_config = ConfigDict(from_attributes=True)


class SalesReturnResponseSchema(BaseModel):
    id: str
    return_number: str
    return_date: datetime
    original_invoice_id: Optional[str] = None
    original_invoice_number: Optional[str] = None
    party_id: Optional[str] = None
    customer_name: str
    godown_id: str
    refund_mode: str
    subtotal_amount: Decimal
    total_tax_amount: Decimal
    grand_total: Decimal
    reason: Optional[str] = None
    notes: Optional[str] = None
    lines: List[SalesReturnLineResponseSchema] = []

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 4. Quotations / Estimates Schemas
# =============================================================================

class QuotationLineInputSchema(BaseModel):
    product_id: str
    unit_name: str
    conversion_factor: Decimal = Field(default=Decimal("1.0"), gt=0)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    gst_rate_percent: Optional[Decimal] = Field(default=None, ge=0)  # None -> product's GST rate


class QuotationCreateSchema(BaseModel):
    quotation_number: Optional[str] = None
    quotation_date: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    party_id: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    price_list_id: Optional[str] = None
    godown_id: Optional[str] = None
    place_of_supply_state_code: str = "33"
    notes: Optional[str] = None
    lines: List[QuotationLineInputSchema]


class QuotationLineResponseSchema(BaseModel):
    id: str
    line_number: int
    product_id: str
    unit_name: str
    conversion_factor: Decimal
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    gst_rate_percent: Decimal
    tax_amount: Decimal
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class QuotationResponseSchema(BaseModel):
    id: str
    quotation_number: str
    quotation_date: datetime
    valid_until: Optional[datetime] = None
    party_id: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    price_list_id: str
    godown_id: str
    place_of_supply_state_code: str
    status: str
    converted_invoice_id: Optional[str] = None
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_tax_amount: Decimal
    round_off_amount: Decimal
    grand_total: Decimal
    notes: Optional[str] = None
    lines: List[QuotationLineResponseSchema] = []

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 5. Delivery Challan Schemas
# =============================================================================

class DeliveryChallanLineInputSchema(BaseModel):
    product_id: str
    unit_name: str
    conversion_factor: Decimal = Field(default=Decimal("1.0"), gt=0)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=0)


class DeliveryChallanCreateSchema(BaseModel):
    challan_number: Optional[str] = None
    challan_date: Optional[datetime] = None
    party_id: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    delivery_site_address: Optional[str] = None
    vehicle_number: Optional[str] = None
    godown_id: Optional[str] = None
    notes: Optional[str] = None
    lines: List[DeliveryChallanLineInputSchema]


class DeliveryChallanLineResponseSchema(BaseModel):
    id: str
    line_number: int
    product_id: str
    unit_name: str
    conversion_factor: Decimal
    quantity: Decimal
    base_quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class DeliveryChallanResponseSchema(BaseModel):
    id: str
    challan_number: str
    challan_date: datetime
    party_id: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    delivery_site_address: Optional[str] = None
    vehicle_number: Optional[str] = None
    godown_id: str
    status: str
    invoiced_invoice_id: Optional[str] = None
    subtotal_amount: Decimal
    grand_total: Decimal
    notes: Optional[str] = None
    lines: List[DeliveryChallanLineResponseSchema] = []

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 6. Owner Review Flags (stock_alerts)
# =============================================================================

class ReviewFlagResponseSchema(BaseModel):
    id: str
    alert_type: str  # 'NEGATIVE_STOCK_WARNING', 'CREDIT_LIMIT_EXCEEDED', 'BELOW_FLOOR_PRICE'
    status: str  # 'OPEN', 'RESOLVED'
    reference_doc_type: str
    reference_doc_id: str
    reference_doc_number: str
    product_id: Optional[str] = None
    party_id: Optional[str] = None
    godown_id: Optional[str] = None
    message: str
    is_offline_created: bool
    owner_override: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReviewFlagResolveSchema(BaseModel):
    owner_pin: str = Field(..., max_length=32)
    notes: Optional[str] = None
