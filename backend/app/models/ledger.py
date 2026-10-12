from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import today_ist
from app.models.base import TenantScopedModel, utc_now


class Party(TenantScopedModel):
    """Customer, Supplier, or Both."""
    __tablename__ = "parties"

    party_type: Mapped[str] = mapped_column(String(20), default="CUSTOMER", nullable=False)  # 'CUSTOMER', 'SUPPLIER', 'BOTH'
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(15), nullable=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), default="33", nullable=False)  # 33 = Tamil Nadu
    billing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_list_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("price_lists.id"), nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    credit_days: Mapped[int] = mapped_column(default=0, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LedgerEntry(TenantScopedModel):
    """Strictly append-only accounting ledger entry."""
    __tablename__ = "ledger_entries"

    party_id: Mapped[str] = mapped_column(String(36), ForeignKey("parties.id"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )  # 'SALES_INVOICE', 'PAYMENT_RECEIPT', 'SALES_RETURN_CREDIT_NOTE', etc.
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    reference_doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_doc_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reference_doc_number: Mapped[str] = mapped_column(String(60), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, default=today_ist, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class PaymentAllocation(TenantScopedModel):
    """Links a credit payment entry to a specific debit invoice entry."""
    __tablename__ = "payment_allocations"

    payment_entry_id: Mapped[str] = mapped_column(String(36), ForeignKey("ledger_entries.id"), nullable=False)
    invoice_entry_id: Mapped[str] = mapped_column(String(36), ForeignKey("ledger_entries.id"), nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class CollectionReminderLog(TenantScopedModel):
    """Dispatched WhatsApp and SMS payment reminders."""
    __tablename__ = "collection_reminder_logs"

    party_id: Mapped[str] = mapped_column(String(36), ForeignKey("parties.id"), nullable=False, index=True)
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    upi_payment_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SENT", nullable=False)  # 'SENT', 'SIMULATED', 'FAILED'
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

