"""Pydantic schemas for Smart Inventory: Godowns, Purchases, Adjustments, Alerts, and Pricing."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# -------------------------------------------------------------
# 1. Godowns & Transfers
# -------------------------------------------------------------

class GodownCreateSchema(BaseModel):
    code: str
    name: str
    is_primary: bool = False


class GodownResponseSchema(BaseModel):
    id: str
    code: str
    name: str
    is_primary: bool
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GodownTransferCreateSchema(BaseModel):
    source_godown_id: str
    target_godown_id: str
    product_id: str
    unit_name: str
    quantity: Decimal = Field(gt=0, description="Quantity in selected unit")
    conversion_factor: Decimal = Field(gt=0, description="Conversion factor to base unit")
    notes: Optional[str] = None


class GodownTransferResponseSchema(BaseModel):
    product_id: str
    product_name: str
    source_godown_name: str
    target_godown_name: str
    unit_name: str
    quantity: Decimal
    base_quantity: Decimal
    unit_cost_base: Decimal
    transfer_reference: str
    transferred_at: datetime


class GodownStockItemSchema(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    tamil_name: Optional[str] = None
    base_unit: str
    current_quantity_base: Decimal
    weighted_avg_cost_base: Decimal
    display_stock: str
    min_stock_base: Decimal
    is_low_stock: bool


# -------------------------------------------------------------
# 2. Purchase Bills (Inward Stock & Landed Cost)
# -------------------------------------------------------------

class PurchaseBillLineCreateSchema(BaseModel):
    product_id: str
    unit_name: str
    conversion_factor: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    unit_purchase_price: Decimal = Field(ge=0)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    gst_rate_percent: Decimal = Field(default=Decimal("0.00"), ge=0)


class PurchaseBillCreateSchema(BaseModel):
    supplier_id: Optional[str] = None
    supplier_name: str
    supplier_invoice_number: str
    bill_date: Optional[datetime] = None
    godown_id: str
    freight_charges: Decimal = Field(default=Decimal("0.00"), ge=0)
    loading_charges: Decimal = Field(default=Decimal("0.00"), ge=0)
    other_expenses: Decimal = Field(default=Decimal("0.00"), ge=0)
    round_off_amount: Decimal = Field(default=Decimal("0.00"))
    notes: Optional[str] = None
    lines: List[PurchaseBillLineCreateSchema] = Field(min_length=1)


class PurchaseBillLineResponseSchema(BaseModel):
    id: str
    line_number: int
    product_id: str
    unit_name: str
    conversion_factor: Decimal
    quantity: Decimal
    base_quantity: Decimal
    unit_purchase_price: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    gst_rate_percent: Decimal
    tax_amount: Decimal
    line_total: Decimal
    apportioned_overhead: Decimal
    landed_cost_base: Decimal

    model_config = ConfigDict(from_attributes=True)


class PurchaseBillResponseSchema(BaseModel):
    id: str
    supplier_id: Optional[str] = None
    supplier_name: str
    supplier_invoice_number: str
    bill_date: datetime
    godown_id: str
    subtotal_taxable: Decimal
    total_tax_amount: Decimal
    freight_charges: Decimal
    loading_charges: Decimal
    other_expenses: Decimal
    round_off_amount: Decimal
    total_invoice_amount: Decimal
    notes: Optional[str] = None
    lines: List[PurchaseBillLineResponseSchema] = []

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# 3. Stock Adjustments (Physical Verification & Audits)
# -------------------------------------------------------------

class StockAdjustmentLineCreateSchema(BaseModel):
    product_id: str
    unit_name: str
    conversion_factor: Decimal = Field(gt=0)
    quantity: Decimal = Field(description="Negative for loss/theft/breakage, positive for surplus")


class StockAdjustmentCreateSchema(BaseModel):
    godown_id: str
    reason_type: str = Field(description="BREAKAGE, THEFT, EXPIRY, or COUNT_CORRECTION")
    notes: Optional[str] = None
    lines: List[StockAdjustmentLineCreateSchema] = Field(min_length=1)


class StockAdjustmentLineResponseSchema(BaseModel):
    id: str
    line_number: int
    product_id: str
    unit_name: str
    conversion_factor: Decimal
    quantity: Decimal
    base_quantity: Decimal
    unit_cost_base: Decimal
    discrepancy_value: Decimal

    model_config = ConfigDict(from_attributes=True)


class StockAdjustmentResponseSchema(BaseModel):
    id: str
    adjustment_number: str
    adjustment_date: datetime
    godown_id: str
    reason_type: str
    total_discrepancy_value: Decimal
    notes: Optional[str] = None
    lines: List[StockAdjustmentLineResponseSchema] = []

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# 4. Minimum-Stock Alerts
# -------------------------------------------------------------

class LowStockAlertItemSchema(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    tamil_name: Optional[str] = None
    base_unit: str
    current_stock_base: Decimal
    min_stock_base: Decimal
    reorder_quantity_base: Decimal
    deficit_base: Decimal
    suggested_reorder_base: Decimal
    alert_severity: str  # 'CRITICAL_NEGATIVE', 'OUT_OF_STOCK', 'CRITICAL_LOW', 'LOW_STOCK'
    display_stock: str
    display_suggested_reorder: str


# -------------------------------------------------------------
# 5. Product Price History
# -------------------------------------------------------------

class PriceHistoryItemSchema(BaseModel):
    price_list_id: str
    price_list_code: str
    price_list_name: str
    unit_name: str
    price: Decimal
    min_allowed_price: Optional[Decimal] = None
    effective_from: datetime
    effective_to: Optional[datetime] = None
    is_current: bool


class PurchaseCostHistoryItemSchema(BaseModel):
    purchase_date: datetime
    supplier_name: str
    supplier_invoice_number: str
    unit_name: str
    quantity: Decimal
    unit_purchase_price: Decimal
    landed_cost_base: Decimal


class ProductPriceHistoryResponseSchema(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    current_purchase_price_base: Decimal
    selling_price_history: List[PriceHistoryItemSchema] = []
    purchase_cost_history: List[PurchaseCostHistoryItemSchema] = []


class UpdateProductPricePayloadSchema(BaseModel):
    price_list_id: str
    unit_name: str
    price: Decimal = Field(ge=0)
    min_allowed_price: Optional[Decimal] = None
