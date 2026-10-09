"""Catalogue, Smart Units, and Pricing ORM models."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantScopedModel, utc_now


class Category(TenantScopedModel):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_category_tenant_name"),
    )


class Brand(TenantScopedModel):
    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_brand_tenant_name"),
    )


class Product(TenantScopedModel):
    __tablename__ = "products"

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tamil_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True)
    brand_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("brands.id"), nullable=True)
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(20), nullable=False)  # 'piece', 'kg', 'metre', 'sqft', 'litre'
    is_variable_weight: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_stock_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    reorder_quantity_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    purchase_price_base: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0.0000"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    units: Mapped[List["ProductUnit"]] = relationship("ProductUnit", back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    prices: Mapped[List["ProductPrice"]] = relationship("ProductPrice", back_populates="product", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_product_tenant_code"),
    )


class ProductUnit(TenantScopedModel):
    __tablename__ = "product_units"

    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)  # Multiplier to base unit
    can_buy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_sell: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_default_sales_unit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default_purchase_unit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="units")

    __table_args__ = (
        UniqueConstraint("tenant_id", "product_id", "unit_name", name="uq_product_unit"),
    )


class PriceList(TenantScopedModel):
    __tablename__ = "price_lists"

    code: Mapped[str] = mapped_column(String(30), nullable=False)  # 'RETAIL', 'WHOLESALE', 'CONTRACTOR'
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_pricelist_tenant_code"),
    )


class ProductPrice(TenantScopedModel):
    __tablename__ = "product_prices"

    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(30), nullable=False)
    price_list_id: Mapped[str] = mapped_column(String(36), ForeignKey("price_lists.id", ondelete="CASCADE"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_allowed_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped["Product"] = relationship("Product", back_populates="prices")
