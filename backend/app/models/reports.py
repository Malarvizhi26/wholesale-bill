"""Expense and Cash Drawer Session ORM models for Profit & Business Reports."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from sqlalchemy import Date, DateTime, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantScopedModel, utc_now


class Expense(TenantScopedModel):
    """Operating expense voucher entry."""
    __tablename__ = "expenses"

    voucher_number: Mapped[str] = mapped_column(String(60), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # SHOP_RENT, ELECTRICITY, SALARY_WAGES, TEA_HAMALI, FREIGHT_OUTWARD, REPAIRS_MAINTENANCE, OFFICE_STATIONERY, MISC
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_mode: Mapped[str] = mapped_column(String(20), default="CASH", nullable=False)  # CASH, UPI, NEFT_RTGS, CHEQUE
    vendor_or_recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_direct_expense: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "voucher_number", name="uq_expense_voucher_number"),
    )


class CashDrawerSession(TenantScopedModel):
    """Cash drawer / counter shift reconciliation session."""
    __tablename__ = "cash_drawer_sessions"

    session_code: Mapped[str] = mapped_column(String(60), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    counter_name: Mapped[str] = mapped_column(String(100), default="Counter 1", nullable=False)
    cashier_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    session_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)  # OPEN, CLOSED, RECONCILED

    opening_cash: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    cash_sales_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    cash_ledger_receipts: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    cash_expenses_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    cash_supplier_payouts: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    expected_cash_drawer: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    actual_cash_counted: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    discrepancy_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    denominations: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "session_code", name="uq_cash_session_code"),
    )
