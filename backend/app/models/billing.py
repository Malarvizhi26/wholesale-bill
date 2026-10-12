"""Sales Invoices, Returns, Quotations, and Delivery Challans ORM models."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantScopedModel, utc_now


# =============================================================================
# 1. Sales Invoices
# =============================================================================

class SalesInvoice(TenantScopedModel):
    """Posted or held sales invoice."""
    __tablename__ = "sales_invoices"

    device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False)
    invoice_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    party_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("parties.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    customer_gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    place_of_supply_state_code: Mapped[str] = mapped_column(String(2), default="33", nullable=False)
    is_b2b: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_list_id: Mapped[str] = mapped_column(String(36), ForeignKey("price_lists.id"), nullable=False)
    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="POSTED", nullable=False)  # 'DRAFT', 'POSTED', 'CANCELLED'
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    total_tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    round_off_amount: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    due_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    payment_mode: Mapped[str] = mapped_column(String(20), default="CASH", nullable=False)  # 'CASH', 'UPI', 'CARD', 'CREDIT', 'SPLIT'
    payment_breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    upi_qr_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_offline_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    offline_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    lines: Mapped[List["SalesInvoiceLine"]] = relationship("SalesInvoiceLine", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_sales_invoice_number"),
    )


class SalesInvoiceLine(TenantScopedModel):
    """Line item on a sales invoice."""
    __tablename__ = "sales_invoice_lines"

    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    actual_weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost_price_base_at_sale: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(10), default="FLAT", nullable=False)  # 'PERCENT' or 'FLAT'
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)
    gst_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    sgst_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    igst_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    invoice: Mapped["SalesInvoice"] = relationship("SalesInvoice", back_populates="lines")

    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_id", "line_number", name="uq_invoice_line_num"),
    )


# =============================================================================
# 2. Sales Returns / Credit Notes
# =============================================================================

class SalesReturn(TenantScopedModel):
    """Customer sales return / credit note."""
    __tablename__ = "sales_returns"

    return_number: Mapped[str] = mapped_column(String(60), nullable=False)
    return_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    original_invoice_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sales_invoices.id"), nullable=True)
    original_invoice_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    party_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("parties.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    refund_mode: Mapped[str] = mapped_column(String(20), default="CREDIT_NOTE", nullable=False)  # 'CASH', 'CREDIT_NOTE', 'UPI'
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[List["SalesReturnLine"]] = relationship("SalesReturnLine", back_populates="return_doc", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "return_number", name="uq_sales_return_number"),
    )


class SalesReturnLine(TenantScopedModel):
    """Line item on a sales return."""
    __tablename__ = "sales_return_lines"

    return_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_returns.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    return_condition: Mapped[str] = mapped_column(
        String(20), default="EXCESS", server_default="EXCESS", nullable=False
    )  # 'EXCESS' (good condition, restocked) or 'DAMAGED' (defective, not restocked)

    return_doc: Mapped["SalesReturn"] = relationship("SalesReturn", back_populates="lines")


# =============================================================================
# 3. Quotations / Estimates
# =============================================================================

class Quotation(TenantScopedModel):
    """Contractor or customer quotation / price estimate."""
    __tablename__ = "quotations"

    quotation_number: Mapped[str] = mapped_column(String(60), nullable=False)
    quotation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    party_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("parties.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    price_list_id: Mapped[str] = mapped_column(String(36), ForeignKey("price_lists.id"), nullable=False)
    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    place_of_supply_state_code: Mapped[str] = mapped_column(String(2), default="33", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)  # 'OPEN', 'CONVERTED', 'EXPIRED'
    converted_invoice_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    total_tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    round_off_amount: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[List["QuotationLine"]] = relationship("QuotationLine", back_populates="quotation", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "quotation_number", name="uq_quotation_number"),
    )


class QuotationLine(TenantScopedModel):
    """Line item on a quotation."""
    __tablename__ = "quotation_lines"

    quotation_id: Mapped[str] = mapped_column(String(36), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    quotation: Mapped["Quotation"] = relationship("Quotation", back_populates="lines")


# =============================================================================
# 4. Delivery Challans
# =============================================================================

class DeliveryChallan(TenantScopedModel):
    """Dispatch / delivery challan moving physical goods before final bill."""
    __tablename__ = "delivery_challans"

    challan_number: Mapped[str] = mapped_column(String(60), nullable=False)
    challan_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    party_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("parties.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    delivery_site_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vehicle_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DISPATCHED", nullable=False)  # 'DISPATCHED', 'DELIVERED', 'INVOICED'
    invoiced_invoice_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[List["DeliveryChallanLine"]] = relationship("DeliveryChallanLine", back_populates="challan", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "challan_number", name="uq_challan_number"),
    )


class DeliveryChallanLine(TenantScopedModel):
    """Line item on a delivery challan."""
    __tablename__ = "delivery_challan_lines"

    challan_id: Mapped[str] = mapped_column(String(36), ForeignKey("delivery_challans.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    challan: Mapped["DeliveryChallan"] = relationship("DeliveryChallan", back_populates="lines")
