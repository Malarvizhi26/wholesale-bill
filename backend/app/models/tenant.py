"""Tenant, Device, Number Series, and User ORM models."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantScopedModel, utc_now


class Tenant(Base):
    """Root tenant entity representing a hardware business."""
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    phone: Mapped[str] = mapped_column(String(15), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str] = mapped_column(Text, nullable=False)
    address_line2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), default="33", nullable=False)  # 33 = Tamil Nadu
    pincode: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), default="INR", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Device(TenantScopedModel):
    """Counter terminal node registering desktop installations."""
    __tablename__ = "devices"

    device_code: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. COUNTER-1
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    is_counter: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "device_code", name="uq_device_tenant_code"),
    )


class NumberSeries(TenantScopedModel):
    """Pre-allocated series blocks for offline and centralized document numbering."""
    __tablename__ = "number_series"

    device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'SALES_INVOICE', 'QUOTATION', etc.
    financial_year: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. '2026-27'
    prefix: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. 'C1/26-27/'
    current_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    range_start: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    range_end: Mapped[int] = mapped_column(Integer, default=999999, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "device_id", "doc_type", "financial_year", name="uq_number_series"),
    )


class User(TenantScopedModel):
    """Staff, clerks, accountants, and owners."""
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="CLERK", nullable=False)  # 'OWNER', 'MANAGER', 'CLERK', 'ACCOUNTANT'
    pin_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 4-digit PIN for supervisor overrides
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_user_tenant_username"),
    )
