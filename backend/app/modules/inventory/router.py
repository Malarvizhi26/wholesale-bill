"""Inventory API endpoints."""

from decimal import Decimal
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.models.catalogue import Product, ProductUnit, ProductPrice
from app.schemas.product import ProductCreateSchema, ProductResponseSchema
from app.modules.inventory.unit_converter import SmartUnitConverter, UnitDefinition

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/products", response_model=List[ProductResponseSchema])
async def list_products(
    search: Optional[str] = Query(None, description="Search by name, Tamil name, or code"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List catalogue products for current tenant."""
    tenant_id = get_current_tenant_id()
    query = (
        select(Product)
        .where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
        .options(selectinload(Product.units))
    )

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (Product.name.ilike(search_filter))
            | (Product.tamil_name.ilike(search_filter))
            | (Product.code.ilike(search_filter))
        )

    result = await session.execute(query)
    return result.scalars().all()


@router.post("/products", response_model=ProductResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Create a new product with packaging units."""
    tenant_id = get_current_tenant_id()
    product_id = str(uuid.uuid4())

    product = Product(
        id=product_id,
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        tamil_name=payload.tamil_name,
        category_id=payload.category_id,
        brand_id=payload.brand_id,
        hsn_code=payload.hsn_code,
        base_unit=payload.base_unit,
        is_variable_weight=payload.is_variable_weight,
        min_stock_base=payload.min_stock_base,
        reorder_quantity_base=payload.reorder_quantity_base,
        purchase_price_base=payload.purchase_price_base,
    )
    session.add(product)

    # Add units
    for u in payload.units:
        unit = ProductUnit(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            product_id=product_id,
            unit_name=u.unit_name,
            conversion_factor=u.conversion_factor,
            can_buy=u.can_buy,
            can_sell=u.can_sell,
            barcode=u.barcode,
            is_default_sales_unit=u.is_default_sales_unit,
            is_default_purchase_unit=u.is_default_purchase_unit,
        )
        session.add(unit)

    await session.commit()
    await session.refresh(product)
    return product


@router.get("/products/{product_id}/unit-display")
async def get_mixed_unit_display(
    product_id: str,
    base_qty: Decimal = Query(..., description="Quantity in base units to decompose"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Decompose base quantity into human-readable packaging breakdown (e.g. 963 pcs -> 9 Box 63 pcs)."""
    tenant_id = get_current_tenant_id()
    result = await session.execute(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
        .options(selectinload(Product.units))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    unit_defs = [
        UnitDefinition(
            unit_name=u.unit_name,
            conversion_factor=u.conversion_factor,
            can_buy=u.can_buy,
            can_sell=u.can_sell,
        )
        for u in product.units
    ]

    display_str = SmartUnitConverter.to_display_units(
        total_base_qty=base_qty,
        base_unit=product.base_unit,
        packaging_units=unit_defs,
    )
    return {
        "product_id": product_id,
        "product_name": product.name,
        "base_unit": product.base_unit,
        "base_quantity": base_qty,
        "display": display_str,
    }
