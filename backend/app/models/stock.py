"""Stock, Godowns, Purchases, Adjustments, and Append-Only Inventory Ledger ORM models."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantScopedModel, utc_now


class Godown(TenantScopedModel):
    __tablename__ = "godowns"

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_godown_tenant_code"),
    )


class StockMovement(TenantScopedModel):
    """Strictly append-only stock movement ledger."""
    __tablename__ = "stock_movements"

    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )  # 'PURCHASE', 'SALE', 'SALES_RETURN', 'PURCHASE_RETURN', 'ADJUSTMENT_IN', 'ADJUSTMENT_OUT', 'TRANSFER_IN', 'TRANSFER_OUT', 'OPENING'
    quantity_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)  # + for IN, - for OUT
    unit_cost_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reference_doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'PURCHASE_BILL', 'SALES_INVOICE', 'STOCK_ADJUSTMENT', 'GODOWN_TRANSFER'
    reference_doc_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reference_doc_number: Mapped[str] = mapped_column(String(60), nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class StockBalance(TenantScopedModel):
    """Fast cache for real-time stock balance and weighted average cost per godown."""
    __tablename__ = "stock_balances"

    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    current_quantity_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    weighted_avg_cost_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    last_movement_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "godown_id", "product_id", name="uq_stock_balance"),
    )


class PurchaseBill(TenantScopedModel):
    """Supplier purchase invoice entry."""
    __tablename__ = "purchase_bills"

    supplier_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("parties.id"), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_invoice_number: Mapped[str] = mapped_column(String(60), nullable=False)
    bill_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    subtotal_taxable: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    total_tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    freight_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    loading_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    other_expenses: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    round_off_amount: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"), nullable=False)
    total_invoice_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[List["PurchaseBillLine"]] = relationship(
        "PurchaseBillLine", back_populates="purchase_bill", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "supplier_invoice_number", name="uq_purchase_bill_invoice_number"),
    )


class PurchaseBillLine(TenantScopedModel):
    """Individual line item on a purchase bill."""
    __tablename__ = "purchase_bill_lines"

    purchase_bill_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_bills.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_purchase_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    apportioned_overhead: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    landed_cost_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    purchase_bill: Mapped["PurchaseBill"] = relationship("PurchaseBill", back_populates="lines")


class StockAdjustment(TenantScopedModel):
    """Physical count or discrepancy stock adjustment header."""
    __tablename__ = "stock_adjustments"

    adjustment_number: Mapped[str] = mapped_column(String(60), nullable=False)
    adjustment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    godown_id: Mapped[str] = mapped_column(String(36), ForeignKey("godowns.id"), nullable=False)
    reason_type: Mapped[str] = mapped_column(String(30), nullable=False)  # 'BREAKAGE', 'THEFT', 'EXPIRY', 'COUNT_CORRECTION'
    total_discrepancy_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[List["StockAdjustmentLine"]] = relationship(
        "StockAdjustmentLine", back_populates="adjustment", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "adjustment_number", name="uq_stock_adj_number"),
    )


class StockAdjustmentLine(TenantScopedModel):
    """Line item for physical stock adjustment."""
    __tablename__ = "stock_adjustment_lines"

    adjustment_id: Mapped[str] = mapped_column(String(36), ForeignKey("stock_adjustments.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)  # Positive for surplus, negative for loss
    base_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)  # Positive for IN, negative for OUT
    unit_cost_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discrepancy_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    adjustment: Mapped["StockAdjustment"] = relationship("StockAdjustment", back_populates="lines")
