"""Stock, Godowns, and Append-Only Inventory Ledger ORM models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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
    )  # 'PURCHASE', 'SALE', 'SALES_RETURN', 'PURCHASE_RETURN', 'ADJUSTMENT_IN', 'ADJUSTMENT_OUT', etc.
    quantity_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)  # + for IN, - for OUT
    unit_cost_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reference_doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'SALES_INVOICE', etc.
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
